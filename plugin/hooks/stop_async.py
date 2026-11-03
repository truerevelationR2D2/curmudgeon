#!/usr/bin/env python3
"""Background stop review (opt-in with /curmudgeon:gate async). When Claude stops, a free static scan runs on the files
changed since the last review, in the background, without blocking. Only when it finds a new FAIL-level problem
does it wake Claude (exit 2 with asyncRewake), and each problem wakes it once. At most 3 wakes per batch of edits.
Claude Code doesn't enforce a timeout on async hooks, so this script keeps its own: every git call has a 10 s limit,
and the whole check, one scan per 200 changed files (every changed file, never only the first 200), stops by DEADLINE
seconds; the next stop starts with the part it had no time for."""
import hashlib, json, os, pathlib, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace
DEADLINE = 300  # seconds for the whole check, well inside the 600 s the hook declares
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "review", "scripts")); import safegit  # git without the repository's own commands (03 §5.57 review)
try: from critic_findings import log_run
except Exception:
    def log_run(*a, **k): pass

CHUNK = 200  # files per scan process
SKIP_WALK = {".git", ".critic", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache", ".cache"}

def walk_changed(root, since, limit=500_000):
    """Outside git: every file under root changed since the last review, by its own time (audit O3), newest first. No
    cap on what is found, so nothing is left out for good (Qodo on #17); the walk itself stops after `limit` entries."""
    out, n = [], 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_WALK]
        for fn in fns:
            n += 1
            p = pathlib.Path(dp) / fn
            try:
                if not p.is_symlink() and (m := p.stat().st_mtime) > since: out.append((m, str(p.relative_to(root)).replace(os.sep, "/")))
            except OSError: continue
        if n >= limit: break
    return [x for _, x in sorted(out, reverse=True)]

def part_order(n, cursor):
    """The parts in the order this stop scans them: from where the last stop ran out of time, round to the start, so a
    slow first part can't keep the later ones waiting at every stop (Qodo on #17)."""
    cursor = cursor if 0 <= cursor < n else 0
    return list(range(cursor, n)) + list(range(cursor))

def main():
    try: data = json.load(sys.stdin)
    except Exception: data = {}
    if data.get("stop_hook_active"): return 0
    root = workspace.project_root(data); c = root / ".critic"
    if c.is_symlink() or any(x.is_symlink() for x in c.glob("*")): return 0  # never write through a link a cloned repo planted
    if not (c / "gate-async").exists(): return 0
    try:
        from critic_findings import gate_owned
        if not gate_owned(root, "async"): return 0  # a committed marker turns nothing on (ultimate audit V12)
    except Exception: return 0  # the owner's record can't be checked: off, never on the project's marker alone (Qodo on PR #14)
    try: stamps = json.loads((c / "ledger.json").read_text()).get("stamps", {})
    except Exception: stamps = {}
    review = c / "last-review.md"; since = review.stat().st_mtime if review.exists() else 0
    changed = [k for k in stamps if (root / k).exists() and (root / k).stat().st_mtime > since]
    log_run(root, "command", "background stop check: git diff --name-only --relative HEAD and git ls-files --others")
    def git(*args):
        try: r = safegit.run([*args], cwd=root, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired): return None
        return r.stdout.split("\0") if r.returncode == 0 else None
    # --relative: in a project that is a subfolder of a repository, paths come relative to the project (audit V47)
    diff, others = git("diff", "--name-only", "--relative", "-z", "HEAD"), git("ls-files", "--others", "--exclude-standard", "-z")
    if diff is None and others is not None: diff = git("ls-files", "-z")  # a repository with no commit yet: what is staged is the change (Qodo on #17)
    if diff is None and others is None: out = walk_changed(root, since)  # not a git work tree: look at the files themselves (audit O3)
    else: out = [x for x in (diff or []) + (others or []) if x]
    changed = sorted(set(changed) | {x for x in out if (root / x).is_file() and not x.startswith(".critic/") and (root / x).stat().st_mtime > since})
    if not changed: return 0
    scan = pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts" / "critic_scan.py"
    outdir = c / "scan-async"
    t0 = time.time(); listed = changed  # every changed file, in parts of CHUNK; never the first 200 only (audit Q09)
    (c / "scan-async-files.txt").write_text("\n".join(listed) + "\n", encoding="utf-8")
    shown_f = c / "async-shown.json"
    try: shown = json.loads(shown_f.read_text())
    except Exception: shown = {"batch": "", "wakes": 0, "ids": []}
    batch = hashlib.sha1("|".join(sorted(changed)).encode()).hexdigest()[:10]
    if shown.get("batch") != batch: shown = {"batch": batch, "wakes": 0, "ids": shown.get("ids", []), "cursor": 0}
    nparts = (len(listed) + CHUNK - 1) // CHUNK; order = part_order(nparts, int(shown.get("cursor") or 0)); done = []
    reports, scanned = [], set()
    for k in order:  # one scan per part, not one process per file
        part = listed[k * CHUNK:(k + 1) * CHUNK]; lst = c / f"scan-async-part-{k}.txt"; lst.write_text("\n".join(part) + "\n", encoding="utf-8")
        left = DEADLINE - (time.time() - t0)
        if left < 10: break  # out of time: the next stop starts from this part (the cursor below)
        try: subprocess.run([sys.executable, str(scan), str(root), "--root", str(root), "--out", str(outdir / f"part-{k}"), "--no-project-rules",
                             "--only", str(lst)], capture_output=True, timeout=left)
        except subprocess.TimeoutExpired: break
        reports.append(outdir / f"part-{k}" / "report.json"); scanned |= set(part); done.append(k)
    shown["cursor"] = 0 if len(done) == nparts else order[len(done)]  # where the next stop starts
    new = []
    mine = scanned
    for rep in reports:
        if not rep.exists(): continue
        for r in json.loads(rep.read_text()).get("findings", []):
            key = f"{r['rule']}|{r['where']}"
            if r["where"].split(":")[0] not in mine: continue  # only problems in the files that changed
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
