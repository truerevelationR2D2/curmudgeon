#!/usr/bin/env python3
"""PreToolUse guard: Curmudgeon's records may only change through its scripts, never by a direct file edit. This is
a tripwire against an agent "fixing" its own score, not a lock: shell commands are not intercepted.
Only active in projects that have a .critic/ folder. Fails open (allows) on any error."""
import json, os, pathlib, sys

PROTECTED = {"ledger.json", "ledger.md", "gate", "gate-count", "gate-async", "findings.jsonl", "findings.sarif", "tally.json", "counts.md", "async-shown.json", "refutations.jsonl", "runlog.jsonl", "spotcheck.md"}
PROTECTED_DIRS = {"baseline", "verify", "restore"}

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path: return 0
    p = pathlib.Path(os.path.normpath(os.path.join(data.get("cwd") or os.getcwd(), path)))  # resolve "..", so .critic/x/../ledger.json is caught
    parts = p.parts
    if ".critic" not in parts: return 0
    after = parts[parts.index(".critic") + 1:]
    if not after: return 0
    if after[0] in PROTECTED or (after[0] in PROTECTED_DIRS):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon records can't be edited directly ({'/'.join(after)}). Use critic_ledger.py or critic_merge.py, which validate every change."}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
