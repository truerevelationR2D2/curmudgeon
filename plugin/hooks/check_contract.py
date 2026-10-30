#!/usr/bin/env python3
"""SubagentStop check: a Curmudgeon reviewer or verifier may not finish until its output meets the contract. When it
does finish (the output passes, or this check already blocked once), its private copy of the project is deleted here,
in order: a separate stop hook would run in parallel and delete the copy while a blocked agent still needs it.
Reviewers must leave a valid .critic/reviews/review-<X>.json; verifiers must return a ```json verdict list, which this
hook saves, unchanged, as .critic/verdicts/<agent id>.json (variant packets: .critic/verdicts-variants/), so no model
copies a verdict (§5.56; guard_state.py keeps both folders from direct edits).
Never blocks twice in a row (stop_hook_active), and never blocks other agents. Fails open on errors, with a message."""
import json, os, pathlib, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace  # this folder's helper: project root, agent workspaces
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
try: from critic_findings import validate, refutation_problem, confirmation_problem, security_refutation_problem  # the same rules apply uses
except Exception as _e:  # a broken install must say so, not fail open silently, and still never leave a copy behind
    try:
        _d = json.load(sys.stdin); workspace.remove(workspace.project_root(_d), _d.get("agent_id"))
    except Exception: pass
    print(json.dumps({"systemMessage": f"Curmudgeon contract check skipped: its scripts could not be loaded ({type(_e).__name__}: {_e}). Reinstall the plugin."})); sys.exit(0)

def started_at(root, agent_id):
    """When this agent started: its workspace record (hooks/workspace.py), else None."""
    try:
        h = workspace.home_for(root, agent_id); p = h / "workspace.json" if h else None
        if not p or p.is_symlink() or not p.is_file(): return None
        v = json.loads(p.read_text()).get("made_at"); return float(v) if isinstance(v, (int, float)) else None
    except Exception: return None

def worked_in_copy(root, agent_id):
    """True when this agent's private copy was finished being made (its workspace record says so)."""
    try:
        h = workspace.home_for(root, agent_id); p = h / "workspace.json" if h else None
        if not p or p.is_symlink() or not p.is_file(): return False
        j = json.loads(p.read_text()); return isinstance(j, dict) and not j.get("building") and isinstance(j.get("made_at"), (int, float))
    except Exception: return False

def write_stop(root, me, rec):
    """The stop record (03 §5.56 item 15), in .critic/stops/, where agents can't write (guard_state) or read (read_guard);
    never through a link."""
    d = root / ".critic" / "stops"
    if d.is_symlink() or (root / ".critic").is_symlink(): return
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(d / f"{me}.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w") as fh: fh.write(json.dumps(rec))

def problems_review(root, msg, agent_id=None):
    d = root / ".critic" / "reviews"
    named = re.findall(r"review-([A-Za-z0-9]+)\.json", msg or "")
    if named: rv = [d / f"review-{named[-1]}.json"]  # the file this reviewer says it wrote
    else: return ["the reply must name the review file it wrote (.critic/reviews/review-<letter>.json)"]
    if not rv[0].exists(): return [f"{rv[0].name} was not written"]
    began = started_at(root, agent_id)
    if began and rv[0].stat().st_mtime < began - 2: return [f"{rv[0].name} was not written by you (it is older than your start); write your own review file"]
    if time.time() - rv[0].stat().st_mtime > 1800: return [f"{rv[0].name} is older than 30 minutes: this run didn't write it"]
    try: rows = json.loads(rv[-1].read_text())
    except Exception as e: return [f"{rv[-1].name} is not valid JSON ({e})"]
    errs = []
    if isinstance(rows, dict):  # {"findings": [...], "set_aside": [...]}: the set-aside list is logged, never counted
        aside = rows.get("set_aside", [])
        if not isinstance(aside, list) or any(not isinstance(x, dict) or not str(x.get("guard") or "").strip() for x in aside):
            errs.append("every set_aside entry must be an object naming the guard it relied on (guard: file:line and why)")
        rows = rows.get("findings")
    if not isinstance(rows, list): return [f"{rv[-1].name} must hold a JSON list of findings, or an object with a findings list"]
    for i, f in enumerate(rows):
        e = validate(f) if isinstance(f, dict) else ["not an object"]
        if e: errs.append(f"finding {i + 1}: {'; '.join(e)}")  # never its title: if a reviewer named another's file, the message must not carry that review's words
    return errs[:8]

def problems_verdict(msg, root=None):
    blocks = re.findall(r"```json\s*\n(.*?)```", msg or "", re.S)
    if not blocks: return ["no ```json verdict list in the reply"]
    try: rows = json.loads(blocks[-1])
    except Exception as e: return [f"the verdict block is not valid JSON ({e})"]
    errs = []
    for v in rows if isinstance(rows, list) else [rows]:
        if not isinstance(v, dict): errs.append("every verdict must be a JSON object"); continue
        if not v.get("id"): errs.append("a verdict has no id"); continue
        if v.get("verdict") not in ("confirmed", "refuted", "downgrade", "unclear"): errs.append(f"{v.get('id')}: verdict must be confirmed, refuted, downgrade or unclear")
        packet = {}
        for sub in ("verify", "verify-variants"):  # a variant packet is judged by its own impact and fields, like the main ones
            try: packet = json.loads((pathlib.Path(root or ".") / ".critic" / sub / f"{v['id']}.json").read_text()); break
            except Exception: pass
        if v.get("verdict") == "confirmed":
            cp = confirmation_problem(v, root=root)
            if cp: errs.append(f"{v.get('id')}: the merge would count this as unclear: {cp}")
        if v.get("verdict") == "refuted":
            imp = packet.get("impact") or "Critical"  # unknown impact: hold it to the strictest rule
            prob = refutation_problem(v.get("refutation") or v.get("reason"), imp, v.get("reproduced"), root=root) or security_refutation_problem(v, packet)
            if prob: errs.append(f"{v.get('id')}: this refutation would be ignored by the merge: {prob}")
    return errs[:8]

def save_verdicts(root, msg, agent_id):
    """Write the verifier's last ```json block, exactly as it returned it, where critic_run.py and the merge read it.
    Verdicts on variant packets (.critic/verify-variants/) go to their own folder. Links are refused; never raises."""
    blocks = re.findall(r"```json\s*\n(.*?)```", msg or "", re.S)
    aid = workspace.clean_id(agent_id) if agent_id else None
    if not blocks or not aid: return None
    try: rows = json.loads(blocks[-1])
    except ValueError: return None
    ids = [str(v.get("id")) for v in (rows if isinstance(rows, list) else [rows]) if isinstance(v, dict)]
    critic = pathlib.Path(root) / ".critic"
    variant = ids and all((critic / "verify-variants" / f"{i}.json").is_file() and not (critic / "verify" / f"{i}.json").is_file() for i in ids)
    d = critic / ("verdicts-variants" if variant else "verdicts")
    if critic.is_symlink() or d.is_symlink(): return None
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{aid}.json"
    if out.is_symlink(): return None
    fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(blocks[-1].strip() + "\n")
    return out

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    kind = str(data.get("agent_type") or "")
    root = workspace.project_root(data)
    if data.get("stop_hook_active"): errs = []  # never block twice in a row
    elif kind.endswith("curmudgeon-reviewer"): errs = problems_review(root, data.get("last_assistant_message", ""), data.get("agent_id"))
    elif kind.endswith("curmudgeon-verifier"): errs = problems_verdict(data.get("last_assistant_message", ""), root)
    else: return 0
    if errs:
        print(json.dumps({"decision": "block", "reason": "Your output doesn't meet Curmudgeon contract yet: " + " | ".join(errs) + ". Fix it, then finish."}))
        return 0  # the agent keeps working, so its private copy stays
    if kind.endswith("curmudgeon-reviewer"):  # 03 §5.56 item 15: the tally checks that each review came from an agent that worked in its private copy
        try:
            named = re.findall(r"review-([A-Za-z0-9]+)\.json", data.get("last_assistant_message", "") or "")
            me = workspace.clean_id(data.get("agent_id")) if data.get("agent_id") else None
            if named and me: write_stop(root, me, {"review": f"review-{named[-1]}.json", "workspace": worked_in_copy(root, data.get("agent_id")), "at": time.time()})
        except Exception: pass
    if kind.endswith("curmudgeon-verifier"):
        try: save_verdicts(root, data.get("last_assistant_message", ""), data.get("agent_id"))
        except Exception as e: print(json.dumps({"systemMessage": f"Curmudgeon could not save this verifier's verdicts ({type(e).__name__}: {e}); critic_run.py next will ask for them again"}))
    try: workspace.remove(root, data.get("agent_id"))  # the agent is really finishing: delete its copy, keep its notes (§5.29)
    except Exception: pass
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e: print(json.dumps({"systemMessage": f"Curmudgeon contract check skipped: {type(e).__name__}: {e}"})); sys.exit(0)
