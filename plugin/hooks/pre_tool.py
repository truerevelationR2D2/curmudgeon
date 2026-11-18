#!/usr/bin/env python3
"""PreToolUse for Read, Grep, Glob, Bash, PowerShell, Monitor, LSP, Agent and Task: the blindness guard (read_guard.py) and the stuck
refusal (stuck.py) in one process, so a session pays for one Python start per tool call, not two (03 §5.56 item 22).
Calls that neither can act on, which are almost all of them (the user's own session, any agent that isn't Curmudgeon's,
except an Agent or Task call, which the fork check sees), return before the guard is imported. One check runs first for
every Bash and PowerShell call, the user's own included (5.9.1, own_scripts.py): a command that runs another copy of
Curmudgeon's scripts, one inside the project laid out like the plugin's, is refused; any command without ".py" or
" -m " returns at once. Each part fails open, as it did as its own hook."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import json, re, sys

DENIED = False

def boundary(data):
    """For a reviewer's or verifier's Bash call, after the backstop above let it through: block it when it is outside
    the reviewers' command list (allowlist.py; listed for the owner, never cut), else log its start for the outcome
    check (outcome.py), which judges after the call what it changed on disk."""
    global DENIED
    import pathlib, workspace, conduct, allowlist, outcome
    root = workspace.project_root(data); me = workspace.clean_id(data.get("agent_id"))
    rec = workspace.info(root, me) if root and me else None
    if not rec: return
    cmd = str((data.get("tool_input") or {}).get("command") or "")
    have = conduct.claimed_by(root, me)
    own = pathlib.Path(root) / ".critic" / "reviews" / have if have else None
    why = allowlist.problem(cmd, rec["payload"], pathlib.Path(rec["payload"]).parent / "notes", own)
    if why:
        DENIED = True
        conduct.note(root, me, why, "blocked")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Curmudgeon: {why}."}}))
        return
    outcome.call_start(root, me, str(data.get("tool_use_id") or ""))

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    ours = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")) is not None
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if data.get("tool_name") in ("Bash", "PowerShell"):  # anyone, the lead included: only this plugin's own scripts run (5.9.1; PowerShell too, review L2)
        try:
            import own_scripts
            why = own_scripts.problem(str((data.get("tool_input") or {}).get("command") or ""), data.get("cwd"))
            if why:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Curmudgeon: {why}."}}))
                return 0
        except Exception: pass
    if not ours and data.get("tool_name") not in ("Agent", "Task"): return 0
    try:
        import read_guard
        read_guard.main(data)
        if read_guard.DENIED: return 0
    except Exception: pass
    if ours and data.get("tool_name") == "Bash" and re.search(r"curmudgeon-(?:reviewer|verifier)$", str(data.get("agent_type"))):
        try: boundary(data)  # the reviewers' command list and the outcome check's start (03 §5.57 item 52)
        except Exception: pass
        if DENIED: return 0
    if ours:
        try:
            import stuck
            stuck.main(data)
        except Exception: pass
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
