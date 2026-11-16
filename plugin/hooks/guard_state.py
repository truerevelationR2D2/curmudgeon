#!/usr/bin/env python3
"""PreToolUse guard: Curmudgeon's records may only change through its scripts, never by a direct file edit. This is
a tripwire against an agent "fixing" its own score, not a lock: shell commands are not intercepted.
Only active in projects that have a .critic/ folder. Fails open (allows) on any error."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import json, os, pathlib, re, sys

PROTECTED = {"ledger.json", "tally-reviews.json", "ledger.md", "decisions.md", "gate", "gate-count", "gate-async", "findings.jsonl", "findings.sarif", "tally.json", "counts.md", "async-shown.json", "refutations.jsonl", "runlog.jsonl", "spotcheck.md", "boundary.json", "plan.json", "cost.jsonl"}
PROTECTED_DIRS = {"baseline", "verify", "restore", "private", "verdicts", "verdicts-variants", "stops", "verify-opened", "proctor"}  # proctor, boundary.json, plan.json, cost.jsonl: written only by the scripts and hooks; a reviewer that wiped the proctor's marks would pass its own check (5.8.1 C2)  # verdicts: saved by check_contract.py as the verifier returned them, never retyped; stops and verify-opened: the hooks' own records of each agent (§5.56)
AGENT_PROTECTED = {"scope.json", "rules.md", "rules", "last-review.md", "briefs", "scan"}  # briefs: what the copy check counts as shown to a reviewer; scan: the report the tally trusts (5.8.1 blind round C1)  # the owner's rules and the run's end marker: an untracked rules.md an agent wrote would count as the owner's  # private: the browser driver's signing key and live-request ledger

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out): check(data)
    if out.getvalue(): sys.stdout.write(out.getvalue()); return 0
    if re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")):  # audit V26: the stuck refusal for a repeated Write or Edit (the PostToolUse watcher sees them; Read-type calls get it in pre_tool.py)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import stuck
            stuck.main(data)
        except Exception: pass
    return 0

def strict(data, p, path):
    """The reviewers' standard (03 §5.57 item 44) for a reviewer's Write or Edit: allowed in its own copy and notes
    (never a settings or instructions file Claude Code reads) and in the review it claimed. Returns None to go on to
    the checks below, ("blocked", why) for a write refused without a cut (no claim yet), or ("cut", why)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import workspace, conduct
    root = workspace.project_root(data)
    if not root: return None
    me = workspace.clean_id(data.get("agent_id"))
    real = os.path.realpath(str(p))
    def under(base):
        b = os.path.realpath(str(base)); return workspace.fold(real) == workspace.fold(b) or workspace.fold(real).startswith(workspace.fold(b) + os.sep)
    mine = pathlib.Path(root) / ".critic" / "scratch" / me
    lex = workspace.fold(str(p)); lm = workspace.fold(str(mine))
    if me and (lex == lm or lex.startswith(lm + os.sep)) and not under(mine): return ("cut", f"wrote {path}, which a link in its copy (node_modules, .venv) carries into the real project")
    if me and under(mine):  # realpath: a link in the copy that carries the write elsewhere lands below, outside
        rel = os.path.relpath(real, os.path.realpath(str(mine)))
        if workspace.fold(rel) in ("workspace.json", "stop.json"): return ("cut", f"wrote {rel}, the hooks' record of its copy")
        if conduct.OWN_SETTINGS_RX.search(rel.replace(os.sep, "/")): return ("cut", f"wrote {path}, an instructions file Claude Code reads")
        return None
    reviews = pathlib.Path(root) / ".critic" / "reviews"
    if workspace.fold(os.path.dirname(real)) == workspace.fold(os.path.realpath(str(reviews))) and re.fullmatch(r"(?i)review-[A-Za-z0-9]+\.json", os.path.basename(real)):
        have = conduct.claimed_by(root, me)
        if not have: return ("blocked", f"{os.path.basename(real)} before claiming your review: run the claim command your brief gives first")
        if have.lower() == os.path.basename(real).lower(): return None
        return ("cut", f"wrote {os.path.basename(real)}, which is not the review it claimed ({have})")
    return ("cut", f"wrote {path}, outside its copy, its notes and the review it claimed")

def check(data):
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path: return 0
    p = pathlib.Path(os.path.normpath(os.path.join(data.get("cwd") or os.getcwd(), path)))  # resolve "..", so .critic/x/../ledger.json is caught
    if re.fullmatch(r"(?:curmudgeon:)?curmudgeon-reviewer", str(data.get("agent_type") or "")):
        r = strict(data, p, path)
        if r:
            import workspace, conduct
            conduct.note(workspace.project_root(data), data.get("agent_id"), r[1], r[0])
            tail = (" That breaks the reviewers' standard (your instructions list it), so this review is cut: its votes won't count, and the report names it." if r[0] == "cut" else "")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Curmudgeon: refused, the agent {r[1]}.{tail}" if r[0] == "cut" else f"Curmudgeon: you can't write {r[1]}."}}))
            return 0
    parts = p.parts
    low = tuple(x.lower() for x in parts)  # .critic/Proctor is .critic/proctor on a case-insensitive disk (macOS, Windows), as read_guard.py already assumes (5.8.1 blind round C2)
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
            if root and ".critic" not in low and under(root):  # a path inside .critic by its words (a copy's linked node_modules) gets the link check below
                why = f"{path} is in the real project, outside your copy: write probes in your copy or your notes folder"
        if why:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": f"Curmudgeon: {why}."}}))
            return 0
    if ".critic" not in low: return 0
    after = parts[low.index(".critic") + 1:]
    if not after: return 0
    first = after[0].lower()
    mine = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("agent_id") or ""))[:64]  # workspace.clean_id
    if agent and first == "scratch" and len(after) >= 2 and after[1].lower() != mine.lower():  # another agent's copy or notes: a blind reviewer never changes what another one reads (ultimate audit Q02)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon: {path} is in another agent's private folder; write only in your own copy and notes."}}))
        return 0
    if agent and first == "scratch" and len(after) == 3 and after[2].lower() in ("workspace.json", "stop.json"):  # the hooks' record of the copy, which the stop record trusts
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon: {'/'.join(after)} is the hooks' record of your copy; agents can't write it."}}))
        return 0
    if agent and first == "scratch" and "payload" in [x.lower() for x in after[:3]]:  # 03 §5.56 item 11: a write inside the copy that a link carries into the real project
        pl = pathlib.Path(*parts[:low.index(".critic") + 1 + [x.lower() for x in after].index("payload") + 1])
        try: out = not os.path.realpath(p).startswith(os.path.realpath(pl) + os.sep)
        except OSError: out = False
        if out:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"Curmudgeon: {path} is inside your copy, but a link (node_modules, .venv) carries a write there into the real project. Write probes in your notes folder instead."}}))
            return 0
    if agent and first in AGENT_PROTECTED:  # the owner's consent files: the lead may write them for the owner, Curmudgeon's own agents never
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon's agents can't write {'/'.join(after)}: it is the owner's (their rules, which live sites may be loaded) or the run's own marker. Ask the lead, who asks the owner."}}))
        return 0
    if first in PROTECTED or first in PROTECTED_DIRS:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Curmudgeon records can't be edited directly ({'/'.join(after)}). Use critic_ledger.py or critic_merge.py, which validate every change."}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
