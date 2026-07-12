"""
false_alarm_analysis.py — รันทุกเคสที่ระบบจะ flag ได้ แล้วแยก true problem vs false alarm

ใช้ FakeKegg ที่ควบคุม DB เองทั้งหมด เพื่อจำลองทุกสถานการณ์ได้แม่นยำ
โดยไม่ต้องพึ่ง KEGG server จริง
"""
import sys
sys.path.insert(0, "../src")

import pandas as pd
from compvertid import map_dataframe


# ------------------------------------------------------------------
# Fake KEGG database — ออกแบบให้ทุกเคสเกิดขึ้นได้ตามต้องการ
# ------------------------------------------------------------------
class FakeKegg:
    COMPOUNDS = {
        # cid -> (name, formula)
        "C00114": ("Choline", "C5H14NO"),        # protonated form (input มัก C5H13NO)
        "C00031": ("D-Glucose", "C6H12O6"),
        "C00267": ("alpha-D-Glucose", "C6H12O6"),  # isomer สูตรเดียวกับ glucose
        "C00221": ("beta-D-Glucose", "C6H12O6"),   # isomer อีกตัว สูตรเดียวกัน
        "C01595": ("Linoleic acid", "C18H32O2"),
        "C00712": ("Oleic acid", "C18H34O2"),
        "C00025": ("L-Glutamate", "C5H9NO4"),
        "C99999": ("Weirdcompound", None),        # KEGG ไม่มีสูตร (เกิดขึ้นจริงได้)
    }
    # ชื่อ -> list ของ cid ที่ค้นเจอ
    FIND = {
        "choline": ["C00114"],
        "glucose": ["C00031", "C00267", "C00221"],  # ค้นเจอ 3 ตัว สูตรเดียวกันหมด
        "linoleic acid": ["C01595"],
        "oleic acid": ["C00712"],
        "glutamate": ["C00025"],
        "weirdcompound": ["C99999"],
        "aspirin": ["C01405", "C21332", "C07588"],   # เจอหลายตัว สูตรต่างกัน
    }
    FORMULA_FOR_MULTI = {
        "C01405": "C9H8O4", "C21332": "C9H9O4", "C07588": "C9H8O4Na",
    }

    def get_compound(self, cid):
        cid = cid.strip()
        if cid in self.COMPOUNDS:
            name, formula = self.COMPOUNDS[cid]
            return {"kegg_name": name, "kegg_formula": formula, "kegg_exact_mass": None}
        if cid in self.FORMULA_FOR_MULTI:
            return {"kegg_name": cid, "kegg_formula": self.FORMULA_FOR_MULTI[cid], "kegg_exact_mass": None}
        return {"kegg_name": None, "kegg_formula": None, "kegg_exact_mass": None}

    def find_by_name(self, name):
        cids = self.FIND.get(name.strip().lower(), [])
        return [{"cid": c, "names": c} for c in cids]


# ------------------------------------------------------------------
# Input: จงใจใส่ทุกเคส
# ------------------------------------------------------------------
rows = [
    # (Name, Formula, KEGG ID, คำอธิบายเคส)
    ("Choline", "C5 H14 N O", "C00114", "A) มี KEGG ID สูตรตรงเป๊ะ"),
    ("Choline", "C5 H13 N O", "C00114", "B) มี KEGG ID สูตรต่าง H+1 (charge)"),
    ("WrongLink", "C3 H4", "C00025", "B2) มี KEGG ID แต่สูตรต่างที่ backbone (คนละสาร)"),
    ("L-Glutamate", "C5 H9 N O4", "C00025", "C) หาเจอจากชื่อ สูตรตรง"),
    ("Oleic acid", "C18 H34 O2", None, "D) ไม่มี ID หาเจอตัวเดียว สูตรตรง"),
    ("Glucose", "C6 H12 O6", None, "E) หาเจอ 3 ตัว สูตรตรงหมด (isomer)"),
    ("Aspirin", "C9 H8 O4", None, "F) หาเจอหลายตัว กรองด้วยสูตรเหลือ 1"),
    ("Aspirin", "C99 H99", None, "G) หาเจอหลายตัว แต่สูตรไม่ตรงสักตัว"),
    ("Weirdcompound", "C10 H10", None, "H) หาเจอ แต่ KEGG ไม่มีสูตรให้เทียบ"),
    ("Choline", "", "C00114", "I) มี KEGG ID แต่ input ไม่มีสูตร"),
    ("PC(18:1/0:0)", "C26 H52 N O7 P", None, "J) lipid species (ข้าม)"),
    ("NonExistentXYZ", "C4 H4", None, "K) หาไม่เจอเลย"),
    ("", "C4 H4", None, "L) ไม่มีชื่อเลย"),
    ("Choline; Glucose", "C6 H12 O6", None, "M) หลายชื่อคั่น ; (ชื่อแรกกับสองคนละสาร)"),
]

df = pd.DataFrame([{"NO": i + 1, "Name": n, "Formula": f, "KEGG ID": k}
                   for i, (n, f, k, _) in enumerate(rows)])
descs = {i + 1: d for i, (_, _, _, d) in enumerate(rows)}

res = map_dataframe(df, "pos", FakeKegg())

# ------------------------------------------------------------------
# จำแนกว่าแต่ละผลเป็น true problem หรือ false alarm หรือ OK
# ------------------------------------------------------------------
CLASSIFY = {
    "verified_high":          ("OK",          "ผลถูก ไม่ต้องดู"),
    "found_high":             ("OK",          "ผลถูก ไม่ต้องดู"),
    "verified_no_formula":    ("FALSE ALARM", "ผลน่าจะถูก แค่ไม่มีสูตรยืนยัน"),
    "found_no_formula_check": ("FALSE ALARM", "ผลน่าจะถูก แค่ไม่มีสูตรยืนยัน"),
    "charge_diff":            ("FALSE ALARM", "ต่างแค่ charge/H — ผลยังน่าเชื่อ"),
    "ambiguous":              ("TRUE PROBLEM","เจอหลายตัวสูตรตรงหมด ต้องเลือกเอง"),
    "formula_mismatch":       ("TRUE PROBLEM","สูตรต่างที่ backbone — อาจคนละสาร"),
    "low":                    ("TRUE PROBLEM","เจอแต่สูตรไม่ตรงเลย น่าสงสัย"),
    "not_found":              ("EXPECTED",    "ไม่เจอจริง — ปกติของข้อมูล"),
    "not_in_KEGG":            ("EXPECTED",    "lipid/สารที่ KEGG ไม่ครอบคลุม — ปกติ"),
    "no_name":                ("INPUT ISSUE", "ไฟล์ input มีปัญหา (ไม่มีชื่อ)"),
}

print("=" * 110)
print(f"{'เคส':<48} {'Confidence':<24} {'ประเภท':<14} Mapped")
print("=" * 110)
for _, r in res.iterrows():
    no = r["Row_NO"]
    conf = r["Confidence"]
    kind, _explain = CLASSIFY.get(conf, ("?", "?"))
    mapped = str(r["Mapped_KEGG_ID"])[:22]
    print(f"{descs[no]:<48} {conf:<24} {kind:<14} {mapped}")

print("\n" + "=" * 110)
print("รายละเอียด Notes ของเคสที่ต้องดู (DEPENDS / TRUE PROBLEM / ambiguous):")
print("=" * 110)
for _, r in res.iterrows():
    if r["Confidence"] in ("charge_diff", "formula_mismatch", "ambiguous", "low"):
        print(f"\n[{descs[r['Row_NO']]}]")
        print(f"  Mapped: {r['Mapped_KEGG_ID']}")
        print(f"  Notes : {r['Notes']}")
