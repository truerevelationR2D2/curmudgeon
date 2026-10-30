#!/usr/bin/env python3
"""PreToolUse guard: Curmudgeon's records may only change through its scripts, never by a direct file edit. This is
a tripwire against an agent "fixing" its own score, not a lock: shell commands are not intercepted.
Only active in projects that have a .critic/ folder. Fails open (allows) on any error."""
import json, os, pathlib, re, sys

PROTECTED = {"ledger.json", "ledger.md", "decisions.md", "gate", "gate-count", "gate-async", "findings.jsonl", "findings.sarif", "tally.json", "counts.md", "async-shown.json", "refutations.jsonl", "runlog.jsonl", "spotcheck.md"}
PROTECTED_DIRS = {"baseline", "verify", "restore", "private", "verdicts", "verdicts-variants", "stops", "verify-opened"}  # verdicts: saved by check_contract.py as the verifier returned them, never retyped; stops and verify-opened: the hooks' own records of each agent (§5.56)
AGENT_PROTECTED = {"scope.json", "rules.md", "rules", "last-review.md"}  # the owner's rules and the run's end marker: an untracked rules.md an agent wrote would count as the owner's  # private: the browser driver's signing key and live-request ledger

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path: return 0
    p = pathlib.Path(os.path.normpath(os.path.join(data.get("cwd") or os.getcwd(), path)))  # resolve "..", so .critic/x/../ledger.json is caught
    parts = p.parts
    agent = bool(re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")))
    if agent:  # 03 §5.56 batch 2 round 2: an agent's Write tool, like its shell, stays out of the owner's record and the real project
        real = os.path.realpath(p)
        def under(base):
            b = os.path.realpath(str(base)); return real == b or real.startswith(b + os.sep)
        base = pathlib.Path(os.environ.get("CURMUDGEON_STATE_DIR") or pathlib.Path.home() / ".curmudgeon")
        why = None
        if under(base): why = f"{path} is the owner's own record of approvals and consent; only the owner gives those, through the lead"
        else:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import workspace
                root = workspace.project_root(data)
            except Exception: root = None
            if root and ".critic" not in parts and under(root):  # a path inside .critic by its words (a copy's linked node_modules) gets the link check below
                why = f"{path} is in the real project, outside your copy: write probes in your copy or your notes folder"
        if why:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Curmudgeon: {why}."}}))
            return 0
    if ".critic" not in parts: return 0
    after = parts[parts.index(".critic") + 1:]
    if not after: return 0
    if agent and after[0] == "scratch" and len(after) == 3 and after[2] in ("workspace.json", "stop.json"):  # the hooks' record of the copy, which the stop record trusts
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon: {'/'.join(after)} is the hooks' record of your copy; agents can't write it."}}))
        return 0
    if agent and after[0] == "scratch" and "payload" in after[:3]:  # 03 §5.56 item 11: a write inside the copy that a link carries into the real project
        pl = pathlib.Path(*parts[:parts.index(".critic") + 1 + after.index("payload") + 1])
        try: out = not os.path.realpath(p).startswith(os.path.realpath(pl) + os.sep)
        except OSError: out = False
        if out:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"Curmudgeon: {path} is inside your copy, but a link (node_modules, .venv) carries a write there into the real project. Write probes in your notes folder instead."}}))
            return 0
    if agent and after[0] in AGENT_PROTECTED:  # the owner's consent files: the lead may write them for the owner, Curmudgeon's own agents never
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon's agents can't write {'/'.join(after)}: it is the owner's (their rules, which live sites may be loaded) or the run's own marker. Ask the lead, who asks the owner."}}))
        return 0
    if after[0] in PROTECTED or (after[0] in PROTECTED_DIRS):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon records can't be edited directly ({'/'.join(after)}). Use critic_ledger.py or critic_merge.py, which validate every change."}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
