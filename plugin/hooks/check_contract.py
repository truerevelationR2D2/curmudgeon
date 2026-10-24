#!/usr/bin/env python3
"""SubagentStop check: a Curmudgeon reviewer or verifier may not finish until its output meets the contract.
Reviewers must leave a valid .critic/reviews/review-<X>.json; verifiers must return a ```json verdict list.
Never blocks twice in a row (stop_hook_active), and never blocks other agents. Fails open on errors, with a message."""
import json, pathlib, re, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
try: from critic_findings import validate, refutation_problem  # both the review and the verdict checks use it
except Exception as _e:  # a broken install must say so, not fail open silently
    print(json.dumps({"systemMessage": f"Curmudgeon contract check skipped: its scripts could not be loaded ({type(_e).__name__}: {_e}). Reinstall the plugin."})); sys.exit(0)

def problems_review(root, msg):
    d = root / ".critic" / "reviews"
    named = re.findall(r"review-([A-Za-z0-9]+)\.json", msg or "")
    if named: rv = [d / f"review-{named[-1]}.json"]  # the file this reviewer says it wrote
    else: return ["the reply must name the review file it wrote (.critic/reviews/review-<letter>.json)"]
    if not rv[0].exists(): return [f"{rv[0].name} was not written"]
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
        if e: errs.append(f"finding {i + 1} ({(f or {}).get('title', '?') if isinstance(f, dict) else '?'}): {'; '.join(e)}")
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
        if v.get("verdict") == "refuted":
            imp = "Critical"  # unknown impact: hold it to the strictest rule
            try: imp = json.loads((pathlib.Path(root or ".") / ".critic" / "verify" / f"{v['id']}.json").read_text()).get("impact") or imp
            except Exception: pass
            prob = refutation_problem(v.get("refutation") or v.get("reason"), imp, v.get("reproduced"), root=root)
            if prob: errs.append(f"{v.get('id')}: this refutation would be ignored by the merge: {prob}")
    return errs[:8]

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    if data.get("stop_hook_active"): return 0
    kind = str(data.get("agent_type") or "")
    root = pathlib.Path(data.get("cwd") or ".")
    if kind.endswith("curmudgeon-reviewer"): errs = problems_review(root, data.get("last_assistant_message", ""))
    elif kind.endswith("curmudgeon-verifier"): errs = problems_verdict(data.get("last_assistant_message", ""), root)
    else: return 0
    if errs:
        print(json.dumps({"decision": "block", "reason": "Your output doesn't meet Curmudgeon contract yet: " + " | ".join(errs) + ". Fix it, then finish."}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e: print(json.dumps({"systemMessage": f"Curmudgeon contract check skipped: {type(e).__name__}: {e}"})); sys.exit(0)
