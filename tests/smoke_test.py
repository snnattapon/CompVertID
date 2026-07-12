"""
smoke_test.py — พิสูจน์ว่า refactor แล้วยังทำงานถูก โดยไม่ยิง network จริง

ใช้ FakeKeggClient แทน KeggClient จริง เพื่อทดสอบ:
1. ฟังก์ชันบริสุทธิ์ (normalize_formula, clean_name, is_lipid_species)
2. map_one_compound ทั้ง 3 เส้นทาง (verify / find / lipid-skip)
3. merge_and_dedupe รวมสารที่เจอทั้ง pos+neg เป็นแถวเดียว
4. load_and_validate จับไฟล์ขาดคอลัมน์ได้
"""
import sys
sys.path.insert(0, "../src")

import pandas as pd
from compvertid import (
    normalize_formula, clean_name, is_lipid_species,
    map_dataframe, merge_and_dedupe, finalize,
    load_and_validate, MissingColumnsError,
)
from compvertid import core


# ---- FakeKeggClient: ตอบแบบ hard-code แทนการยิง KEGG จริง ----
class FakeKeggClient:
    DB = {
        "C00114": {"kegg_name": "Choline", "kegg_formula": "C5H14NO", "kegg_exact_mass": 104.1},
        "C01595": {"kegg_name": "Linoleic acid", "kegg_formula": "C18H32O2", "kegg_exact_mass": 280.2},
        "C00712": {"kegg_name": "Oleic acid", "kegg_formula": "C18H34O2", "kegg_exact_mass": 282.3},
    }
    FIND = {
        "Oleic acid": [{"cid": "C00712", "names": "Oleic acid"}],
        "Linoleic acid": [{"cid": "C01595", "names": "Linoleic acid"}],
    }
    def get_compound(self, cid):
        return dict(self.DB.get(cid.strip(),
                    {"kegg_name": None, "kegg_formula": None, "kegg_exact_mass": None}))
    def find_by_name(self, name):
        return [dict(h) for h in self.FIND.get(name.strip(), [])]


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    assert cond, f"FAILED: {label}"


print("1) pure functions")
check("normalize 'C5 H13 N O' -> C5H13NO", normalize_formula("C5 H13 N O") == "C5H13NO")
check("normalize drops trailing 1 (C1H4->CH4)", normalize_formula("C1 H4") == "CH4")
check("clean_name splits ';'", clean_name("Choline; Phthalic anhydride") == ["Choline", "Phthalic anhydride"])
check("is_lipid PC(18:1/0:0)", is_lipid_species("PC(18:1/0:0)") is True)
check("is_lipid Choline == False", is_lipid_species("Choline") is False)

print("\n2) map_one_compound paths (via map_dataframe)")
client = FakeKeggClient()

# pos: Choline มี KEGG ID -> verify (KEGG formula C5H14NO vs input C5H13NO = charge diff)
# Oleic acid ไม่มี KEGG ID -> find -> C00712
df_pos = pd.DataFrame([
    {"NO": 1, "Name": "Choline", "Formula": "C5 H13 N O", "KEGG ID": "C00114"},
    {"NO": 2, "Name": "PC(18:1/0:0)", "Formula": "C26 H52 N O7 P", "KEGG ID": None},
    {"NO": 3, "Name": "Oleic acid", "Formula": "C18 H34 O2", "KEGG ID": None},
])
res_pos = map_dataframe(df_pos, "pos", client)
choline = res_pos[res_pos["Input_Name"] == "Choline"].iloc[0]
check("Choline verified (has KEGG ID)", choline["Mapped_KEGG_ID"] == "C00114")
check("Choline charge diff detected", choline["Confidence"] == "charge_diff")
lipid = res_pos[res_pos["Input_Name"] == "PC(18:1/0:0)"].iloc[0]
check("PC lipid skipped", lipid["Confidence"] == "not_in_KEGG")
oleic = res_pos[res_pos["Input_Name"] == "Oleic acid"].iloc[0]
check("Oleic acid found via name", oleic["Mapped_KEGG_ID"] == "C00712" and oleic["Confidence"] == "found_high")

print("\n3) merge_and_dedupe (Oleic acid in both pos+neg -> 1 row)")
df_neg = pd.DataFrame([
    {"NO": 1, "Name": "Oleic acid", "Formula": "C18 H34 O2", "KEGG ID": None},
    {"NO": 2, "Name": "Linoleic acid", "Formula": "C18 H32 O2", "KEGG ID": "C01595"},
])
res_neg = map_dataframe(df_neg, "neg", client)
merged = merge_and_dedupe(res_pos, res_neg)
oleic_rows = merged[merged["Mapped_KEGG_ID"] == "C00712"]
check("Oleic acid deduped to 1 row", len(oleic_rows) == 1)
check("Oleic acid Mode = pos;neg", oleic_rows.iloc[0]["Mode"] == "pos;neg")
final = finalize(merged)
check("finalize produces all output columns", list(final.columns) == core.config.OUTPUT_COLUMNS)

print("\n4) load_and_validate rejects missing columns")
bad = pd.DataFrame([{"NO": 1, "WrongCol": "x"}])
bad_path = "/tmp/bad.xlsx"
bad.to_excel(bad_path, sheet_name="Compounds", index=False)
try:
    load_and_validate(bad_path)
    check("should have raised", False)
except MissingColumnsError as e:
    check("MissingColumnsError raised with column info", "Name" in str(e))

print("\nALL SMOKE TESTS PASSED ✓")
