"""
launcher.py — entry point สำหรับ PyInstaller (.app / .exe)

ทำไมต้องมีไฟล์นี้:
    PyInstaller เรียกไฟล์ entry แบบ "สคริปต์เดี่ยว" ทำให้ relative import
    ใน gui.py (เช่น `from . import config`) พังด้วย
    "ImportError: attempted relative import with no known parent package"

    ไฟล์นี้ import gui ในฐานะส่วนหนึ่งของ package `compvertid` (absolute import)
    แล้วเรียก main() — บริบทของ package จึงครบ relative import ข้างในทำงานปกติ
"""
from compvertid.gui import main

if __name__ == "__main__":
    main()
