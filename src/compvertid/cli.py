"""
cli.py — ทางเข้าแบบ command line

ผูก pipeline ทั้งหมดเข้าด้วยกัน: load_input -> map_dataframe -> merge_and_dedupe
-> finalize -> เขียน Excel ออก

ชั้นนี้เป็นที่เดียวที่ "พูด" (print / progress bar) — core ยังคงสะอาด
tqdm ถูกเสียบผ่าน progress_callback ที่ core เตรียมไว้ให้

ตัวอย่างการใช้:
    # ไฟล์ Compound Discoverer สองโหมด
    compvertid --pos compounds_pos_raw.xlsx --neg compounds_neg_raw.xlsx -o results.xlsx

    # ไฟล์รายชื่อจาก NMR (โหมดเดียว)
    compvertid --pos my_compounds.txt -o results.xlsx

    # ระบุโหมดชัด ๆ ด้วย --input + --mode
    compvertid --input list.csv --mode pos -o results.xlsx
"""

import argparse
import sys
from pathlib import Path

from . import __version__, config
from .kegg_api import KeggClient
from .input_loader import load_input, UnsupportedInputError
from .core import (
    map_dataframe,
    merge_and_dedupe,
    finalize,
    MissingColumnsError,
)
from .logging_setup import setup_logging, log_problem_compound

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False


def _make_progress_callback(mode_tag: str, use_bar: bool):
    """
    สร้าง progress_callback สำหรับ core.map_dataframe
    ถ้ามี tqdm และเปิด bar ไว้ -> แสดง progress bar สวย ๆ
    ถ้าไม่มี -> พิมพ์เปอร์เซ็นต์เป็นระยะแทน
    """
    if use_bar and _HAS_TQDM:
        bar = {"pbar": None}

        def cb(current, total, name):
            if bar["pbar"] is None:
                bar["pbar"] = tqdm(total=total, desc=f"[{mode_tag.upper()}] Mapping", ncols=100)
            bar["pbar"].n = current
            bar["pbar"].set_postfix_str(name[:30])
            bar["pbar"].refresh()
            if current >= total:
                bar["pbar"].close()

        return cb
    else:
        def cb(current, total, name):
            if current == total or current % 25 == 0:
                pct = (current / total * 100) if total else 100
                print(f"  [{mode_tag.upper()}] {current}/{total} ({pct:.0f}%)")

        return cb


def _map_one_source(filepath, mode_tag, client, quiet):
    """โหลดไฟล์หนึ่ง + map + คืน DataFrame (จัดการ error ให้เป็นข้อความอ่านรู้เรื่อง)"""
    path = Path(filepath)
    if not path.exists():
        print(f"ไม่พบไฟล์: {filepath}", file=sys.stderr)
        return None

    if not quiet:
        print(f"\n{'='*60}\nProcessing {mode_tag.upper()}: {path.name}\n{'='*60}")

    try:
        df = load_input(filepath)
    except MissingColumnsError as e:
        print(f"ไฟล์ผิดรูปแบบ: {e}", file=sys.stderr)
        return None
    except UnsupportedInputError as e:
        print(f"นามสกุลไม่รองรับ: {e}", file=sys.stderr)
        return None

    if not quiet:
        print(f"   Found {len(df)} rows")

    cb = _make_progress_callback(mode_tag, use_bar=not quiet)
    return map_dataframe(df, mode_tag, client, progress_callback=cb)


# Confidence ที่ถือว่า "มีปัญหา" ควร log รายละเอียดตอน debug
_PROBLEM_CONFIDENCES = {
    "formula_mismatch", "ambiguous", "low", "not_found", "no_name",
}


def _log_problem_rows(logger, result_df, mode_tag):
    """log เฉพาะแถวที่ผลออกมามีปัญหา (เรียกเมื่อเปิด debug เท่านั้น)"""
    for _, r in result_df.iterrows():
        if r.get("Confidence") in _PROBLEM_CONFIDENCES:
            log_problem_compound(
                logger, mode_tag, r.get("Row_NO"),
                r.get("Input_Name"), r.get("Input_Formula"),
                f"{r.get('Confidence')} | {r.get('Notes')}",
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compvertid",
        description="Map compounds (Compound Discoverer xlsx หรือ รายชื่อ txt/csv) ไปยัง KEGG IDs",
    )
    p.add_argument("--pos", metavar="FILE", help="ไฟล์ positive mode (.xlsx/.txt/.csv)")
    p.add_argument("--neg", metavar="FILE", help="ไฟล์ negative mode (.xlsx/.txt/.csv)")
    p.add_argument("--input", metavar="FILE", help="ไฟล์เดียว (ใช้คู่กับ --mode)")
    p.add_argument("--mode", choices=["pos", "neg"], default="pos",
                   help="โหมดของ --input (ค่าเริ่มต้น: pos)")
    p.add_argument("-o", "--output", metavar="FILE", default="kegg_mapping_results.xlsx",
                   help="ไฟล์ผลลัพธ์ (ค่าเริ่มต้น: kegg_mapping_results.xlsx)")
    p.add_argument("--delay", type=float, default=config.API_DELAY,
                   help=f"หน่วงเวลาระหว่าง API call วินาที (ค่าเริ่มต้น: {config.API_DELAY})")
    p.add_argument("-q", "--quiet", action="store_true", help="ไม่แสดง progress bar")
    p.add_argument("--debug", action="store_true",
                   help="เปิดโหมด debug: log รายละเอียดสารที่มีปัญหา (สำหรับส่งให้ผู้พัฒนาตรวจสอบ)")
    p.add_argument("--version", action="version", version=f"compvertid {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # รวบรวมแหล่ง input เป็น (filepath, mode_tag)
    sources = []
    if args.input:
        sources.append((args.input, args.mode))
    if args.pos:
        sources.append((args.pos, "pos"))
    if args.neg:
        sources.append((args.neg, "neg"))

    if not sources:
        print("ต้องระบุ input อย่างน้อยหนึ่งไฟล์ (--pos / --neg / --input)", file=sys.stderr)
        return 2

    # ตั้งค่า logging (เก็บ log ข้างไฟล์ผลลัพธ์) — เรียกก่อนเริ่มงานจริง
    logger, log_file = setup_logging(output_path=args.output, debug=args.debug)
    if not args.quiet:
        print(f"บันทึก log ที่: {log_file}")

    def _on_network_error(msg):
        print(f"  [network] {msg}", file=sys.stderr)
        logger.error(f"Network: {msg}")

    client = KeggClient(delay=args.delay, on_network_error=_on_network_error)

    try:
        # map ทุกแหล่ง แยกตาม mode tag
        df_by_mode = {"pos": None, "neg": None}
        for filepath, mode_tag in sources:
            logger.info(f"Processing {mode_tag}: {Path(filepath).name}")
            result = _map_one_source(filepath, mode_tag, client, args.quiet)
            if result is None:
                logger.error(f"Failed to load/map source: {Path(filepath).name}")
                return 1
            logger.info(f"Mapped {len(result)} rows from {mode_tag} ({Path(filepath).name})")

            # log เฉพาะแถวที่มีปัญหา (ปรากฏเฉพาะเมื่อเปิด debug)
            if args.debug:
                _log_problem_rows(logger, result, mode_tag)

            if df_by_mode[mode_tag] is None:
                df_by_mode[mode_tag] = result
            else:
                import pandas as pd
                df_by_mode[mode_tag] = pd.concat([df_by_mode[mode_tag], result], ignore_index=True)

        # เตรียม pos/neg (เติม DataFrame ว่างถ้าขาดข้างใดข้างหนึ่ง)
        import pandas as pd
        df_pos = df_by_mode["pos"] if df_by_mode["pos"] is not None else pd.DataFrame(columns=config.OUTPUT_COLUMNS)
        df_neg = df_by_mode["neg"] if df_by_mode["neg"] is not None else pd.DataFrame(columns=config.OUTPUT_COLUMNS)

        if not args.quiet:
            print(f"\n{'='*60}\nMerge and Dedupe\n{'='*60}")
        info_cb = (lambda msg: (logger.info(msg), print(f"   {msg}"))) if not args.quiet \
            else (lambda msg: logger.info(msg))
        merged = merge_and_dedupe(df_pos, df_neg, info_callback=info_cb)
        final_df = finalize(merged)

        # เขียนผลออก
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        final_df.to_excel(out_path, sheet_name=config.SHEET_NAME, index=False)
        logger.info(f"Saved results to {out_path} ({len(final_df)} rows)")

        # สถิติ API ลง log เสมอ (เป็นตัวเลข ไม่มีชื่อ compound — ปลอดภัย)
        s = client.stats
        logger.info(
            f"KEGG API stats: compound_calls={s['compound_api_calls']} "
            f"cache_hits={s['compound_cache_hits']} "
            f"find_calls={s['find_api_calls']} find_cache_hits={s['find_cache_hits']} "
            f"network_errors={s['network_errors']}"
        )

        # สรุปหน้าจอ
        print(f"\nเสร็จแล้ว! บันทึกที่: {out_path}")
        if not args.quiet:
            print("\nสรุปตาม Mode:")
            print(final_df["Mode"].value_counts().to_string())
            print("\nสรุปตาม Confidence:")
            print(final_df["Confidence"].value_counts().to_string())
            print(f"\nสถิติ KEGG API: compound calls={s['compound_api_calls']} "
                  f"(cache hits={s['compound_cache_hits']}), "
                  f"find calls={s['find_api_calls']} (cache hits={s['find_cache_hits']}), "
                  f"network errors={s['network_errors']}")
            print(f"\nLog: {log_file}")

        return 0

    except Exception:
        # จับทุก error ที่ไม่คาดคิด ลง log พร้อม traceback เต็ม แล้วแจ้งผู้ใช้ให้ส่ง log
        logger.exception("Unexpected error during run")
        print(f"\nเกิดข้อผิดพลาด — รายละเอียดถูกบันทึกไว้ที่:\n  {log_file}\n"
              f"หากต้องการความช่วยเหลือ ส่งไฟล์ log นี้ให้ผู้พัฒนาตรวจสอบได้",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
