#!/usr/bin/env python3
"""Measure one scripted lens against its planted-defect fixture, its clean twin and its decoys, with no model (SC-48
onward; the rule from Project instructions 12: a lens ships only after it is measured).

usage:
  lens.py eval/lens5.json [--json]

It copies the fixture and the clean twin to a temporary folder, runs critic_scan.py on each, and reports:
  recall      planted defects whose rule fired at the planted file:line
  precision   regular rows from this lens that hit a planted defect, out of all regular rows from this lens in the
              fixture (pedantic rows are counted apart and never count either way)
  decoys      regular rows from this lens in a decoy file (must be 0)
  clean twin  regular rows from this lens in the clean twin (must be 0)
Exit 0 when recall is 100% and decoys and clean-twin rows are 0; 1 otherwise; 2 on bad usage."""
import json, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCAN = HERE.parent / "plugin" / "skills" / "review" / "scripts" / "critic_scan.py"

def rows(folder, area):
    with tempfile.TemporaryDirectory(prefix="lens-") as t:
        dst = pathlib.Path(t) / "p"; shutil.copytree(folder, dst)
        r = subprocess.run([sys.executable, str(SCAN), ".", "--root", ".", "--no-project-rules"], cwd=dst, capture_output=True, text=True, timeout=300)
        rep = dst / ".critic" / "scan" / "report.json"
        if not rep.exists(): sys.exit(f"lens: the scan wrote no report ({r.stderr.strip()[-300:]})")
        areas = set(area) if isinstance(area, list) else {area}
        return [x for x in json.loads(rep.read_text())["findings"] if x.get("area") in areas]

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0 if a else 2
    key = json.loads(pathlib.Path(a[0]).read_text()); area = key["area"]
    got = rows(HERE / key["fixture"], area); clean = rows(HERE / key["clean"], area)
    reg = [x for x in got if x.get("tier") != "pedantic"]
    hits = {p["id"]: any(x["rule"] == p["rule"] and x["where"] == p["where"] for x in reg) for p in key["planted"]}
    true_rows = [x for x in reg if any(x["rule"] == p["rule"] and x["where"] == p["where"] for p in key["planted"])]
    decoy = [x for x in reg if x["where"].rsplit(":", 1)[0] in key.get("decoy_files", [])]
    clean_reg = [x for x in clean if x.get("tier") != "pedantic"]
    out = {"lens": key["lens"], "recall": f"{sum(hits.values())} of {len(hits)}", "missed": [k for k, v in hits.items() if not v],
           "precision": f"{len(true_rows)} of {len(reg)}", "false_rows": [f"{x['rule']} {x['where']}" for x in reg if x not in true_rows],
           "decoy_rows": [f"{x['rule']} {x['where']}" for x in decoy], "clean_twin_rows": [f"{x['rule']} {x['where']}" for x in clean_reg],
           "pedantic_rows": sum(1 for x in got if x.get("tier") == "pedantic")}
    ok = not out["missed"] and not out["decoy_rows"] and not out["clean_twin_rows"]
    out["verdict"] = "PASS" if ok else "FAIL"
    if "--json" in a: print(json.dumps(out, indent=1))
    else:
        print(f"{out['lens']}: {out['verdict']}")
        for k in ("recall", "precision", "missed", "false_rows", "decoy_rows", "clean_twin_rows", "pedantic_rows"): print(f"  {k}: {out[k]}")
    return 0 if ok else 1

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
