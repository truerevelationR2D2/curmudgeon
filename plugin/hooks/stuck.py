#!/usr/bin/env python3
"""Stuck detection, "throw it a rope" (SC-67, ruling §5.15). A script, not a model, decides whether a Curmudgeon agent
is going round in circles, from its own recent tool calls. The patterns are rebuilt in our own code from OpenHands'
stuck detector and SWE-agent's typed exits (both MIT).

PostToolUse (Curmudgeon agents only; every other session and agent returns at once): each call is recorded in the
agent's scratch folder as (normalised action, normalised result, error or not). Then:

  stuck_repeat      the same action with the same result 3 times in a row
  stuck_error_loop  the same action failing 3 times in a row
  stuck_pingpong    two actions alternating A, B, A, B, A, B

The first time a signal fires the agent gets ONE rope: what it repeated, the last error, and two allowed next moves
(change approach, or declare "cannot verify: <why>"). If the same signal fires again, the agent is told to stop that
scenario and move on, a typed STUCK row goes to .critic/stuck.jsonl (listed in counts.md, never hidden), and the
PreToolUse side refuses that exact action from then on. A stuck reviewer is an absent vote, never an invented one.

Normalising strips times, dates, ports, temporary paths, hex ids and long numbers, so "the same" means the same.
Fails open: a broken check never stops an agent."""
import hashlib, json, os, pathlib, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace

WINDOW = 12
NORM = [(re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(:\d\d(\.\d+)?)?Z?"), "<time>"), (re.compile(r"\b\d\d:\d\d:\d\d\b"), "<time>"),
        (re.compile(r"(?:/tmp|/var/folders|/private/var)/[\w./-]+"), "<tmp>"), (re.compile(r":\d{2,5}\b"), ":<port>"),
        (re.compile(r"\b[0-9a-f]{12,}\b"), "<hex>"), (re.compile(r"\b\d{5,}\b"), "<n>"), (re.compile(r"\d+(\.\d+)?\s*(ms|s|seconds)\b"), "<dur>")]

def norm(text):
    t = str(text)[:20000]
    for rx, rep in NORM: t = rx.sub(rep, t)
    return hashlib.sha256(t.encode()).hexdigest()[:16]

def is_error(resp):
    if isinstance(resp, dict):
        if resp.get("is_error") or resp.get("error") or resp.get("interrupted"): return True
        code = resp.get("exit_code", resp.get("returncode"))
        if isinstance(code, int) and code != 0: return True
        resp = resp.get("stderr") or resp.get("stdout") or resp.get("content") or ""
    return bool(re.match(r"\s*(error|traceback|fatal|exception|command failed|no such file)", str(resp)[:200], re.I))

def state_path(root, agent_id):
    h = workspace.home_for(root, agent_id)
    return (h / "actions.json") if h else None

def load(p):
    try: return json.loads(p.read_text()) if p and p.is_file() and not p.is_symlink() else {"calls": [], "roped": [], "stuck": [], "blocked": []}
    except Exception: return {"calls": [], "roped": [], "stuck": [], "blocked": []}

def signal(calls):
    if len(calls) >= 3:
        a, b, c = calls[-3:]
        if a["act"] == b["act"] == c["act"]:
            if a["err"] and b["err"] and c["err"]: return "stuck_error_loop"
            if a["res"] == b["res"] == c["res"]: return "stuck_repeat"
    if len(calls) >= 6:
        acts = [x["act"] for x in calls[-6:]]
        if acts[0] != acts[1] and acts[0::2] == [acts[0]] * 3 and acts[1::2] == [acts[1]] * 3: return "stuck_pingpong"
    return None

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    kind = str(data.get("agent_type") or "")
    if not re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup|detector)", kind): return 0
    root = workspace.project_root(data); aid = workspace.clean_id(data.get("agent_id"))
    p = state_path(root, aid)
    if not p or not p.parent.is_dir(): return 0
    st = load(p)
    act = norm(json.dumps({"tool": data.get("tool_name"), "input": data.get("tool_input")}, sort_keys=True))
    event = data.get("hook_event_name") or ("PostToolUse" if "tool_response" in data else "PreToolUse")
    if event == "PreToolUse":
        if act in st.get("blocked", []):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason":
                "Curmudgeon: you were stuck on exactly this action and told to stop. Mark this scenario 'cannot verify: <why>' and move on to the next thing you were going to check."}}))
        return 0
    resp = data.get("tool_response")
    st["calls"] = (st.get("calls", []) + [{"act": act, "res": norm(json.dumps(resp, sort_keys=True, default=str)), "err": is_error(resp), "tool": data.get("tool_name")}])[-WINDOW:]
    sig = signal(st["calls"]); msg = None
    if sig and sig not in st.get("roped", []):
        st.setdefault("roped", []).append(sig); st["calls"] = st["calls"][-1:]  # the rope resets the window
        what = {"stuck_repeat": "the same action with the same result three times", "stuck_error_loop": "the same action failing three times", "stuck_pingpong": "two actions alternating back and forth"}[sig]
        msg = (f"Curmudgeon rope ({sig}): you have repeated {what} (last tool: {data.get('tool_name')}). That approach isn't getting anywhere. "
               "You have two moves: (1) change approach: a different file, command, input or tool than the ones you've tried; or (2) declare 'cannot verify: <why you're stuck>' for this scenario "
               "and move on. If the same thing happens again you'll be stopped on it.")
    elif sig:
        st.setdefault("stuck", []).append(sig); st.setdefault("blocked", []).append(act)
        led = {}
        try: led = json.loads((root / ".critic" / "ledger.json").read_text())
        except Exception: pass
        row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "run": led.get("run"), "round": led.get("round"), "role": kind.split(":")[-1].replace("curmudgeon-", ""), "agent_id": aid, "type": sig, "tool": data.get("tool_name")}
        sj = root / ".critic" / "stuck.jsonl"
        if not sj.is_symlink():
            with open(sj, "a", encoding="utf-8") as fh: fh.write(json.dumps(row) + "\n")
        msg = (f"STUCK ({sig}): the same pattern again after your rope. Stop this scenario now: write 'cannot verify: <why>' for it in your output (with what you tried), "
               "and move on to the next thing you were going to check. This exact action is now refused. The stuck record is kept so the cause can be fixed.")
    try: p.write_text(json.dumps(st))
    except OSError: pass
    if msg: print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
