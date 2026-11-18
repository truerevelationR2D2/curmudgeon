#!/usr/bin/env python3
"""PostToolUse for the stuck detector (stuck.py): calls by anything but a Curmudgeon agent, which are almost all of
them, return before stuck.py and its imports load (03 §5.56 item 22). Fails open, as stuck.py does."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import json, re, sys

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    if not re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")): return 0
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if data.get("tool_name") in ("Write", "Edit", "MultiEdit") and re.search(r"curmudgeon-reviewer$", str(data.get("agent_type"))):
        try:  # its own claimed review, saved: a known write the outcome check never charges to anyone (round 1, F-b4ea77d7)
            import pathlib, workspace, conduct, outcome
            root = workspace.project_root(data); me = workspace.clean_id(data.get("agent_id")); have = conduct.claimed_by(root, me) if root else None
            f = str((data.get("tool_input") or {}).get("file_path") or "")
            if have and f and os.path.realpath(f) == os.path.realpath(str(pathlib.Path(root) / ".critic" / "reviews" / have)): outcome.known(root, f)
        except Exception: pass
    if data.get("tool_name") == "Bash" and re.search(r"curmudgeon-(?:reviewer|verifier)$", str(data.get("agent_type"))):
        try:  # the outcome check (03 §5.57 item 52): what this call changed on disk, whatever its spelling
            import pathlib, workspace, conduct, outcome
            root = workspace.project_root(data); me = workspace.clean_id(data.get("agent_id"))
            if root and me and workspace.info(root, me):
                have = conduct.claimed_by(root, me)
                own = [pathlib.Path(root) / ".critic" / "reviews" / have] if have else []
                outcome.record(root, outcome.call_end(root, me, str(data.get("tool_use_id") or ""), own))
        except Exception: pass
    try:
        import stuck
        stuck.main(data)
    except Exception: pass
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
