"""
gui_headless_test.py — ทดสอบ GUI ภายใต้ virtual display (Xvfb)
ตรวจ: สร้าง UI ได้, สีตารางตั้งถูก, threaded pipeline + queue ทำงาน, ผลลง treeview พร้อมสี
"""
import sys, time
sys.path.insert(0, "../src")

import tkinter as tk
import compvertid.gui as gui
from compvertid import config


# fake client แทน KEGG จริง
class FakeClient:
    def __init__(self, **kw):
        self.stats = {"compound_api_calls": 0, "compound_cache_hits": 0,
                      "find_api_calls": 0, "find_cache_hits": 0, "network_errors": 0}
    def get_compound(self, cid):
        db = {"C00114": {"kegg_name": "Choline", "kegg_formula": "C5H14NO", "kegg_exact_mass": 104.1},
              "C00031": {"kegg_name": "D-Glucose", "kegg_formula": "C6H12O6", "kegg_exact_mass": None}}
        self.stats["compound_api_calls"] += 1
        return dict(db.get(cid.strip(), {"kegg_name": None, "kegg_formula": None, "kegg_exact_mass": None}))
    def find_by_name(self, name):
        f = {"Choline": [{"cid": "C00114", "names": "Choline"}],
             "Glucose": [{"cid": "C00031", "names": "D-Glucose"}]}
        self.stats["find_api_calls"] += 1
        return [dict(h) for h in f.get(name.strip(), [])]

gui.KeggClient = FakeClient

def P(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    assert cond, label

# input file: mix of good + charge_diff + not_found
open("/tmp/gui_in.txt", "w").write("Name\tFormula\nCholine\tC5H13NO\nGlucose\tC6H12O6\nMysteryX\tC4H4\n")

print("1) build UI")
root = tk.Tk()
app = gui.CompVertIDGUI(root)
P("window title set", "CompVertID" in root.title())
P("treeview has 5 columns", len(app.tree["columns"]) == 5)
P("color tags configured", all(
    app.tree.tag_configure(g)["background"][-1].lower() == f"#{h}".lower()[-1]
    for g, h in config.COLOR_GROUP_HEX.items()))
P("run button starts enabled", str(app.btn_run["state"]) == "normal")
P("open-folder buttons start disabled", str(app.btn_open_out["state"]) == "disabled")

print("2) run threaded pipeline")
app.pos_file.set("/tmp/gui_in.txt")
app.output_file.set("/tmp/gui_out.xlsx")
app._on_run()
P("run button disabled during work", str(app.btn_run["state"]) == "disabled")

# pump the event loop until worker finishes (max ~5s)
deadline = time.time() + 5
while time.time() < deadline:
    root.update()
    if app._worker and not app._worker.is_alive():
        # ให้ queue poll รอบสุดท้ายทำงาน
        for _ in range(5):
            root.update(); time.sleep(0.05)
        break
    time.sleep(0.02)

print("3) verify results populated")
rows = app.tree.get_children()
P("3 rows in treeview", len(rows) == 3)

# ตรวจสีของแต่ละแถว
results = []
for item in rows:
    vals = app.tree.item(item, "values")
    tags = app.tree.item(item, "tags")
    results.append((vals[1], vals[4], tags[0] if tags else None))  # name, confidence, colorgroup
    print(f"     {vals[1]:<12} conf={vals[4]:<20} color={tags[0] if tags else None}")

by_name = {r[0]: r for r in results}
P("Choline -> charge_diff -> yellow", by_name["Choline"][1] == "charge_diff" and by_name["Choline"][2] == "yellow")
P("Glucose -> found_high -> green", by_name["Glucose"][1] == "found_high" and by_name["Glucose"][2] == "green")
P("MysteryX -> not_found -> gray", by_name["MysteryX"][1] == "not_found" and by_name["MysteryX"][2] == "gray")

print("4) post-run UI state")
P("run button re-enabled", str(app.btn_run["state"]) == "normal")
P("open output folder enabled", str(app.btn_open_out["state"]) == "normal")
P("open log folder enabled", str(app.btn_open_log["state"]) == "normal")
P("output file created", __import__("os").path.exists("/tmp/gui_out.xlsx"))

root.destroy()
print("\nALL GUI HEADLESS TESTS PASSED")
