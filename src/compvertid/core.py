"""
core.py — ตรรกะการ map compound → KEGG ID (ล้วน ๆ ไม่ผูกกับ UI)

หลักการออกแบบ:
- ทุกฟังก์ชันเป็น "ฟังก์ชันบริสุทธิ์" เท่าที่ทำได้ (รับ input → คืน output)
- ไม่มี print / tqdm / emoji / การผูก path ในไฟล์นี้
- การรายงานความคืบหน้าใช้ progress_callback ที่ชั้นบน (CLI/GUI) ส่งเข้ามา
- การคุยกับ KEGG ทำผ่าน KeggClient (ฉีดเข้ามา) → test ได้ด้วยการ mock

จุดที่ปรับปรุงจากสคริปต์เดิม:
- ตรวจสอบคอลัมน์ที่จำเป็นก่อน map → แจ้ง error อ่านเข้าใจได้ แทน KeyError
- แทนที่ pandas groupby().apply() (deprecated) ด้วยการวนลูปที่ควบคุมได้
"""

import re

import pandas as pd

from . import config
from .kegg_api import KeggClient


# ==================================================================
# FUNCTIONS: formula normalization, parsing, name cleaning, lipid detection
# (ยกมาจากสคริปต์เดิม — เป็นฟังก์ชันบริสุทธิ์อยู่แล้ว)
# ==================================================================
def normalize_formula(formula: str) -> str:
    """
    ปรับสูตรให้อยู่ในรูปแบบเทียบกันได้:
    Compound Discoverer ใช้ "C5 H13 N O" (มีเว้นวรรค)
    KEGG ใช้ "C5H13NO" (ไม่มีเว้นวรรค) และมักละเลข '1' ที่ตามหลังธาตุ (CH4 ไม่ใช่ C1H4)
    """
    if not isinstance(formula, str):
        return ""
    f = formula.replace(" ", "").strip()
    f = re.sub(r"([A-Z][a-z]?)1(?![0-9])", r"\1", f)
    return f


def parse_formula_to_atoms(formula: str) -> dict:
    """
    แยกสูตรเป็น dict ธาตุ → จำนวน
    เช่น "C5H13NO" → {"C": 5, "H": 13, "N": 1, "O": 1}
    """
    atoms = {}
    for match in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
        elem, count = match.group(1), match.group(2)
        if elem:
            atoms[elem] = atoms.get(elem, 0) + (int(count) if count else 1)
    return atoms


def formula_diff_explanation(f1: str, f2: str) -> str:
    """
    อธิบายความต่างระหว่างสองสูตร ช่วยบอกว่าต่างเพราะ charge หรือเป็นคนละสาร
    """
    a1 = parse_formula_to_atoms(f1)
    a2 = parse_formula_to_atoms(f2)
    all_elems = set(a1) | set(a2)
    diffs = []
    for e in sorted(all_elems):
        d = a2.get(e, 0) - a1.get(e, 0)
        if d != 0:
            diffs.append(f"{e}{d:+d}")
    if diffs == ["H+1"] or diffs == ["H-1"]:
        return f"({', '.join(diffs)}) charge state — quaternary ammonium compounds are often stored as protonated forms in KEGG"
    return f"({', '.join(diffs)})"


def classify_formula_diff(f1: str, f2: str) -> str:
    """
    จำแนกว่าความต่างระหว่างสองสูตรเป็นแบบไหน:
      "match"       — เหมือนกัน (ไม่ต่าง)
      "charge"      — ต่างแค่ไฮโดรเจน (H±1, H±2) → มักเป็นเรื่อง charge/protonation
                      ผลยังน่าเชื่อถือ ถือเป็น false alarm
      "mismatch"    — ต่างที่ธาตุอื่นหรือ backbone → อาจเป็นคนละสาร ต้องตรวจ

    ใช้แยก confidence: charge_diff (เหลือง) vs formula_mismatch (ส้ม)
    เพื่อให้ผู้ใช้ (และ GUI) แยกสองกรณีนี้ออกจากกันได้จากคอลัมน์ Confidence เลย
    """
    a1 = parse_formula_to_atoms(f1)
    a2 = parse_formula_to_atoms(f2)
    all_elems = set(a1) | set(a2)

    diffs = {}
    for e in all_elems:
        d = a2.get(e, 0) - a1.get(e, 0)
        if d != 0:
            diffs[e] = d

    if not diffs:
        return "match"

    # ต่างเฉพาะ H และจำนวนไม่มาก (|ΔH| <= 2) → ถือเป็น charge/protonation
    if set(diffs.keys()) == {"H"} and abs(diffs["H"]) <= 2:
        return "charge"

    return "mismatch"


def clean_name(name: str) -> list:
    """
    Compound Discoverer อาจคืนหลายชื่อคั่นด้วย ';' เช่น "Choline; Phthalic anhydride"
    แยกเป็น list และตัดช่องว่าง
    """
    if not isinstance(name, str):
        return []
    parts = [p.strip() for p in name.split(";")]
    return [p for p in parts if p]

def name_matches_exactly(query_name: str, kegg_names: str) -> bool:
    """
    เทียบว่าชื่อที่ค้น (query_name) ตรงเป๊ะกับชื่อใดชื่อหนึ่งที่ KEGG คืนมาไหม
    KEGG คืนชื่อหลายชื่อคั่นด้วย ';' เช่น "Choline; ..."
    เทียบแบบ case-insensitive และตัดช่องว่างหัวท้าย
    """
    if not query_name or not isinstance(kegg_names, str):
        return False
    q = query_name.strip().lower()
    candidates = [n.strip().lower() for n in kegg_names.split(";")]
    return q in candidates

def is_lipid_species(name: str) -> bool:
    """
    เช็คว่าชื่อเป็น lipid species notation ที่ KEGG ไม่ครอบคลุมไหม
    เช่น PC(18:1/0:0), LPC(16:0), TG(18:1/18:1/18:1)
    """
    prefixes = "|".join(config.LIPID_PREFIXES)
    pattern = rf"^({prefixes})\(\d+:\d+"
    return bool(re.match(pattern, name.strip()))


# ==================================================================
# MAIN LOGIC: map compound เดียว
# ==================================================================
def map_one_compound(row: pd.Series, client: KeggClient) -> dict:
    """
    map compound หนึ่งแถวไปยัง KEGG
    client: KeggClient ที่ฉีดเข้ามา (จัดการ cache/retry/delay ให้เอง)
    """
    name = row.get(config.COL_NAME, "")
    formula = row.get(config.COL_FORMULA, "")
    existing_kegg = row.get(config.COL_KEGG_ID, None)

    result = {
        "Input_Name": name,
        "Input_Formula": formula,
        "Original_KEGG_ID": existing_kegg if pd.notna(existing_kegg) else "",
        "Mapped_KEGG_ID": "",
        "KEGG_Name": "",
        "KEGG_Formula": "",
        "Formula_Match": "",
        "Confidence": "",
        "Notes": "",
    }

    input_formula_norm = normalize_formula(formula)

    # --- เงื่อนไข 1: มี KEGG ID อยู่แล้ว → verify ---
    if pd.notna(existing_kegg) and str(existing_kegg).strip().startswith("C"):
        cid = str(existing_kegg).strip()
        info = client.get_compound(cid)

        result["Mapped_KEGG_ID"] = cid
        result["KEGG_Name"] = info["kegg_name"] or ""
        result["KEGG_Formula"] = info["kegg_formula"] or ""

        if input_formula_norm and info["kegg_formula"]:
            kegg_norm = normalize_formula(info["kegg_formula"])
            diff_kind = classify_formula_diff(input_formula_norm, kegg_norm)
            if diff_kind == "match":
                result["Formula_Match"] = "Yes"
                result["Confidence"] = "verified_high"
                result["Notes"] = "Correct KEGG ID (formula matches)"
            elif diff_kind == "charge":
                result["Formula_Match"] = "Charge"
                diff_msg = formula_diff_explanation(input_formula_norm, kegg_norm)
                result["Confidence"] = "charge_diff"
                result["Notes"] = f"Likely charge/protonation difference: input={input_formula_norm}, KEGG={kegg_norm} {diff_msg}"
            else:
                result["Formula_Match"] = "No"
                diff_msg = formula_diff_explanation(input_formula_norm, kegg_norm)
                result["Confidence"] = "formula_mismatch"
                result["Notes"] = f"Different Formula: input={input_formula_norm}, KEGG={kegg_norm} {diff_msg}"
        else:
            result["Formula_Match"] = "Unknown"
            result["Confidence"] = "verified_no_formula"
            result["Notes"] = "Fetched KEGG data but no formula available for comparison"
        return result

    # --- เงื่อนไข 2: ไม่มี KEGG ID → ต้องค้นหา ---
    name_candidates = clean_name(name)
    if not name_candidates:
        result["Confidence"] = "no_name"
        result["Notes"] = "No compound name in input"
        return result

    lipid_names = [n for n in name_candidates if is_lipid_species(n)]
    non_lipid_names = [n for n in name_candidates if not is_lipid_species(n)]

    if lipid_names and not non_lipid_names:
        result["Confidence"] = "not_in_KEGG"
        result["Notes"] = f"Lipid species (skipped): {'; '.join(lipid_names)}"
        return result

    all_hits = []
    for candidate in non_lipid_names:
        hits = client.find_by_name(candidate)
        for h in hits:
            h["query_name"] = candidate
        all_hits.extend(hits)

    if not all_hits:
        result["Confidence"] = "not_found"
        result["Notes"] = f"Search not found in KEGG: {'; '.join(non_lipid_names)}"
        if lipid_names:
            result["Notes"] += f" (lipid species skipped: {'; '.join(lipid_names)})"
        return result

    if len(all_hits) == 1:
        cid = all_hits[0]["cid"]
        info = client.get_compound(cid)
        result["Mapped_KEGG_ID"] = cid
        result["KEGG_Name"] = info["kegg_name"] or all_hits[0]["names"]
        result["KEGG_Formula"] = info["kegg_formula"] or ""

        if input_formula_norm and info["kegg_formula"]:
            kegg_norm = normalize_formula(info["kegg_formula"])
            diff_kind = classify_formula_diff(input_formula_norm, kegg_norm)
            if diff_kind == "match":
                result["Formula_Match"] = "Yes"
                result["Confidence"] = "found_high"
                result["Notes"] = "Found 1 match with matching formula"
            elif diff_kind == "charge":
                result["Formula_Match"] = "Charge"
                diff_msg = formula_diff_explanation(input_formula_norm, kegg_norm)
                result["Confidence"] = "charge_diff"
                result["Notes"] = f"Found 1 match, likely charge/protonation difference: KEGG={info['kegg_formula']} {diff_msg}"
            else:
                result["Formula_Match"] = "No"
                result["Confidence"] = "formula_mismatch"
                result["Notes"] = f"Found 1 match but formula doesn't match: KEGG={info['kegg_formula']}"
        else:
            result["Formula_Match"] = "Unknown"
            result["Confidence"] = "found_no_formula_check"
            result["Notes"] = "Found 1 match (no formula to compare)"
        return result

# หลายผลลัพธ์ — ตัดสินตามลำดับ: ชื่อตรงเป๊ะ → formula → fallback
    # ขั้น 1: หาตัวที่ชื่อตรงเป๊ะกับที่ค้น (case-insensitive)
    exact_name_hits = [
        h for h in all_hits
        if name_matches_exactly(h.get("query_name", ""), h.get("names", ""))
    ]

    # ดึง info เฉพาะกลุ่มที่จะพิจารณา (ถ้ามีชื่อตรงเป๊ะ ดึงเฉพาะกลุ่มนั้นก่อน ประหยัด API)
    hits_to_inspect = exact_name_hits if exact_name_hits else all_hits
    for hit in hits_to_inspect:
        if "info" not in hit:
            hit["info"] = client.get_compound(hit["cid"])

    # ขั้น 2: ถ้ามีชื่อตรงเป๊ะ
    if exact_name_hits:
        # ในกลุ่มชื่อตรงเป๊ะ ลองหาตัวที่ formula ตรงด้วย (ถ้ามี input formula)
        exact_and_formula = []
        if input_formula_norm:
            for hit in exact_name_hits:
                kegg_f = hit["info"].get("kegg_formula")
                if kegg_f and normalize_formula(kegg_f) == input_formula_norm:
                    exact_and_formula.append(hit)

        if len(exact_and_formula) == 1:
            # ดีที่สุด: ชื่อตรง + formula ตรง
            chosen = exact_and_formula[0]
            result["Mapped_KEGG_ID"] = chosen["cid"]
            result["KEGG_Name"] = chosen["info"]["kegg_name"] or chosen["names"]
            result["KEGG_Formula"] = chosen["info"]["kegg_formula"] or ""
            result["Formula_Match"] = "Yes"
            result["Confidence"] = "found_high"
            result["Notes"] = f"Exact name match + formula match (from {len(all_hits)} results)"
            return result

        if len(exact_name_hits) == 1:
            # ชื่อตรงเป๊ะตัวเดียว — ใช้เลย (verify formula ถ้ามี)
            chosen = exact_name_hits[0]
            result["Mapped_KEGG_ID"] = chosen["cid"]
            result["KEGG_Name"] = chosen["info"]["kegg_name"] or chosen["names"]
            result["KEGG_Formula"] = chosen["info"]["kegg_formula"] or ""
            if input_formula_norm and chosen["info"].get("kegg_formula"):
                kegg_norm = normalize_formula(chosen["info"]["kegg_formula"])
                if kegg_norm == input_formula_norm:
                    result["Formula_Match"] = "Yes"
                    result["Confidence"] = "found_high"
                    result["Notes"] = f"Exact name match + formula match (from {len(all_hits)} results)"
                else:
                    result["Formula_Match"] = "No"
                    result["Confidence"] = "name_match_verify"
                    result["Notes"] = f"Exact name match but formula differs (KEGG={chosen['info']['kegg_formula']}) — please verify"
            else:
                result["Formula_Match"] = "Unknown"
                result["Confidence"] = "name_match_verify"
                result["Notes"] = f"Exact name match, no formula to confirm (from {len(all_hits)} results) — please verify"
            return result

        # ชื่อตรงเป๊ะหลายตัว (สารชื่อพ้อง) — คืนทั้งหมดให้ verify
        cids = ";".join([h["cid"] for h in exact_name_hits])
        result["Mapped_KEGG_ID"] = cids
        result["KEGG_Name"] = " | ".join([h["info"]["kegg_name"] or h["names"] for h in exact_name_hits])
        result["Formula_Match"] = "Unknown"
        result["Confidence"] = "ambiguous"
        result["Notes"] = f"Multiple exact name matches ({len(exact_name_hits)} entries) — please verify"
        return result

    # ขั้น 3: ไม่มีชื่อตรงเป๊ะ → ใช้ formula กรอง (ตรรกะเดิม)
    formula_matches = []
    for hit in all_hits:
        if "info" not in hit:
            hit["info"] = client.get_compound(hit["cid"])
        info = hit["info"]
        if input_formula_norm and info.get("kegg_formula"):
            if normalize_formula(info["kegg_formula"]) == input_formula_norm:
                formula_matches.append(hit)

    if len(formula_matches) == 1:
        chosen = formula_matches[0]
        result["Mapped_KEGG_ID"] = chosen["cid"]
        result["KEGG_Name"] = chosen["info"]["kegg_name"] or chosen["names"]
        result["KEGG_Formula"] = chosen["info"]["kegg_formula"] or ""
        result["Formula_Match"] = "Yes"
        result["Confidence"] = "found_high"
        result["Notes"] = f"Filtered from {len(all_hits)} results with matching formula, left with 1"
    elif len(formula_matches) > 1:
        cids = ";".join([h["cid"] for h in formula_matches])
        result["Mapped_KEGG_ID"] = cids
        result["KEGG_Name"] = " | ".join([h["info"]["kegg_name"] or h["names"] for h in formula_matches])
        result["KEGG_Formula"] = formula_matches[0]["info"]["kegg_formula"] or ""
        result["Formula_Match"] = "Yes"
        result["Confidence"] = "ambiguous"
        result["Notes"] = f"Multiple results with matching formula ({len(formula_matches)} entries) — please verify"
    else:
        cids = ";".join([h["cid"] for h in all_hits[:5]])
        result["Mapped_KEGG_ID"] = cids
        result["Formula_Match"] = "No"
        result["Confidence"] = "low"
        result["Notes"] = f"Found {len(all_hits)} results, no exact name or formula match — please verify"

    return result    


# ==================================================================
# อ่าน + ตรวจสอบไฟล์ Excel
# ==================================================================
class MissingColumnsError(ValueError):
    """ยกขึ้นเมื่อไฟล์ input ขาดคอลัมน์ที่จำเป็น"""
    pass


def load_and_validate(filepath, sheet_name: str = config.SHEET_NAME) -> pd.DataFrame:
    """
    อ่านไฟล์ Excel และตรวจว่ามีคอลัมน์ที่จำเป็นครบ
    ถ้าขาด → ยก MissingColumnsError พร้อมบอกว่าขาดคอลัมน์ไหน
    (แก้ปัญหาเดิมที่ hard-code ชื่อคอลัมน์ แล้ว crash ด้วย KeyError ที่อ่านยาก)
    """
    df = pd.read_excel(filepath, sheet_name=sheet_name)
    missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise MissingColumnsError(
            f"ไฟล์ '{filepath}' (sheet '{sheet_name}') ขาดคอลัมน์ที่จำเป็น: {missing}. "
            f"คอลัมน์ที่พบในไฟล์: {list(df.columns)[:10]}..."
        )
    return df


# ==================================================================
# map ทั้งไฟล์ + ใส่ Mode tag
# ==================================================================
def map_dataframe(
    df: pd.DataFrame,
    mode_tag: str,
    client: KeggClient,
    progress_callback=None,
) -> pd.DataFrame:
    """
    map ทุกแถวใน DataFrame แล้วเพิ่มคอลัมน์ Mode

    progress_callback: ฟังก์ชัน callback(current:int, total:int, name:str) หรือ None
                       ให้ชั้นบน (CLI/GUI) เอาไปแสดง progress bar เอง
                       core ไม่รู้ว่าจะแสดงผลยังไง
    """
    results = []
    total = len(df)
    for i, (idx, row) in enumerate(df.iterrows(), start=1):
        if progress_callback:
            current_name = str(row.get(config.COL_NAME, "?"))[:40]
            progress_callback(i, total, current_name)

        result = map_one_compound(row, client)
        result["Row_NO"] = row.get(config.COL_NO, idx + 1)
        result["Mode"] = mode_tag
        results.append(result)

    return pd.DataFrame(results)


# ==================================================================
# merge pos+neg + dedupe ตาม KEGG ID
# ==================================================================
def _aggregate_group(g: pd.DataFrame) -> pd.Series:
    """รวมแถวที่มี Mapped_KEGG_ID เดียวกันเป็นแถวเดียว"""
    modes = sorted(g["Mode"].unique(), key=lambda x: 0 if x == "pos" else 1)
    g = g.copy()
    g["_priority"] = g["Confidence"].map(config.CONFIDENCE_PRIORITY).fillna(99)
    g = g.sort_values("_priority")
    base = g.iloc[0].copy()

    base["Mode"] = ";".join(modes)
    base["Input_Name"] = " | ".join(g["Input_Name"].astype(str).unique())
    base["Row_NO"] = ";".join(g["Row_NO"].astype(str).unique())

    if len(modes) > 1:
        existing_note = base["Notes"] if pd.notna(base["Notes"]) else ""
        base["Notes"] = f"[Found in {';'.join(modes)}] {existing_note}".strip()

    if "_priority" in base.index:
        base = base.drop("_priority")
    return base


def merge_and_dedupe(
    df_pos: pd.DataFrame,
    df_neg: pd.DataFrame,
    info_callback=None,
) -> pd.DataFrame:
    """
    รวม pos+neg แล้ว dedupe ตาม KEGG ID:
    - KEGG ID ซ้ำ → รวมเป็นแถวเดียว Mode = "pos;neg"
    - ไม่มี KEGG ID / มีหลาย C number (ambiguous) → เก็บทุกแถว

    info_callback: callback(message:str) หรือ None สำหรับรายงานสรุป (ไม่ใช่ print ตรง)
    """
    def _report(msg):
        if info_callback:
            info_callback(msg)

    combined = pd.concat([df_pos, df_neg], ignore_index=True)
    _report(f"Before dedupe: {len(combined)} rows (pos: {len(df_pos)}, neg: {len(df_neg)})")

    def is_single_cid(cid):
        return isinstance(cid, str) and cid.startswith("C") and ";" not in cid

    mask_single = combined["Mapped_KEGG_ID"].apply(is_single_cid)
    df_dedupe = combined[mask_single].copy()
    df_keep_all = combined[~mask_single].copy()

    if len(df_dedupe) > 0:
        # แทน groupby().apply() (deprecated) ด้วยการวนลูปเอง เพื่อเลี่ยง warning/behavior
        # ที่ต่างกันตามเวอร์ชัน pandas ที่ผู้ใช้ลง
        grouped_rows = []
        for _cid, g in df_dedupe.groupby("Mapped_KEGG_ID", sort=False):
            grouped_rows.append(_aggregate_group(g))
        df_dedupe_grouped = pd.DataFrame(grouped_rows).reset_index(drop=True)

        n_before, n_after = len(df_dedupe), len(df_dedupe_grouped)
        _report(f"Dedupe by KEGG ID: {n_before} -> {n_after} rows (merged {n_before - n_after} duplicates)")
    else:
        df_dedupe_grouped = df_dedupe

    final = pd.concat([df_dedupe_grouped, df_keep_all], ignore_index=True)
    _report(f"After dedupe: {len(final)} rows")
    return final


# ==================================================================
# จัดเรียงคอลัมน์ + แถว ให้พร้อมเซฟ
# ==================================================================
def finalize(final_df: pd.DataFrame) -> pd.DataFrame:
    """จัดลำดับคอลัมน์และเรียงแถวตาม Mode + Confidence"""
    final_df = final_df[config.OUTPUT_COLUMNS].copy()
    final_df["_mode_sort"] = final_df["Mode"].map(config.MODE_SORT_ORDER).fillna(99)
    final_df = (
        final_df.sort_values(["_mode_sort", "Confidence", "Mapped_KEGG_ID"])
        .drop(columns=["_mode_sort"])
        .reset_index(drop=True)
    )
    return final_df
