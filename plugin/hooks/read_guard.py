#!/usr/bin/env python3
"""PreToolUse: makes blindness a control, not only an instruction. When a Curmudgeon reviewer, verifier or dedup agent
tries to read something its role must not see, the call is denied:

  reviewer  other reviews, the scan, the tally, counts, findings, the teardown, verify packets, the ledger, history,
            the outside reviewer's files, and other agents' scratch folders
  verifier  the reviews, the tally, counts, findings, the teardown, dedup files, history and the outside files
            (it may read its packets, the code, the scan and the ledger's recorded decisions)
  dedup     the reviews, the tally, counts, findings, the scan, verify packets, the ledger, history and outside files

It also refuses a fork (an Agent call with subagent_type "fork") while a review run is active: a fork inherits the
whole conversation, so it can't be blind.

Read, Grep and Glob are checked by their path arguments. Bash is checked by looking for a forbidden .critic path in
the command, which is best effort: a determined agent can still build a path a pattern can't see. Every other agent and
the main conversation are untouched. It never fails closed on its own errors (a crash allows the call), because a
broken guard must not stop the user's work; the merge script's own checks still apply."""
import json, os, pathlib, re, sys, time

COMMON = ["reviews", "tally.json", "counts.md", "findings.jsonl", "findings.sarif", "last-review.md", "history", "outside",
          "findings-import.jsonl", "refutations.jsonl", "spotcheck.md"]
DENY = {"reviewer": COMMON + ["scan", "scan-async", "verify", "dedup-candidates.json", "groups.json", "ledger.json", "ledger.md"],
        "verifier": COMMON + ["dedup-candidates.json", "groups.json", "ledger.json"],
        "dedup": COMMON + ["scan", "scan-async", "verify", "ledger.json", "ledger.md"]}

def role_of(agent_type):
    m = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup)", agent_type or "")
    return m.group(1) if m else None

def forbidden(text, role, agent_id):
    """The first forbidden .critic path named in text, or None."""
    for m in re.finditer(r"\.critic[/\\]+([^\s/\\\"'`;|&)]+)(?:[/\\]+([^\s/\\\"'`;|&)]+))?", text):
        top, sub = m.group(1), m.group(2) or ""
        if top in DENY[role] or (top == "scratch" and sub and sub != agent_id): return f".critic/{top}" + (f"/{sub}" if top == "scratch" else "")
    return None

def run_active(root):
    led = root / ".critic" / "ledger.json"
    try: started = json.loads(led.read_text()).get("started_at") if led.is_file() and not led.is_symlink() else None
    except Exception: started = None
    if not started: return False
    last = root / ".critic" / "last-review.md"
    return not last.exists() or last.stat().st_mtime < started

def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    tool, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    root = pathlib.Path(data.get("cwd") or os.getcwd())
    if tool in ("Agent", "Task"):
        if str(ti.get("subagent_type") or "").lower() == "fork" and run_active(root):
            return deny("Curmudgeon: no forks during a review run. A fork inherits the whole conversation, so it can't review blind. Start the named agent (curmudgeon:curmudgeon-reviewer, -verifier, -dedup or -detector) instead.")
        return 0
    role = role_of(data.get("agent_type"))
    if not role: return 0
    agent_id = str(data.get("agent_id") or "")
    texts = []
    for k in ("file_path", "path", "pattern", "glob", "command", "notebook_path"):
        v = ti.get(k)
        if isinstance(v, str) and v: texts.append(v)
    for v in texts:
        cands = [v]
        if not v.startswith(("/", "\\")) and tool != "Bash": cands.append(str(root / v))
        try:
            real = str(pathlib.Path(v if os.path.isabs(v) else root / v).resolve()) if tool != "Bash" else ""
            if real: cands.append(real)
        except (OSError, ValueError): pass
        for c in cands:
            hit = forbidden(c.replace("\\", "/"), role, agent_id)
            if hit:
                return deny(f"Curmudgeon blindness: a {role} may not read {hit}. Review only what your brief gives you"
                            + (" and your own scratch folder." if role else "."))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
