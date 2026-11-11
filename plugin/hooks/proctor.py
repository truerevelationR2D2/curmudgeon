"""The proctor (03 §5.57 item 35): a reviewer's whole transcript (every command's and every read's output) is checked for
what it must never have seen: one of the unique marks Curmudgeon writes into every brief, scan report, tally, count,
dedup list, verification packet and reviewer's review (critic_findings.proctor_mark, listed in
.critic/proctor/marks.json, which agents can't read). A mark in a reviewer's tool output means it read that file. Its
own brief's and its own review's marks don't count.

Only marks count, never similar text: text two honest reviewers both saw (the same test failure, a project rule)
would void one of them (5.5.0 blind round: three reviewers showed it), and precision comes first. The marks go on
every line of a review (one finding per line), and at the top and the bottom of every other file, so a partial read
of a review shows one; a grep of one line of a brief or the scan report may not, and the guard and the private copy
stay the first layers there.

The check runs at the reviewer's stop (its record in .critic/stops/) and again at each tally, against every mark known
by then, so a reviewer that read a review stamped after it stopped is caught too. Only tool results are read: what the
agent was shown, never what it typed (a 96-bit mark can't be guessed). A script; no model judges. It reads only."""
import json, pathlib, re, time

MAX_TRANSCRIPT = 64 * 1024 * 1024
BUDGET_S = 25         # the stop hook has 60 seconds in all

def _strings(x, out, cap):
    """Every string inside x (a tool result's content: a string, or a list of text parts), up to cap characters."""
    if isinstance(x, str): out.append(x); return len(x)
    n = 0
    if isinstance(x, list):
        for y in x: n += _strings(y, out, cap - n) if n < cap else 0
    elif isinstance(x, dict):
        for y in x.values(): n += _strings(y, out, cap - n) if n < cap else 0
    return n

def shown(transcript_path, deadline):
    """The text of every tool result in the transcript, joined; None when it can't be read in time."""
    p = pathlib.Path(str(transcript_path or ""))
    try:
        if not str(transcript_path or "") or not p.is_file() or p.stat().st_size > MAX_TRANSCRIPT: return None
        parts, n = [], 0
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if time.time() > deadline: return None
                try: j = json.loads(line)
                except ValueError: continue
                if not isinstance(j, dict): continue
                c = (j.get("message") or {}).get("content") if isinstance(j.get("message"), dict) else None
                for item in c if isinstance(c, list) else []:
                    if isinstance(item, dict) and item.get("type") == "tool_result": n += _strings(item.get("content"), parts, MAX_TRANSCRIPT - n)
                if "toolUseResult" in j: n += _strings(j["toolUseResult"], parts, MAX_TRANSCRIPT - n)
        return "\n".join(parts)
    except OSError: return None

def marks(root):
    p = pathlib.Path(root) / ".critic" / "proctor" / "marks.json"
    try: m = json.loads(p.read_text(encoding="utf-8")) if p.is_file() and not p.is_symlink() else {}
    except (OSError, ValueError): return {}
    m = m.get("marks") if isinstance(m, dict) else None
    return {k: str(v.get("what", "")) for k, v in m.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(m, dict) else {}

def check(root, transcript_path, review_name):
    """{"checked": True, "saw": [...]} or {"checked": False, "why": ...}."""
    text = shown(transcript_path, time.time() + BUDGET_S)
    if text is None: return {"checked": False, "why": "no readable transcript"}
    letter = re.fullmatch(r"review-([A-Za-z0-9]+)\.json", str(review_name or ""))
    own = {f"brief-{letter.group(1)}", f"review-{letter.group(1)}.json"} if letter else set()
    return {"checked": True, "saw": sorted({f"the mark of {what}" for mark, what in marks(root).items() if what not in own and mark in text})}
