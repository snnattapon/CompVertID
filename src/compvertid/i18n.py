"""
i18n.py — ระบบข้อความสองภาษา (internationalization) ของ CompVertID

หลักการ:
- รวมข้อความที่ผู้ใช้เห็นทั้งหมดไว้ที่เดียว แยกตาม "กุญแจ" (key) ที่สื่อความหมาย
- โค้ด (GUI/CLI) เรียกผ่าน t(key, lang) แทนการฝังข้อความตรง ๆ
- เพิ่ม/ถอดภาษาได้โดยแก้ที่ไฟล์นี้ไฟล์เดียว ไม่ต้องแตะ gui.py

การตั้งชื่อ key: ใช้ชื่อที่สื่อ "หน้าที่" ไม่ผูกกับภาษา (button.run ไม่ใช่ button.thai_run)
→ อนาคตถ้าถอดภาษาไทยออก key เดิมยังใช้ต่อได้ทันที

ข้อความที่มีตัวแปรแทรก ใช้รูปแบบ {name} แล้วเรียก .format(name=...) ที่จุดใช้งาน
→ แต่ละภาษาจัดตำแหน่ง/ถ้อยคำรอบตัวแปรได้อิสระ

ค่า default = "en" (มาตรฐานโปรเจกต์ open-source); ผู้ใช้สลับเป็น "th" ได้ใน GUI
"""

# ภาษาที่รองรับ (โค้ดสั้นมาตรฐาน ISO 639-1)
SUPPORTED_LANGS = ("en", "th")

# ภาษาเริ่มต้นเมื่อเปิดโปรแกรม
DEFAULT_LANG = "en"

# ชื่อภาษาที่แสดงใน dropdown (ให้ผู้ใช้เห็นเป็นชื่อภาษานั้น ๆ เอง)
LANG_DISPLAY_NAMES = {
    "en": "English",
    "th": "ไทย",
}


TRANSLATIONS = {
    # ==============================================================
    # English (ภาษาเริ่มต้น)
    # ==============================================================
    "en": {
        # ---- หน้าต่าง ----
        "window.title": "CompVertID v{version}",

        # ---- ป้ายเลือกภาษา ----
        "lang.label": "Language:",

        # ---- ส่วนไฟล์ข้อมูลเข้า ----
        "input.frame": "Input files — from the same experiment/project only",
        "input.warn.line1": "⚠  Use only two files from the same experiment (positive + negative mode of the same sample set)",
        "input.warn.line2": "Do not mix files from different projects — results are merged and deduplicated as if from one experiment, which contaminates the data",
        "input.pos_label": "Positive mode (single file):",
        "input.neg_label": "Negative mode (single file):",
        "input.hint": "Supported: Excel from Compound Discoverer (.xlsx) or compound name list (.txt/.csv)",

        # ---- ส่วนไฟล์ผลลัพธ์ ----
        "output.frame": "Output file",
        "output.save_as": "Save as:",

        # ---- ตัวเลือก ----
        "option.debug": "Debug mode (log details of problematic compounds — enable when sending logs to the developer)",

        # ---- ปุ่ม ----
        "button.run": "Run",
        "button.select_file": "Select file...",
        "button.select_output": "Choose location...",
        "button.open_output": "Open results folder",
        "button.open_log": "Open log folder",

        # ---- หัวตาราง (ตรงกับชื่อคอลัมน์ output; ปกติคงไว้เป็นอังกฤษทั้งสองภาษา) ----
        "table.mode": "Mode",
        "table.input_name": "Input_Name",
        "table.mapped_kegg_id": "Mapped_KEGG_ID",
        "table.kegg_formula": "KEGG_Formula",
        "table.confidence": "Confidence",
        "table.frame": "Results",

        # ---- file dialog ----
        "dialog.pick_input.title": "Select data file",
        "dialog.pick_output.title": "Save results as",

        # ---- ชนิดไฟล์ใน dialog ----
        "filetype.supported": "Supported files",
        "filetype.cd": "Compound Discoverer (Excel)",
        "filetype.list": "Compound list (Text/CSV)",
        "filetype.all": "All files",
        "filetype.excel": "Excel",

        # ---- messagebox ----
        "msg.no_input.title": "No file selected",
        "msg.no_input.body": "Please select at least one input data file",
        "msg.no_output.title": "No save location",
        "msg.no_output.body": "Please specify an output file",
        "msg.error.title": "Error",
        "msg.error.body": "{msg}\n\nDetails have been saved to the log.\nIf you need help, you can send the log file to the developer.",

        # ---- สถานะ (บางอันแทรกตัวแปร) ----
        "status.ready": "Ready — select files and click Run",
        "status.reading": "Reading file {name} ...",
        "status.processing": "Processing {current}/{total}: {name}",
        "status.merging": "Merging results and removing duplicates ...",
        "status.network_error": "Network problem: {msg}",
        "status.done": "Done! {n} rows — saved to {name}",
        "status.error": "An error occurred — see the log for details",

        # ---- error ที่ประกอบข้อความ ----
        "error.generic": "An error occurred: {msg}",
    },

    # ==============================================================
    # ไทย
    # ==============================================================
    "th": {
        # ---- หน้าต่าง ----
        "window.title": "CompVertID v{version}",

        # ---- ป้ายเลือกภาษา ----
        "lang.label": "ภาษา:",

        # ---- ส่วนไฟล์ข้อมูลเข้า ----
        "input.frame": "ไฟล์ข้อมูลเข้า — จากการทดลอง/โปรเจกต์เดียวกันเท่านั้น",
        "input.warn.line1": "⚠  ใส่ได้เฉพาะสองไฟล์ของการทดลองเดียวกัน (positive + negative mode ของตัวอย่างชุดเดียวกัน)",
        "input.warn.line2": "อย่านำไฟล์จากคนละโปรเจกต์มารันพร้อมกัน — ผลจะถูกรวมและตัดซ้ำเหมือนเป็นการทดลองเดียว ทำให้ข้อมูลปนกัน",
        "input.pos_label": "Positive mode (ไฟล์เดียว):",
        "input.neg_label": "Negative mode (ไฟล์เดียว):",
        "input.hint": "รองรับ: ไฟล์ Excel จาก Compound Discoverer (.xlsx) หรือ รายชื่อสาร (.txt/.csv)",

        # ---- ส่วนไฟล์ผลลัพธ์ ----
        "output.frame": "ไฟล์ผลลัพธ์",
        "output.save_as": "บันทึกเป็น:",

        # ---- ตัวเลือก ----
        "option.debug": "โหมด Debug (บันทึกรายละเอียดสารที่มีปัญหาลง log — เปิดเมื่อจะส่ง log ให้ผู้พัฒนา)",

        # ---- ปุ่ม ----
        "button.run": "เริ่มทำงาน (Run)",
        "button.select_file": "เลือกไฟล์...",
        "button.select_output": "เลือกที่เก็บ...",
        "button.open_output": "เปิดโฟลเดอร์ผลลัพธ์",
        "button.open_log": "เปิดโฟลเดอร์ log",

        # ---- หัวตาราง (คงชื่อคอลัมน์เป็นอังกฤษให้ตรงกับไฟล์ output) ----
        "table.mode": "Mode",
        "table.input_name": "Input_Name",
        "table.mapped_kegg_id": "Mapped_KEGG_ID",
        "table.kegg_formula": "KEGG_Formula",
        "table.confidence": "Confidence",
        "table.frame": "ผลลัพธ์",

        # ---- file dialog ----
        "dialog.pick_input.title": "เลือกไฟล์ข้อมูล",
        "dialog.pick_output.title": "บันทึกผลลัพธ์เป็น",

        # ---- ชนิดไฟล์ใน dialog ----
        "filetype.supported": "ไฟล์ที่รองรับ",
        "filetype.cd": "Compound Discoverer (Excel)",
        "filetype.list": "รายชื่อสาร (Text/CSV)",
        "filetype.all": "ทุกไฟล์",
        "filetype.excel": "Excel",

        # ---- messagebox ----
        "msg.no_input.title": "ยังไม่ได้เลือกไฟล์",
        "msg.no_input.body": "กรุณาเลือกไฟล์ข้อมูลเข้าอย่างน้อยหนึ่งไฟล์",
        "msg.no_output.title": "ยังไม่ได้เลือกที่บันทึก",
        "msg.no_output.body": "กรุณาระบุไฟล์ผลลัพธ์",
        "msg.error.title": "เกิดข้อผิดพลาด",
        "msg.error.body": "{msg}\n\nรายละเอียดถูกบันทึกไว้ใน log แล้ว\nหากต้องการความช่วยเหลือ ส่งไฟล์ log ให้ผู้พัฒนาตรวจสอบได้",

        # ---- สถานะ (บางอันแทรกตัวแปร) ----
        "status.ready": "พร้อมทำงาน — เลือกไฟล์แล้วกด Run",
        "status.reading": "กำลังอ่านไฟล์ {name} ...",
        "status.processing": "กำลังประมวลผล {current}/{total}: {name}",
        "status.merging": "กำลังรวมผลและตัดข้อมูลซ้ำ ...",
        "status.network_error": "เครือข่ายมีปัญหา: {msg}",
        "status.done": "เสร็จแล้ว! ได้ผล {n} แถว — บันทึกที่ {name}",
        "status.error": "มีข้อผิดพลาด — ดูรายละเอียดใน log",

        # ---- error ที่ประกอบข้อความ ----
        "error.generic": "เกิดข้อผิดพลาด: {msg}",
    },
}


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """
    ดึงข้อความตาม key และภาษา แล้วเติมตัวแปร (ถ้ามี) ผ่าน .format()

    t("button.run")                         -> "Run"
    t("button.run", "th")                   -> "เริ่มทำงาน (Run)"
    t("status.reading", "th", name="a.xlsx")-> "กำลังอ่านไฟล์ a.xlsx ..."

    ถ้าไม่พบภาษา → ถอยไปใช้ DEFAULT_LANG
    ถ้าไม่พบ key → คืน key นั้นกลับไปตรง ๆ (ช่วยให้เห็นทันทีว่าลืมแปล key ไหน)
    ถ้าตัวแปรที่ format ขาด → คืนข้อความดิบ (ยังไม่ format) แทนที่จะ crash
    """
    lang_table = TRANSLATIONS.get(lang) or TRANSLATIONS.get(DEFAULT_LANG, {})
    template = lang_table.get(key)

    if template is None:
        # ถอยไปหาใน default ก่อน เผื่อภาษาปัจจุบันแปลไม่ครบ
        template = TRANSLATIONS.get(DEFAULT_LANG, {}).get(key, key)

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def available_languages() -> list[tuple[str, str]]:
    """
    คืนรายการภาษาที่รองรับเป็น [(code, display_name), ...]
    ให้ GUI เอาไปใส่ dropdown ได้ทันที
    """
    return [(code, LANG_DISPLAY_NAMES.get(code, code)) for code in SUPPORTED_LANGS]


def display_to_code(display_name: str) -> str:
    """
    แปลงชื่อภาษาที่แสดง (เช่น "ไทย") กลับเป็น code ("th")
    ใช้ตอนอ่านค่าที่ผู้ใช้เลือกจาก dropdown
    ถ้าไม่ตรงกับอันไหน → คืน DEFAULT_LANG
    """
    for code, name in LANG_DISPLAY_NAMES.items():
        if name == display_name:
            return code
    return DEFAULT_LANG
