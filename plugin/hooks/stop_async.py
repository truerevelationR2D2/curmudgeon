#!/usr/bin/env python3
"""Background stop review (opt-in with /curmudgeon:gate async). When Claude stops, a free static scan runs on the files
changed since the last review, in the background, without blocking. Only when it finds a new FAIL-level problem
does it wake Claude (exit 2 with asyncRewake), and each problem wakes it once. At most 3 wakes per batch of edits."""
import hashlib, json, os, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
try: from critic_findings import log_run
except Exception:
    def log_run(*a, **k): pass

def main():
    try: data = json.load(sys.stdin)
    except Exception: data = {}
    if data.get("stop_hook_active"): return 0
    root = pathlib.Path(data.get("cwd") or os.getcwd()); c = root / ".critic"
    if c.is_symlink() or any(x.is_symlink() for x in c.glob("*")): return 0  # never write through a link a cloned repo planted
    if not (c / "gate-async").exists(): return 0
    try: stamps = json.loads((c / "ledger.json").read_text()).get("stamps", {})
    except Exception: stamps = {}
    review = c / "last-review.md"; since = review.stat().st_mtime if review.exists() else 0
    changed = [k for k in stamps if (root / k).exists() and (root / k).stat().st_mtime > since]
    if True:  # new or changed files outside the stamps count too
        log_run(root, "command", "background stop check: git diff --name-only HEAD and git ls-files --others")
        out = subprocess.run(["git", "diff", "--name-only", "-z", "HEAD"], cwd=root, capture_output=True, text=True).stdout.split("\0")
        out += subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root, capture_output=True, text=True).stdout.split("\0")
        out = [x for x in out if x]
        changed = sorted(set(changed) | {x for x in out if (root / x).is_file() and not x.startswith(".critic/") and (root / x).stat().st_mtime > since})
    if not changed: return 0
    scan = pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts" / "critic_scan.py"
    outdir = c / "scan-async"
    for x in changed[:40]:
        subprocess.run([sys.executable, str(scan), str(root / x), "--root", str(root), "--out", str(outdir / hashlib.sha1(x.encode()).hexdigest()[:8]), "--no-project-rules"], capture_output=True, timeout=120)
    shown_f = c / "async-shown.json"
    try: shown = json.loads(shown_f.read_text())
    except Exception: shown = {"batch": "", "wakes": 0, "ids": []}
    batch = hashlib.sha1("|".join(sorted(changed)).encode()).hexdigest()[:10]
    if shown.get("batch") != batch: shown = {"batch": batch, "wakes": 0, "ids": shown.get("ids", [])}
    new = []
    for rep in outdir.glob("*/report.json"):
        for r in json.loads(rep.read_text()).get("findings", []):
            key = f"{r['rule']}|{r['where']}"
            if r["sev"] == "FAIL" and key not in shown["ids"] and key not in [f"{x['rule']}|{x['where']}" for x in new]: new.append(r)
    if not new: shown_f.write_text(json.dumps(shown)); return 0
    if shown["wakes"] >= 3:  # don't mark them shown: they'll be reported in the next batch
        shown_f.write_text(json.dumps(shown)); return 0
    show = new[:8]
    shown["wakes"] += 1; shown["ids"] += [f"{r['rule']}|{r['where']}" for r in show]; shown_f.write_text(json.dumps(shown))
    more = f"\n…and {len(new) - len(show)} more (they'll be shown next time)." if len(new) > len(show) else ""
    print("Curmudgeon background check found new blocking problems in files edited since the last review:\n" + "\n".join(f"- {r['where']}: {r['what']}" for r in show) + more +
          "\nFix them, or run /curmudgeon:review review on those files. (/curmudgeon:gate off stops these checks.)", file=sys.stderr)
    return 2

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
