import sys, time
sys.path.insert(0, "../src")
import tkinter as tk
import kegg_mapper.gui as gui

class FakeClient:
    def __init__(self, **kw):
        self.stats = {"compound_api_calls":0,"compound_cache_hits":0,"find_api_calls":0,"find_cache_hits":0,"network_errors":0}
    def get_compound(self, cid):
        db={"C00114":{"kegg_name":"Choline","kegg_formula":"C5H14NO","kegg_exact_mass":104.1},
            "C00031":{"kegg_name":"D-Glucose","kegg_formula":"C6H12O6","kegg_exact_mass":None},
            "C00025":{"kegg_name":"L-Glutamate","kegg_formula":"C5H9NO4","kegg_exact_mass":None},
            "C00712":{"kegg_name":"Oleic acid","kegg_formula":"C18H34O2","kegg_exact_mass":None}}
        return dict(db.get(cid.strip(),{"kegg_name":None,"kegg_formula":None,"kegg_exact_mass":None}))
    def find_by_name(self, name):
        f={"Choline":[{"cid":"C00114","names":"Choline"}],"Glucose":[{"cid":"C00031","names":"D-Glucose"}],
           "L-Glutamate":[{"cid":"C00025","names":"L-Glutamate"}],"Oleic acid":[{"cid":"C00712","names":"Oleic acid"}],
           "Aspirin":[{"cid":"C01405","names":"a"},{"cid":"C21332","names":"b"}]}
        return [dict(h) for h in f.get(name.strip(),[])]
    # aspirin multi -> ambiguous needs formulas
gui.KeggClient = FakeClient

open("/tmp/shot_in.txt","w").write(
    "Name\tFormula\nCholine\tC5H13NO\nGlucose\tC6H12O6\nL-Glutamate\tC5H9NO4\n"
    "Oleic acid\tC18H34O2\nPC(18:1/0:0)\tC26H52NO7P\nMysteryX\tC4H4\n")

root = tk.Tk()
app = gui.CompVertIDGUI(root)
app.pos_file.set("/tmp/shot_in.txt")
app.output_file.set("/tmp/shot_out.xlsx")
app._on_run()
deadline = time.time()+5
while time.time() < deadline:
    root.update()
    if app._worker and not app._worker.is_alive():
        for _ in range(6): root.update(); time.sleep(0.05)
        break
    time.sleep(0.02)
root.update()
time.sleep(0.3)
root.update()

# capture window
import subprocess
root.geometry("820x620+0+0")
root.update()
time.sleep(0.4)
subprocess.run(["import","-window","root","/tmp/gui_screenshot.png"])  # imagemagick capture root
root.destroy()
print("screenshot attempted")
