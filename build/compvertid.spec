# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — build GUI เป็นไฟล์เดียว (--onefile)

ใช้ได้ทั้ง Windows และ macOS (PyInstaller เลือก format ตาม OS ที่ build ให้เอง)
สร้างจาก entry point ของ GUI: src/compvertid/gui.py

build ด้วย:
    pyinstaller build/compvertid.spec

หมายเหตุ: ต้อง build บน OS เป้าหมายจริง (PyInstaller cross-compile ข้าม OS ไม่ได้)
- .exe  -> build บน Windows
- .app  -> build บน macOS
"""
import sys
from pathlib import Path

# To read __version__ from src without importing the whole package (avoid dependency while building)
_init = Path(SPECPATH).parent / "src" / "compvertid" / "__init__.py"
_version_line = next(
    ln for ln in _init.read_text(encoding="utf-8").splitlines()
    if ln.strip().startswith("__version__")
)
app_version = _version_line.split("=")[1].strip().strip('"').strip("'")

# ชื่อ executable ต่อ OS
app_name = "CompVertID"

block_cipher = None

a = Analysis(
    ["../src/compvertid/gui.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    # pandas/openpyxl/tkinter บางส่วนถูกโหลดแบบ dynamic — ระบุให้ PyInstaller เก็บครบ
    hiddenimports=[
        "openpyxl",
        "openpyxl.cell._writer",
        "pandas._libs.tslibs.base",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # ตัด module ที่ไม่ใช้ออก ลดขนาดไฟล์
    excludes=[
        "matplotlib", "scipy", "PyQt5", "PyQt6", "PySide2", "PySide6",
        "IPython", "jupyter", "notebook", "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI app — ไม่เปิดหน้าต่าง console
    disable_windowed_traceback=False,
    argv_emulation=True,    # macOS: ให้เปิดไฟล์ที่ลากมาวางบนไอคอนได้
    target_arch=None,       # ให้ตรงกับ arch ของเครื่อง build (arm64/x86_64)
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # ใส่ path ไอคอนภายหลังได้ (.ico บน Win, .icns บน Mac)
)

# บน macOS: ห่อเป็น .app bundle ด้วย
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{app_name}.app",
        icon=None,
        bundle_identifier="org.compvertid.app",
        info_plist={
            "NSHighResolutionCapable": "True",
            "CFBundleShortVersionString": app_version,
        },
    )
