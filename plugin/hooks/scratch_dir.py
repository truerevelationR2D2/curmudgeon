#!/usr/bin/env python3
"""SubagentStart: gives each Curmudgeon agent its own private scratch folder, .critic/scratch/<agent_id>/, and tells it
the path. The read guard (read_guard.py) stops agents from reading each other's folders, so a reviewer's notes or test
scripts can never reach another reviewer. Never fails the agent's start."""
import json, os, pathlib, re, sys

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    kind = str(data.get("agent_type") or "")
    if not re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup|detector)", kind): return 0
    agent_id = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("agent_id") or ""))[:64]
    if not agent_id: return 0
    root = pathlib.Path(data.get("cwd") or os.getcwd()); c = root / ".critic"
    if c.is_symlink() or (c / "scratch").is_symlink(): return 0  # never create through a link a cloned repo planted
    d = c / "scratch" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    try: os.chmod(d, 0o700)
    except OSError: pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext":
        f"Your private scratch folder is {d}. Put any notes, probes or test scripts there and nowhere else; other agents can't read it, and you can't read theirs."}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
