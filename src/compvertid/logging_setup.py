"""
logging_setup.py — ระบบ log ที่ออกแบบเพื่อ debug ง่ายและเคารพ privacy

ปรัชญา: ผู้ใช้รันแล้วได้ log file หนึ่งไฟล์ต่อการรัน ถ้าเจอปัญหาก็ส่งไฟล์นั้น
        กลับมาให้ผู้พัฒนาตรวจสอบ — ไม่มีการส่งข้อมูลอัตโนมัติใด ๆ (no telemetry)
        ผู้ใช้เห็นได้เองว่าจะแชร์อะไร ก่อนกดส่ง

ที่เก็บ log:
- หลัก: โฟลเดอร์เดียวกับไฟล์ผลลัพธ์ (ผู้ใช้เพิ่งเลือกเอง รู้ว่าอยู่ไหน เขียนได้แน่)
- fallback: โฟลเดอร์มาตรฐานของ OS ผ่าน platformdirs (กรณีไม่ได้ระบุ output
  หรือโฟลเดอร์นั้นเขียนไม่ได้)

ระดับ log:
- INFO : เหตุการณ์ทั่วไป (เริ่ม/จบ, จำนวนแถว, เวอร์ชัน, OS, สถิติ API) — ปลอดภัยเสมอ
- ERROR: traceback เต็ม + บริบท — เสมอเมื่อเกิด error
- DEBUG: ชื่อ/สูตรของ compound เฉพาะตัวที่มีปัญหา — opt-in เท่านั้น (ปิดเป็น default)

Privacy: โหมดปกติ (ไม่เปิด debug) log จะไม่มีชื่อ compound เลย มีแต่ตัวเลข/เหตุการณ์
"""

import logging
import platform
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs

from . import __version__, config


LOGGER_NAME = "compvertid"

# ขนาดสูงสุดต่อไฟล์ log และจำนวน backup (rotation กันไฟล์บวมเต็มเครื่อง)
_MAX_BYTES = 2 * 1024 * 1024   # 2 MB ต่อไฟล์
_BACKUP_COUNT = 3              # เก็บย้อนหลัง 3 ไฟล์

# ชื่อแอปสำหรับ platformdirs (ใช้กำหนดโฟลเดอร์มาตรฐาน OS)
_APP_NAME = "CompVertID"

# header อธิบาย privacy — เขียนไว้ต้นไฟล์ทุกครั้ง ให้ผู้ใช้เปิดอ่านก่อนส่ง
_PRIVACY_HEADER = """\
# ============================================================================
# CompVertID — Log File
# ============================================================================
# ไฟล์นี้บันทึกการทำงานของโปรแกรมไว้ เพื่อช่วยตรวจหาปัญหาเมื่อเกิดข้อผิดพลาด
#
# ไฟล์นี้เก็บอะไรบ้าง:
#   - เวลาเริ่ม/จบการทำงาน, จำนวนแถวที่อ่านได้
#   - เวอร์ชันโปรแกรม, ระบบปฏิบัติการ, เวอร์ชัน Python
#   - สถิติการเรียก KEGG API (จำนวนครั้ง สำเร็จ/ล้มเหลว) — เป็นตัวเลขเท่านั้น
#   - ข้อความ error (ถ้ามี)
#
# ไฟล์นี้ "ไม่" เก็บชื่อหรือสูตรของสารประกอบ เว้นแต่คุณเปิดโหมด debug เอง
#   (--debug ใน command line หรือ ติ๊ก "Debug mode" ใน GUI)
#   ซึ่งจะบันทึกรายละเอียดเฉพาะสารที่มีปัญหา เพื่อช่วย debug
#
# หากจะส่งไฟล์นี้ให้ผู้พัฒนาตรวจสอบ แนะนำให้เปิดอ่านก่อน เพื่อความสบายใจ
# ============================================================================

"""


def _resolve_log_dir(output_path=None) -> Path:
    """
    เลือกโฟลเดอร์เก็บ log:
    1. ถ้ามี output_path และโฟลเดอร์ของมันเขียนได้ -> ใช้โฟลเดอร์เดียวกับ output
    2. ไม่งั้น -> โฟลเดอร์มาตรฐาน OS ผ่าน platformdirs
    คืน Path ของโฟลเดอร์ (สร้างให้แล้ว)
    """
    if output_path is not None:
        out_dir = Path(output_path).expanduser().resolve().parent
        if _is_writable(out_dir):
            return out_dir

    # fallback: โฟลเดอร์ log มาตรฐานของ OS
    #   Windows: %LOCALAPPDATA%\CompVertID\Logs
    #   macOS  : ~/Library/Logs/CompVertID
    #   Linux  : ~/.local/state/CompVertID/log (หรือใกล้เคียง)
    fallback = Path(platformdirs.user_log_dir(_APP_NAME))
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _is_writable(directory: Path) -> bool:
    """ตรวจว่าโฟลเดอร์เขียนได้จริง (เผื่อกรณี Program Files ที่ freeze .exe ไปวาง)"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        testfile = directory / ".kegg_write_test"
        testfile.write_text("ok", encoding="utf-8")
        testfile.unlink()
        return True
    except (OSError, PermissionError):
        return False


def setup_logging(output_path=None, debug: bool = False) -> tuple[logging.Logger, Path]:
    """
    ตั้งค่า logger สำหรับการรันหนึ่งครั้ง

    output_path: path ไฟล์ผลลัพธ์ (เอาไว้หาโฟลเดอร์เก็บ log ข้าง ๆ) หรือ None
    debug: True = เปิด DEBUG (log รายละเอียด compound ที่มีปัญหา), False = ปกติ

    คืน (logger, log_file_path)
    """
    log_dir = _resolve_log_dir(output_path)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = log_dir / f"compvertid_run_{timestamp}.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # ล้าง handler เดิม (กันซ้ำเมื่อเรียกหลายครั้งในโปรเซสเดียว เช่นใน GUI)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    # เขียน privacy header ก่อน (ใช้ไฟล์ปกติ ไม่ผ่าน handler เพื่อให้อยู่บนสุดเสมอ)
    log_file.write_text(_PRIVACY_HEADER, encoding="utf-8")

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ไฟล์ log พร้อม rotation (append ต่อจาก header)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # บันทึกข้อมูลสภาพแวดล้อมทันที (ปลอดภัยเสมอ ช่วย debug ปัญหา env/version มากที่สุด)
    logger.info(f"=== CompVertID v{__version__} ===")
    logger.info(f"Platform : {platform.platform()}")
    logger.info(f"Python   : {platform.python_version()}")
    try:
        import pandas as pd
        logger.info(f"pandas   : {pd.__version__}")
    except Exception:
        pass
    logger.info(f"Debug mode: {'ON (compound details will be logged)' if debug else 'OFF'}")
    logger.info(f"Log file : {log_file}")

    return logger, log_file


def get_logger() -> logging.Logger:
    """ดึง logger ตัวเดียวกันจากที่อื่นในโปรแกรม (หลังเรียก setup_logging แล้ว)"""
    return logging.getLogger(LOGGER_NAME)


def log_problem_compound(logger: logging.Logger, mode: str, row_no, name, formula, reason: str):
    """
    log รายละเอียดของ compound ที่มีปัญหา — จะปรากฏก็ต่อเมื่อเปิด debug เท่านั้น
    (ระดับ DEBUG; โหมดปกติ logger ตั้ง level ไว้ที่ INFO จึงถูกกรองทิ้ง)

    ใช้กับเฉพาะแถวที่ map ไม่ได้/ผลแปลก ไม่ใช่ dump ทั้งไฟล์ →
    เปิดเผยข้อมูลน้อยที่สุดเท่าที่จำเป็นต่อการ debug
    """
    logger.debug(f"[problem] mode={mode} row={row_no} name={name!r} formula={formula!r} reason={reason}")
