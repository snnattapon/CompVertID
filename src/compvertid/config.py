"""
config.py — ค่าคงที่ทั้งหมดของ CompVertID รวมไว้ที่เดียว

แก้ค่าที่นี่ที่เดียว แล้วมีผลทั้ง core, CLI และ GUI
(เดิมค่าเหล่านี้กระจายอยู่ในสคริปต์หลัก ทำให้แก้ยากและ hard-code)
"""

# ------------------------------------------------------------------
# KEGG REST API
# ------------------------------------------------------------------
KEGG_BASE = "https://rest.kegg.jp"

# หน่วงเวลาระหว่างการเรียก API (วินาที) — อย่ายิงถี่เกินไป ถนอม KEGG server
API_DELAY = 0.35

# timeout ต่อ 1 request (วินาที)
API_TIMEOUT = 15

# จำนวนครั้งที่ retry เมื่อเรียก API ล้มเหลว (network error / timeout)
API_MAX_RETRIES = 3

# หน่วงเวลาก่อน retry (วินาที) — จะคูณเพิ่มแบบ backoff ในแต่ละรอบ
API_RETRY_BACKOFF = 1.0

# ------------------------------------------------------------------
# ชื่อ sheet และคอลัมน์ที่จำเป็นในไฟล์ input
# ------------------------------------------------------------------
SHEET_NAME = "Compounds"

# คอลัมน์ที่ core ใช้จริง (มีแค่ 4 ตัวจาก 202 คอลัมน์)
# ถ้าไฟล์ผู้ใช้ไม่มีคอลัมน์เหล่านี้ จะแจ้ง error ที่อ่านเข้าใจได้ แทนการ crash
COL_NAME = "Name"
COL_FORMULA = "Formula"
COL_KEGG_ID = "KEGG ID"
COL_NO = "NO"  # ใช้เป็น row number อ้างอิง (ถ้าไม่มีจะ fallback เป็น index)

# คอลัมน์ที่ต้องมีจริง ๆ ถึงจะ map ได้ (NO เป็น optional)
REQUIRED_COLUMNS = [COL_NAME, COL_FORMULA, COL_KEGG_ID]

# ------------------------------------------------------------------
# ชื่อคอลัมน์ output
# ------------------------------------------------------------------
OUTPUT_COLUMNS = [
    "Mode", "Row_NO", "Input_Name", "Input_Formula", "Original_KEGG_ID",
    "Mapped_KEGG_ID", "KEGG_Name", "KEGG_Formula",
    "Formula_Match", "Confidence", "Notes",
]

# ------------------------------------------------------------------
# Lipid species notation ที่ KEGG ไม่ครอบคลุม
# ------------------------------------------------------------------
LIPID_PREFIXES = [
    "PC", "LPC", "PE", "LPE", "PG", "LPG", "PI", "LPI",
    "PS", "LPS", "PA", "LPA", "TG", "DG", "MG", "CE", "Cer", "SM", "CL",
]

# ------------------------------------------------------------------
# ลำดับความสำคัญของ Confidence (เลขน้อย = ดีกว่า) ใช้ตอน dedupe เลือกแถวที่เก็บ
# ------------------------------------------------------------------
CONFIDENCE_PRIORITY = {
    "verified_high": 1,
    "found_high": 2,
    "verified_no_formula": 3,
    "found_no_formula_check": 4,
    "name_match_verify": 4.5,  # ชื่อตรงเป๊ะ แต่ยังไม่ได้ยืนยันด้วย formula
    "charge_diff": 5,          # ต่างแค่ charge/H — ผลยังน่าเชื่อ
    "ambiguous": 6,
    "formula_mismatch": 7,     # ต่างที่ backbone — อาจคนละสาร
    "low": 8,
    "not_found": 9,
    "not_in_KEGG": 10,
    "no_name": 11,
}

# ลำดับการ sort ตาม Mode ในผลลัพธ์สุดท้าย
MODE_SORT_ORDER = {"pos": 1, "pos;neg": 2, "neg": 3}

# ------------------------------------------------------------------
# การจัดกลุ่มสีของ Confidence สำหรับแสดงผล (GUI หยิบไปใช้กำหนดสีแถว/ป้าย)
# green  = เชื่อได้         · yellow = น่าเชื่อ แต่ระวัง
# orange = ต้องตรวจเอง      · gray   = ปกติของข้อมูล (ไม่เจอ/ข้าม/ไม่มีชื่อ)
# ------------------------------------------------------------------
CONFIDENCE_COLOR_GROUP = {
    "verified_high": "green",
    "found_high": "green",
    "verified_no_formula": "yellow",
    "found_no_formula_check": "yellow",
    "name_match_verify": "yellow",
    "charge_diff": "yellow",
    "ambiguous": "orange",
    "formula_mismatch": "orange",
    "low": "orange",
    "not_found": "gray",
    "not_in_KEGG": "gray",
    "no_name": "gray",
}

# ค่าสี hex ของแต่ละกลุ่ม (ให้ GUI/Excel ใช้ตรงกัน)
COLOR_GROUP_HEX = {
    "green": "C6EFCE",   # เขียวอ่อน
    "yellow": "FFEB9C",  # เหลืองอ่อน
    "orange": "FFD9A0",  # ส้มอ่อน
    "gray": "E0E0E0",    # เทาอ่อน
}
