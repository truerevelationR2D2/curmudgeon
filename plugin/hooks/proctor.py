"""The proctor (03 §5.57 item 35): at a reviewer's stop, its whole transcript (every command's and every read's output)
is checked for what it must never have seen. Two things count:

  marks  Curmudgeon writes a unique mark into every brief, scan report, tally, count and verification packet
         (critic_findings.proctor_mark, listed in .critic/proctor/marks.json, which agents can't read). A mark in a
         reviewer's tool output means it read that file. Its own brief's mark doesn't count.
  text   distinctive text from another reviewer's review file written so far: 48-character pieces of its titles,
         evidence, failing cases and fixes. A piece that also appears in the code it reviewed, in the plugin's
         reference files, in the change map or in its own review isn't distinctive, so it doesn't count.

The result goes in the reviewer's stop record: {"checked": true, "saw": [...]} or {"checked": false, "why": ...}
when the transcript can't be read in time. The merge voids a review whose record lists anything seen.

Only tool results are read: what the agent was shown, never what it typed (a mark can't be guessed). This is a
script; no model judges. Read only; it never changes the transcript or blocks."""
import json, os, pathlib, re, time

PIECE = 48            # characters in one piece of another review's text
MAX_TRANSCRIPT = 64 * 1024 * 1024
MAX_CORPUS = 32 * 1024 * 1024
BUDGET_S = 25         # the stop hook has 60 seconds in all
FIELDS = ("title", "evidence", "failing_case", "remediation", "preconditions", "root_cause")

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
    """The text of every tool result in the transcript, joined; None when it can't be read."""
    p = pathlib.Path(str(transcript_path or ""))
    try:
        if not p.is_file() or p.stat().st_size > MAX_TRANSCRIPT: return None
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

def _texts(path):
    try: v = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return []
    rows = v.get("findings") if isinstance(v, dict) else v
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            out += [str(r[k]) for k in FIELDS if isinstance(r.get(k), str) and len(r[k]) >= PIECE]
    return out

def pieces(s):
    """Up to three pieces of s (start, middle, end), as written and as a JSON file stores it."""
    flat = " ".join(s.split())
    forms = {flat, json.dumps(flat)[1:-1], json.dumps(flat, ensure_ascii=False)[1:-1]}
    out = set()
    for f in forms:
        if len(f) < PIECE: continue
        for at in sorted({0, (len(f) - PIECE) // 2, len(f) - PIECE}): out.add(f[at:at + PIECE])
    return out

def corpus(root, payload, refs, own):
    """Text a reviewer may legitimately have seen and quoted: the code it reviewed, the references, the change map and
    its own review. Read lazily, only when a piece is found."""
    parts, n = [], 0
    files = [pathlib.Path(root) / ".critic" / "change-map.md", pathlib.Path(own)]
    if refs and pathlib.Path(refs).is_dir(): files += sorted(pathlib.Path(refs).rglob("*.md"))
    if payload and pathlib.Path(payload).is_dir():
        for dp, dn, fn in os.walk(payload):
            dn[:] = [d for d in dn if d not in (".git", "node_modules", ".critic")]
            files += [pathlib.Path(dp) / f for f in fn]
    for f in files:
        if n > MAX_CORPUS: break
        try:
            if f.is_file() and not f.is_symlink() and f.stat().st_size < 4 * 1024 * 1024:
                t = f.read_text(encoding="utf-8", errors="replace"); parts.append(t); n += len(t)
        except OSError: pass
    joined = "\n".join(parts)
    return joined + "\n" + " ".join(joined.split())

def check(root, transcript_path, review_name, payload=None, refs=None):
    """{"checked": True, "saw": [...]} or {"checked": False, "why": ...}."""
    deadline = time.time() + BUDGET_S
    text = shown(transcript_path, deadline)
    if text is None: return {"checked": False, "why": "no readable transcript"}
    flat = " ".join(text.split())
    letter = re.fullmatch(r"review-([A-Za-z0-9]+)\.json", str(review_name or ""))
    letter = letter.group(1) if letter else None
    saw = []
    for mark, what in marks(root).items():
        if letter and what == f"brief-{letter}": continue  # its own brief (any round)
        if mark in text: saw.append(f"the mark of {what}")
    rv = pathlib.Path(root) / ".critic" / "reviews"
    own = rv / str(review_name or "")
    common = None
    for other in sorted(rv.glob("review-*.json")) if rv.is_dir() and not rv.is_symlink() else []:
        if other.name == own.name or other.is_symlink(): continue
        if time.time() > deadline: return {"checked": False, "why": "the transcript was too long to check in time"}
        hit = [pc for s in _texts(other) for pc in pieces(s) if pc in text or pc in flat]
        if hit:
            if common is None: common = corpus(root, payload, refs, own)
            if any(pc not in common for pc in hit): saw.append(f"text from {other.name}")
    return {"checked": True, "saw": sorted(set(saw))}
