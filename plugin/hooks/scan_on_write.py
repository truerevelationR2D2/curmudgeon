#!/usr/bin/env python3
"""PostToolUse on Write, Edit and MultiEdit: the while-you-work scan (SC-62). It scans only the file just written,
with Curmudgeon's own scripted checks (well under a second, no model tokens, no project commands, nothing sent
anywhere), and hands any FAIL row straight back to Claude to fix, each problem once per version of the file.

Active in projects where Curmudgeon has run (a .critic/ledger.json exists), until `/curmudgeon:gate off` (which writes
.critic/watch-off; gate on or async removes it). Never for files under .critic/, never for Curmudgeon's own agents
(they work in private copies), never through a linked .critic. The scan's output goes to a temporary folder, so the
last review's report is never overwritten. Fails open and silent: a broken scan never stops the user's work."""
import hashlib, json, os, pathlib, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace

SCAN = pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts" / "critic_scan.py"

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    if str(data.get("agent_type") or "").split(":")[-1].startswith("curmudgeon-"): return 0
    root = workspace.project_root(data); c = root / ".critic"
    if c.is_symlink() or not (c / "ledger.json").is_file() or (c / "watch-off").exists(): return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path")
    if not path: return 0
    p = pathlib.Path(path); p = p if p.is_absolute() else root / p
    try: rel = p.resolve().relative_to(root.resolve())
    except (ValueError, OSError): return 0
    if not p.is_file() or ".critic" in rel.parts or p.stat().st_size > 2_000_000: return 0
    with tempfile.TemporaryDirectory(prefix="curmudgeon-watch-") as t:
        only = pathlib.Path(t) / "only.txt"; only.write_text(str(rel).replace(os.sep, "/") + "\n")
        try: subprocess.run([sys.executable, "-I", str(SCAN), ".", "--root", ".", "--only", str(only), "--out", t, "--no-project-rules", "--no-interact"],
                            cwd=root, capture_output=True, timeout=15, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        except (subprocess.SubprocessError, OSError): return 0
        try: rows = json.loads((pathlib.Path(t) / "report.json").read_text())["findings"]
        except Exception: return 0
    me = str(rel).replace(os.sep, "/")
    fails = [r for r in rows if r.get("sev") == "FAIL" and str(r.get("where", "")).split(":")[0] == me]
    if not fails: return 0
    shown_p = c / "watch-shown.json"
    try: shown = json.loads(shown_p.read_text()) if shown_p.is_file() and not shown_p.is_symlink() else {}
    except Exception: shown = {}
    digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    key = f"{me}@{digest}"
    new = [r for r in fails if f"{r['rule']}|{r['where']}" not in shown.get(key, [])]
    if not new: return 0
    shown = {k: v for k, v in shown.items() if not k.startswith(me + "@")}; shown[key] = [f"{r['rule']}|{r['where']}" for r in fails]
    try:
        if not shown_p.is_symlink(): shown_p.write_text(json.dumps(shown))
    except OSError: pass
    lines = [f"- {r['where']}: {r['what']} ({r['rule']})" for r in new[:8]]
    print(json.dumps({"decision": "block", "reason": "Curmudgeon's while-you-work scan found a blocking problem in the file you just wrote; fix it before moving on:\n" + "\n".join(lines) +
                      ("\n(…and more)" if len(new) > 8 else "") + "\nIf a row is wrong, record it with critic_ledger.py fp <rule> <file:line> \"why\"."}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
