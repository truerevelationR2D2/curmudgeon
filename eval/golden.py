#!/usr/bin/env python3
"""Rung 2 of the evidence ladder: golden tests for the scripted checks, with no model. Each fixture is copied to a
temporary folder (fixture2 gets its fake planted key in the copy only), scanned with critic_scan.py, and the result is
reduced to what should not change by accident: every row's severity, rule, area, place and message, and every check's
state. That is compared with eval/golden/<fixture>.json.

  golden.py              compare; exit 1 on any difference, printing it
  CRITIC_UPDATE_GOLDEN=1 golden.py    rewrite the expected files on purpose (review the diff before committing)

A stale expected file (for a fixture that no longer exists) also fails. The idea of on-purpose snapshot updates and
stale-snapshot failures comes from syrupy (MIT); this is our own code."""
import difflib, json, os, pathlib, re, shutil, subprocess, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
SCAN = HERE.parent / "plugin" / "skills" / "review" / "scripts" / "critic_scan.py"
FIXTURES = ["fixture", "fixture-clean", "fixture2", "fixture2-clean", "fixture3", "fixture4", "fixture4-clean"]
PLANT = ("__PLANTED_STRIPE_KEY__", "sk_" + "live_51HxQ2bOrderDeskSecretKey9f8e7d")

def snapshot(name):
    with tempfile.TemporaryDirectory() as t:
        dst = pathlib.Path(t) / name
        shutil.copytree(HERE / name, dst, ignore=shutil.ignore_patterns(".critic"))
        for p in dst.rglob("*.js"):
            s = p.read_text(encoding="utf-8")
            if PLANT[0] in s: p.write_text(s.replace(*PLANT), encoding="utf-8")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable, "-I", str(SCAN), ".", "--root", ".", "--no-project-rules"], cwd=dst, capture_output=True, timeout=300, env=env)
        rep = json.loads((dst / ".critic" / "scan" / "report.json").read_text())
    rows = sorted({(r["sev"], r["rule"], r["area"], r["where"], r["what"]) for r in rep["findings"]})
    checks = {k: v["state"] for k, v in sorted(rep["checks"].items())}
    return {"checks": checks, "rows": [list(r) for r in rows]}

def main():
    update = os.environ.get("CRITIC_UPDATE_GOLDEN") == "1"; bad = 0
    want = {f"{n}.json" for n in FIXTURES}
    for stale in sorted(p.name for p in (HERE / "golden").glob("*.json") if p.name not in want):
        print(f"STALE golden/{stale}: its fixture is gone; delete it"); bad += 1
    for name in FIXTURES:
        got = json.dumps(snapshot(name), indent=1, ensure_ascii=False) + "\n"
        exp_p = HERE / "golden" / f"{name}.json"
        if update: exp_p.write_text(got, encoding="utf-8"); print(f"wrote golden/{name}.json"); continue
        if not exp_p.exists(): print(f"MISSING golden/{name}.json (run with CRITIC_UPDATE_GOLDEN=1 once)"); bad += 1; continue
        exp = exp_p.read_text(encoding="utf-8")
        if exp != got:
            bad += 1; print(f"CHANGED {name}:")
            sys.stdout.writelines(difflib.unified_diff(exp.splitlines(True), got.splitlines(True), f"golden/{name}.json", "now", n=1))
        else: print(f"ok {name}")
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())
