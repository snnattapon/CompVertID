"""
gui.py — หน้าต่างโปรแกรม (tkinter) สำหรับผู้ใช้ที่ไม่ถนัด command line

ออกแบบเพื่อ workflow ง่าย ๆ: เลือกไฟล์ -> กด Run -> เห็น progress -> เปิดดูผล
รองรับทั้งไฟล์ Compound Discoverer (.xlsx) และรายชื่อ (.txt/.csv)

จุดสำคัญทางเทคนิค:
- mapping รันใน background thread เพื่อไม่ให้หน้าต่างค้าง (freeze) ระหว่างยิง API
- สื่อสารจาก worker thread กลับ UI ผ่าน queue (thread-safe) แล้วให้ main loop
  ดึงมาอัปเดต — ห้ามแตะ widget จาก thread อื่นตรง ๆ (tkinter ไม่ปลอดภัย)
- ผลลัพธ์ลงสีตาม config.CONFIDENCE_COLOR_GROUP ที่วางไว้ตั้งแต่กลุ่ม 1

i18n: ข้อความที่ผู้ใช้เห็นดึงจาก i18n.t(key, self.lang) — สลับภาษาได้จาก dropdown
      แบบ rebuild (สร้าง UI ใหม่ทั้งหมดตอนสลับ) ค่าที่กรอกไว้ผูกกับ StringVar/
      BooleanVar จึงไม่หายตอน rebuild

หมายเหตุ status/error ที่วิ่งผ่าน queue จาก worker thread:
      worker ส่ง "key ของ i18n + พารามิเตอร์" กลับมา (ไม่ส่งข้อความสำเร็จรูป)
      แล้วให้ _poll_queue บน main thread แปลเป็นข้อความตามภาษาปัจจุบัน
      → ถ้าผู้ใช้สลับภาษาระหว่างรัน ข้อความใหม่ก็ยังตรงภาษา
"""

import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

import pandas as pd

from . import __version__, config, i18n
from .kegg_api import KeggClient
from .input_loader import load_input, UnsupportedInputError
from .core import map_dataframe, merge_and_dedupe, finalize, MissingColumnsError
from .logging_setup import setup_logging, log_problem_compound


_PROBLEM_CONFIDENCES = {"formula_mismatch", "ambiguous", "low", "not_found", "no_name"}


def _file_types(lang: str):
    """สร้างรายการชนิดไฟล์สำหรับ file dialog ตามภาษาปัจจุบัน"""
    return [
        (i18n.t("filetype.supported", lang), "*.xlsx *.xlsm *.txt *.csv *.tsv"),
        (i18n.t("filetype.cd", lang), "*.xlsx *.xlsm"),
        (i18n.t("filetype.list", lang), "*.txt *.csv *.tsv"),
        (i18n.t("filetype.all", lang), "*.*"),
    ]


def _open_folder(path: Path):
    """เปิด file explorer ไปที่โฟลเดอร์ที่กำหนด (ข้ามแพลตฟอร์ม)"""
    path = Path(path)
    folder = path if path.is_dir() else path.parent
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["explorer", str(folder)])
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder)])
        else:
            subprocess.run(["xdg-open", str(folder)])
    except Exception:
        pass  # เปิดไม่ได้ก็ไม่ต้องล้ม แค่ผู้ใช้ต้องไปเปิดเอง


class CompVertIDGUI:
    def __init__(self, root):
        self.root = root
        self.root.geometry("820x680")
        self.root.minsize(720, 600)

        # ภาษาปัจจุบัน (default = en) — ต้องตั้งก่อน _build_ui เพราะ UI ใช้ค่านี้
        self.lang = i18n.DEFAULT_LANG

        # ตัวแปรสถานะ (ผูกกับ widget; ไม่หายตอน rebuild เพราะไม่สร้างใหม่)
        self.pos_file = tk.StringVar()
        self.neg_file = tk.StringVar()
        self.output_file = tk.StringVar(value=str(Path.home() / "kegg_mapping_results.xlsx"))
        self.debug_mode = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value=i18n.t("status.ready", self.lang))
        # ตัวแปรของ dropdown ภาษา (เก็บชื่อที่แสดง เช่น "English"/"ไทย")
        self.lang_var = tk.StringVar(value=i18n.LANG_DISPLAY_NAMES[self.lang])

        self._queue = queue.Queue()   # ช่องทางสื่อสารจาก worker thread กลับ UI
        self._worker = None
        self._last_output = None
        self._last_log = None
        self._last_result_df = None   # ผลล่าสุด เก็บไว้เติมตารางกลับตอน rebuild (สลับภาษา)

        self._build_ui()
        self._poll_queue()  # เริ่มวนตรวจ queue

    # --------------------------------------------------------------
    # สร้างหน้าตา (เรียกซ้ำได้ — ใช้ตอนสลับภาษา)
    # --------------------------------------------------------------
    def _build_ui(self):
        # ล้าง widget เดิมทั้งหมดก่อนสร้างใหม่ (รองรับการ rebuild ตอนสลับภาษา)
        for child in self.root.winfo_children():
            child.destroy()

        # อัปเดต title ตามภาษาปัจจุบัน
        self.root.title(i18n.t("window.title", self.lang, version=__version__))

        pad = {"padx": 8, "pady": 4}

        # ---- แถบเลือกภาษา (มุมบน) ----
        frm_lang = ttk.Frame(self.root)
        frm_lang.pack(fill="x", **pad)
        ttk.Label(frm_lang, text=i18n.t("lang.label", self.lang)).pack(side="left", padx=(8, 4))
        lang_names = [name for _, name in i18n.available_languages()]
        combo = ttk.Combobox(
            frm_lang, textvariable=self.lang_var, values=lang_names,
            state="readonly", width=12,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._on_language_change)

        # ---- ส่วนเลือกไฟล์ input ----
        frm_in = ttk.LabelFrame(self.root, text=i18n.t("input.frame", self.lang))
        frm_in.pack(fill="x", **pad)

        # แถบเตือนสำคัญ: pos/neg ต้องเป็นคู่ของการทดลองเดียวกัน (ชั้น 2 ของ cross-project protection)
        warn = tk.Frame(frm_in, bg="#FFF3CD", highlightbackground="#E0A800", highlightthickness=1)
        warn.grid(row=0, column=0, columnspan=3, sticky="we", padx=8, pady=(8, 4))
        tk.Label(
            warn,
            text=i18n.t("input.warn.line1", self.lang),
            bg="#FFF3CD", fg="#664D03", justify="left", anchor="w", font=("", 9, "bold"),
        ).pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(
            warn,
            text=i18n.t("input.warn.line2", self.lang),
            bg="#FFF3CD", fg="#664D03", justify="left", anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 4))

        self._file_row(frm_in, i18n.t("input.pos_label", self.lang), self.pos_file, 1)
        self._file_row(frm_in, i18n.t("input.neg_label", self.lang), self.neg_file, 2)
        ttk.Label(
            frm_in,
            text=i18n.t("input.hint", self.lang),
            foreground="#666",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))

        # ---- ส่วนไฟล์ผลลัพธ์ ----
        frm_out = ttk.LabelFrame(self.root, text=i18n.t("output.frame", self.lang))
        frm_out.pack(fill="x", **pad)
        ttk.Label(frm_out, text=i18n.t("output.save_as", self.lang)).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(frm_out, textvariable=self.output_file, width=60).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(frm_out, text=i18n.t("button.select_output", self.lang), command=self._pick_output).grid(row=0, column=2, padx=8)
        frm_out.columnconfigure(1, weight=1)

        # ---- ตัวเลือก ----
        frm_opt = ttk.Frame(self.root)
        frm_opt.pack(fill="x", **pad)
        ttk.Checkbutton(
            frm_opt,
            text=i18n.t("option.debug", self.lang),
            variable=self.debug_mode,
        ).pack(side="left", padx=8)

        # ---- ปุ่ม Run + progress ----
        frm_run = ttk.Frame(self.root)
        frm_run.pack(fill="x", **pad)
        self.btn_run = ttk.Button(frm_run, text=i18n.t("button.run", self.lang), command=self._on_run)
        self.btn_run.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(frm_run, mode="determinate", length=380)
        self.progress.pack(side="left", padx=8, fill="x", expand=True)

        ttk.Label(self.root, textvariable=self.status_text, foreground="#333").pack(fill="x", padx=12)

        # ---- ตารางผลลัพธ์ ----
        frm_tbl = ttk.LabelFrame(self.root, text=i18n.t("table.frame", self.lang))
        frm_tbl.pack(fill="both", expand=True, **pad)
        # คอลัมน์ตารางคงชื่อ (key ภายใน) เป็นชื่อคอลัมน์ output เพื่อ map ค่าได้ตรง
        cols = ("Mode", "Input_Name", "Mapped_KEGG_ID", "KEGG_Formula", "Confidence")
        # หัวตารางที่แสดง (แปลได้ แต่ปัจจุบันคงเป็นอังกฤษให้ตรงไฟล์ output ทั้งสองภาษา)
        headings = {
            "Mode": i18n.t("table.mode", self.lang),
            "Input_Name": i18n.t("table.input_name", self.lang),
            "Mapped_KEGG_ID": i18n.t("table.mapped_kegg_id", self.lang),
            "KEGG_Formula": i18n.t("table.kegg_formula", self.lang),
            "Confidence": i18n.t("table.confidence", self.lang),
        }
        self.tree = ttk.Treeview(frm_tbl, columns=cols, show="headings", height=10)
        widths = {"Mode": 70, "Input_Name": 220, "Mapped_KEGG_ID": 150, "KEGG_Formula": 120, "Confidence": 150}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(frm_tbl, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # ตั้งสีแต่ละกลุ่ม (ตาม config) ให้ Treeview
        for group, hexcolor in config.COLOR_GROUP_HEX.items():
            self.tree.tag_configure(group, background=f"#{hexcolor}")

        # ถ้ามีผลลัพธ์เดิมอยู่ (เช่นเพิ่งรันเสร็จแล้วสลับภาษา) เติมกลับลงตารางใหม่
        if self._last_result_df is not None:
            self._fill_tree(self._last_result_df)

        # ---- ปุ่มเปิดโฟลเดอร์ (หลังรันเสร็จ) ----
        frm_open = ttk.Frame(self.root)
        frm_open.pack(fill="x", **pad)
        # สถานะปุ่ม: เปิดใช้ได้เฉพาะเมื่อมีผล/ log แล้ว (คงสถานะข้าม rebuild)
        out_state = "normal" if self._last_output else "disabled"
        log_state = "normal" if self._last_log else "disabled"
        self.btn_open_out = ttk.Button(frm_open, text=i18n.t("button.open_output", self.lang), command=self._open_output_folder, state=out_state)
        self.btn_open_out.pack(side="left", padx=8)
        self.btn_open_log = ttk.Button(frm_open, text=i18n.t("button.open_log", self.lang), command=self._open_log_folder, state=log_state)
        self.btn_open_log.pack(side="left", padx=8)

    def _file_row(self, parent, label, var, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(parent, textvariable=var, width=60).grid(row=row, column=1, sticky="we", padx=4)
        ttk.Button(parent, text=i18n.t("button.select_file", self.lang),
                   command=lambda: self._pick_file(var)).grid(row=row, column=2, padx=8)
        parent.columnconfigure(1, weight=1)

    # --------------------------------------------------------------
    # สลับภาษา
    # --------------------------------------------------------------
    def _on_language_change(self, event=None):
        """ผู้ใช้เลือกภาษาใหม่จาก dropdown → อัปเดต self.lang แล้วสร้าง UI ใหม่ทั้งหมด"""
        new_lang = i18n.display_to_code(self.lang_var.get())
        if new_lang == self.lang:
            return  # ภาษาเดิม ไม่ต้องทำอะไร
        self.lang = new_lang
        # อัปเดตข้อความ status ปัจจุบันให้เป็นภาษาใหม่ (ถ้ายังเป็นข้อความ ready เริ่มต้น)
        self.status_text.set(i18n.t("status.ready", self.lang))
        self._build_ui()

    # --------------------------------------------------------------
    # การเลือกไฟล์
    # --------------------------------------------------------------
    def _pick_file(self, var):
        path = filedialog.askopenfilename(
            title=i18n.t("dialog.pick_input.title", self.lang),
            filetypes=_file_types(self.lang),
        )
        if path:
            var.set(path)

    def _pick_output(self):
        path = filedialog.asksaveasfilename(
            title=i18n.t("dialog.pick_output.title", self.lang),
            defaultextension=".xlsx",
            initialfile="kegg_mapping_results.xlsx",
            filetypes=[(i18n.t("filetype.excel", self.lang), "*.xlsx")],
        )
        if path:
            self.output_file.set(path)

    # --------------------------------------------------------------
    # กด Run
    # --------------------------------------------------------------
    def _on_run(self):
        if self._worker and self._worker.is_alive():
            return  # กำลังทำงานอยู่ ไม่ให้กดซ้ำ

        sources = []
        if self.pos_file.get().strip():
            sources.append((self.pos_file.get().strip(), "pos"))
        if self.neg_file.get().strip():
            sources.append((self.neg_file.get().strip(), "neg"))

        if not sources:
            messagebox.showwarning(
                i18n.t("msg.no_input.title", self.lang),
                i18n.t("msg.no_input.body", self.lang),
            )
            return
        if not self.output_file.get().strip():
            messagebox.showwarning(
                i18n.t("msg.no_output.title", self.lang),
                i18n.t("msg.no_output.body", self.lang),
            )
            return

        # ล้างตารางเดิม + ล็อกปุ่ม
        self._last_result_df = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.btn_run.config(state="disabled")
        self.btn_open_out.config(state="disabled")
        self.btn_open_log.config(state="disabled")
        self.progress.config(value=0)

        # เริ่ม worker thread
        self._worker = threading.Thread(
            target=self._run_pipeline,
            args=(sources, self.output_file.get().strip(), self.debug_mode.get()),
            daemon=True,
        )
        self._worker.start()

    # --------------------------------------------------------------
    # งานหนักรันใน thread แยก (ห้ามแตะ widget ตรง ๆ ที่นี่)
    # worker ส่ง "คีย์ i18n + พารามิเตอร์" กลับ ไม่ส่งข้อความสำเร็จรูป
    # ให้ _poll_queue (main thread) แปลตามภาษาปัจจุบัน
    # --------------------------------------------------------------
    def _run_pipeline(self, sources, output_path, debug):
        try:
            logger, log_file = setup_logging(output_path=output_path, debug=debug)
            self._queue.put(("log_file", str(log_file)))

            client = KeggClient(
                on_network_error=lambda msg: (
                    logger.error(f"Network: {msg}"),
                    self._queue.put(("status_key", ("status.network_error", {"msg": msg}))),
                )
            )

            df_by_mode = {"pos": None, "neg": None}
            for filepath, mode_tag in sources:
                self._queue.put(("status_key", ("status.reading", {"name": Path(filepath).name})))
                try:
                    df = load_input(filepath)
                except (MissingColumnsError, UnsupportedInputError) as e:
                    logger.error(str(e))
                    self._queue.put(("error_raw", str(e)))
                    return

                total = len(df)
                self._queue.put(("total", total))

                def cb(current, t, name, _mode=mode_tag):
                    self._queue.put(("progress", (current, t, f"[{_mode}] {name}")))

                result = map_dataframe(df, mode_tag, client, progress_callback=cb)
                logger.info(f"Mapped {len(result)} rows from {mode_tag} ({Path(filepath).name})")

                if debug:
                    for _, r in result.iterrows():
                        if r.get("Confidence") in _PROBLEM_CONFIDENCES:
                            log_problem_compound(logger, mode_tag, r.get("Row_NO"),
                                                 r.get("Input_Name"), r.get("Input_Formula"),
                                                 f"{r.get('Confidence')} | {r.get('Notes')}")

                if df_by_mode[mode_tag] is None:
                    df_by_mode[mode_tag] = result
                else:
                    df_by_mode[mode_tag] = pd.concat([df_by_mode[mode_tag], result], ignore_index=True)

            self._queue.put(("status_key", ("status.merging", {})))
            df_pos = df_by_mode["pos"] if df_by_mode["pos"] is not None else pd.DataFrame(columns=config.OUTPUT_COLUMNS)
            df_neg = df_by_mode["neg"] if df_by_mode["neg"] is not None else pd.DataFrame(columns=config.OUTPUT_COLUMNS)
            merged = merge_and_dedupe(df_pos, df_neg, info_callback=lambda m: logger.info(m))
            final_df = finalize(merged)

            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            final_df.to_excel(out_path, sheet_name=config.SHEET_NAME, index=False)
            logger.info(f"Saved results to {out_path} ({len(final_df)} rows)")

            s = client.stats
            logger.info(f"KEGG API stats: compound_calls={s['compound_api_calls']} "
                        f"cache_hits={s['compound_cache_hits']} find_calls={s['find_api_calls']} "
                        f"find_cache_hits={s['find_cache_hits']} network_errors={s['network_errors']}")

            self._queue.put(("done", (final_df, str(out_path))))

        except Exception as e:
            try:
                logger.exception("Unexpected error during run")
            except Exception:
                pass
            self._queue.put(("error_key", ("error.generic", {"msg": str(e)})))

    # --------------------------------------------------------------
    # main loop ดึงข้อความจาก queue มาอัปเดต UI (ทำงานบน main thread)
    # --------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "status":
                    self.status_text.set(payload)
                elif kind == "status_key":
                    key, kw = payload
                    self.status_text.set(i18n.t(key, self.lang, **kw))
                elif kind == "total":
                    self.progress.config(maximum=payload, value=0)
                elif kind == "progress":
                    current, total, name = payload
                    self.progress.config(value=current)
                    self.status_text.set(i18n.t("status.processing", self.lang,
                                                current=current, total=total, name=name))
                elif kind == "log_file":
                    self._last_log = payload
                elif kind == "done":
                    final_df, out_path = payload
                    self._on_done(final_df, out_path)
                elif kind == "error_raw":
                    self._on_error(payload)
                elif kind == "error_key":
                    key, kw = payload
                    self._on_error(i18n.t(key, self.lang, **kw))
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)  # วนตรวจทุก 80ms

    def _fill_tree(self, final_df):
        """เติมผลลง treeview พร้อมสีตามกลุ่ม confidence (แยกออกมาให้ rebuild เรียกซ้ำได้)"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for _, r in final_df.iterrows():
            conf = r["Confidence"]
            group = config.CONFIDENCE_COLOR_GROUP.get(conf, "gray")
            self.tree.insert("", "end", tags=(group,), values=(
                r["Mode"], r["Input_Name"], r["Mapped_KEGG_ID"], r["KEGG_Formula"], conf,
            ))

    def _on_done(self, final_df, out_path):
        self._last_output = out_path
        self._last_result_df = final_df   # เก็บไว้เผื่อ rebuild ตอนสลับภาษา
        self._fill_tree(final_df)
        n = len(final_df)
        self.status_text.set(i18n.t("status.done", self.lang, n=n, name=Path(out_path).name))
        self.btn_run.config(state="normal")
        self.btn_open_out.config(state="normal")
        self.btn_open_log.config(state="normal")
        self.progress.config(value=self.progress["maximum"])

    def _on_error(self, msg):
        self.status_text.set(i18n.t("status.error", self.lang))
        self.btn_run.config(state="normal")
        if self._last_log:
            self.btn_open_log.config(state="normal")
        messagebox.showerror(
            i18n.t("msg.error.title", self.lang),
            i18n.t("msg.error.body", self.lang, msg=msg),
        )

    def _open_output_folder(self):
        if self._last_output:
            _open_folder(Path(self._last_output))

    def _open_log_folder(self):
        if self._last_log:
            _open_folder(Path(self._last_log))


def main():
    root = tk.Tk()
    CompVertIDGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
