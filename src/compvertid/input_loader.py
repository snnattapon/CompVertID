"""
input_loader.py — ชั้นรับข้อมูลเข้า (แปลงทุกแหล่งให้เป็น DataFrame หน้าตาเดียวกัน)

รองรับ 2 ทางเข้า:
1. ไฟล์ .xlsx จาก Compound Discoverer (sheet 'Compounds', 202 คอลัมน์)
2. ไฟล์ .txt / .csv รายชื่อสาร (จาก NMR หรือเทคนิคอื่น)
   - แบบ A: ชื่ออย่างเดียว บรรทัดละชื่อ (ไม่มี header)
   - แบบ B/C: มี header ระบุคอลัมน์ Name / Formula / KEGG ID (คั่น tab หรือ comma)

หลักการ: ไม่ว่าเข้ามาแบบไหน คืน DataFrame ที่ "การันตี" ว่ามีคอลัมน์
         Name, Formula, KEGG ID เสมอ (เติมค่าว่างถ้าไม่มีข้อมูล)
         → ส่งเข้า core.map_dataframe() เดิมได้ทันที โดยไม่ต้องแก้ core

การแยกประเภทดูจากนามสกุลไฟล์:
    .xlsx / .xlsm  -> โหมด Compound Discoverer
    .txt / .csv / .tsv -> โหมดรายชื่อ
"""

import csv
from pathlib import Path

import pandas as pd

from . import config
from .core import load_and_validate


# ชื่อ header ที่ยอมรับสำหรับแต่ละคอลัมน์ (case-insensitive, ตัดช่องว่าง/underscore)
_NAME_ALIASES = {"name", "compound", "compoundname", "compound name"}
_FORMULA_ALIASES = {"formula", "molecularformula", "molecular formula"}
_KEGG_ALIASES = {"keggid", "kegg id", "kegg", "kegg_id"}

# นามสกุลที่ถือว่าเป็นไฟล์ Compound Discoverer
_CD_EXTENSIONS = {".xlsx", ".xlsm"}
# นามสกุลที่ถือว่าเป็นรายชื่อ
_LIST_EXTENSIONS = {".txt", ".csv", ".tsv"}


class UnsupportedInputError(ValueError):
    """ยกขึ้นเมื่อนามสกุลไฟล์ไม่รองรับ"""
    pass


def _canonical_header(h: str) -> str | None:
    """แปลง header ที่ผู้ใช้พิมพ์มา -> ชื่อคอลัมน์มาตรฐาน (Name/Formula/KEGG ID) หรือ None"""
    key = h.strip().lower().replace("_", " ").replace("  ", " ")
    key_nospace = key.replace(" ", "")
    if key in _NAME_ALIASES or key_nospace in {a.replace(" ", "") for a in _NAME_ALIASES}:
        return config.COL_NAME
    if key in _FORMULA_ALIASES or key_nospace in {a.replace(" ", "") for a in _FORMULA_ALIASES}:
        return config.COL_FORMULA
    if key in _KEGG_ALIASES or key_nospace in {a.replace(" ", "") for a in _KEGG_ALIASES}:
        return config.COL_KEGG_ID
    return None


def _looks_like_header(fields: list[str]) -> bool:
    """เดาว่าบรรทัดแรกเป็น header ไหม: ถ้ามีอย่างน้อยหนึ่งช่องตรงกับชื่อคอลัมน์ที่รู้จัก"""
    return any(_canonical_header(f) is not None for f in fields)


def _sniff_delimiter(sample: str) -> str:
    """เดาตัวคั่น (tab หรือ comma) จากเนื้อไฟล์ ถ้าเดาไม่ได้ใช้ค่า default ตามบริบท"""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
        return dialect.delimiter
    except csv.Error:
        # เดาไม่ออก: ถ้ามี tab ให้ใช้ tab ไม่งั้น comma
        if "\t" in sample:
            return "\t"
        return ","


def _ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """เติมคอลัมน์ Name/Formula/KEGG ID ที่ขาดให้เป็นค่าว่าง แล้วจัดลำดับ"""
    for col in config.REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    # ใส่ NO ถ้ายังไม่มี (ไล่ลำดับตามแถว)
    if config.COL_NO not in df.columns:
        df.insert(0, config.COL_NO, range(1, len(df) + 1))
    return df


def load_name_list(filepath) -> pd.DataFrame:
    """
    อ่านไฟล์รายชื่อ (.txt/.csv/.tsv) แล้วคืน DataFrame ที่มีคอลัมน์มาตรฐาน

    รองรับ:
    - ชื่ออย่างเดียว บรรทัดละชื่อ (ไม่มี header)
    - มี header: Name / Formula / KEGG ID (คั่น tab หรือ comma)
    บรรทัดว่างและบรรทัดขึ้นต้นด้วย '#' จะถูกข้าม (comment)
    """
    path = Path(filepath)
    raw = path.read_text(encoding="utf-8-sig")  # utf-8-sig กัน BOM จาก Excel/Notepad

    # เก็บเฉพาะบรรทัดที่มีเนื้อหา ตัด comment
    lines = [ln.rstrip("\n\r") for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]

    if not lines:
        # ไฟล์ว่าง → คืน DataFrame เปล่าที่มีคอลัมน์ครบ
        return _ensure_required_columns(pd.DataFrame({config.COL_NAME: []}))

    delimiter = _sniff_delimiter("\n".join(lines[:5]))
    rows = [next(csv.reader([ln], delimiter=delimiter)) for ln in lines]
    rows = [[c.strip() for c in r] for r in rows]

    first = rows[0]
    if _looks_like_header(first):
        # มี header → map แต่ละคอลัมน์เข้าชื่อมาตรฐาน
        header_map = {}
        for i, h in enumerate(first):
            canon = _canonical_header(h)
            if canon:
                header_map[i] = canon
        data_rows = rows[1:]
        records = []
        for r in data_rows:
            rec = {}
            for i, canon in header_map.items():
                rec[canon] = r[i] if i < len(r) else ""
            records.append(rec)
        df = pd.DataFrame(records)
    else:
        # ไม่มี header → ถือว่าคอลัมน์แรกคือ Name (คอลัมน์อื่นถ้ามีก็ทิ้ง เพราะไม่รู้ว่าเป็นอะไร)
        names = [r[0] for r in rows if r and r[0]]
        df = pd.DataFrame({config.COL_NAME: names})

    return _ensure_required_columns(df)


def load_input(filepath) -> pd.DataFrame:
    """
    ทางเข้าหลัก: รับ path ไฟล์ใด ๆ แล้วเลือกวิธีอ่านตามนามสกุล
    คืน DataFrame ที่การันตีคอลัมน์ Name / Formula / KEGG ID

    - .xlsx/.xlsm -> Compound Discoverer (ผ่าน load_and_validate เดิม)
    - .txt/.csv/.tsv -> รายชื่อ (ผ่าน load_name_list)
    """
    ext = Path(filepath).suffix.lower()
    if ext in _CD_EXTENSIONS:
        return load_and_validate(filepath)
    if ext in _LIST_EXTENSIONS:
        return load_name_list(filepath)
    raise UnsupportedInputError(
        f"นามสกุลไฟล์ '{ext}' ไม่รองรับ. รองรับเฉพาะ: "
        f"{sorted(_CD_EXTENSIONS | _LIST_EXTENSIONS)}"
    )
