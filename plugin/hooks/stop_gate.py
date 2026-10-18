#!/usr/bin/env python3
"""Curmudgeon stop gate (opt-in, Claude Code only). Turned on per project by /curmudgeon:gate on (creates .critic/gate).

It blocks finishing for one of two causes, each with its own message:
  1. edits since the last review: a watched file is newer than .critic/last-review.md. Watched files are the ones the
     last review stamped (critic_ledger.py stamp) plus any code file created or changed since (so new files count too).
  2. open Critical/High findings after a full run. A review-only run (mode "review") is an audit: its open findings
     never block.
Loop guards: never blocks while Claude Code reports stop_hook_active; at most 3 blocks for the same batch of edits.
After the third it lets stops through for that batch for good (it says so once); a new edit starts a new batch.
Fails open, but never silently: an unexpected error lets the stop through with a message saying the gate is off."""
import hashlib, json, os, pathlib, sys

SKIP = {".git", "node_modules", "dist", "build", ".critic", "__pycache__", ".next", "coverage", "vendor", ".venv", "venv"}
CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".css", ".scss", ".html", ".vue", ".svelte", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".swift", ".kt"}

def newest(root, stamps):
    best = (0.0, None)
    paths = [root / k for k in stamps]
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith(".")]
        paths += [pathlib.Path(dp) / fn for fn in fns if pathlib.Path(fn).suffix in CODE]
    for p in paths:
        try: m = p.stat().st_mtime
        except OSError: continue  # deleted files and broken links are skipped, not fatal
        if m > best[0]: best = (m, p)
    return best

def out(obj): print(json.dumps(obj)); return 0

def main():
    try: data = json.load(sys.stdin)
    except Exception: data = {}
    if data.get("stop_hook_active"): return 0
    root = pathlib.Path(data.get("cwd") or os.getcwd()); c = root / ".critic"
    if not (c / "gate").exists(): return 0
    try: L = json.loads((c / "ledger.json").read_text())
    except FileNotFoundError: L = {}
    except Exception as e: return out({"systemMessage": f"Curmudgeon gate is off for this stop: the ledger can't be read ({e}). Fix .critic/ledger.json or run critic_ledger.py init."})
    if not isinstance(L, dict): L = {}
    review = c / "last-review.md"
    m, p = newest(root, L.get("stamps") or {})
    reason, batch = None, ""
    if p is not None and not (review.exists() and review.stat().st_mtime >= m):
        batch = hashlib.sha1(f"{p}:{m}".encode()).hexdigest()[:12]
        where = p.relative_to(root) if str(p).startswith(str(root)) else p
        reason = ("No Curmudgeon review exists yet for this project's edits." if not review.exists() else f"{where} was edited after the last Curmudgeon review.") + \
                 " Run /curmudgeon:review review on the files edited since the last review (use the curmudgeon-reviewer agent), and save the teardown to .critic/last-review.md."
    elif L.get("mode") == "full":
        open_ = [i for i, f in (L.get("findings") or {}).items() if isinstance(f, dict) and f.get("status") == "open" and str(f.get("score", "")).title() in ("Critical", "High")]
        if open_:
            batch = "open:" + ",".join(sorted(open_))
            reason = (f"The last full Curmudgeon run left Critical/High findings open: {', '.join(open_[:8])}. Fix each one, or defer it with "
                      "critic_ledger.py defer ID impossible|conflicts|worse \"note\". Then re-check and update .critic/last-review.md.")
    cnt = c / "gate-count"
    if not reason: cnt.unlink(missing_ok=True); return 0
    try: prev = json.loads(cnt.read_text())
    except Exception: prev = {}
    if prev.get("batch") == batch and prev.get("released"): return 0  # already handed back for this batch
    n = prev.get("n", 0) + 1 if prev.get("batch") == batch else 1
    if n > 3:
        cnt.write_text(json.dumps({"batch": batch, "n": n, "released": True}))
        return out({"systemMessage": f"Curmudgeon gate let this stop through after 3 blocks on the same work, and won't block it again until something changes. Still unresolved: {reason.split('. ')[0]}. Over to you: fix, defer with a reason, or /curmudgeon:gate off."})
    cnt.write_text(json.dumps({"batch": batch, "n": n}))
    return out({"decision": "block", "reason": f"Curmudgeon gate ({n} of 3 for this work): {reason} Turn the gate off with /curmudgeon:gate off."})

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:
        print(json.dumps({"systemMessage": f"Curmudgeon gate is off for this stop: unexpected error ({type(e).__name__}: {e})."})); sys.exit(0)
