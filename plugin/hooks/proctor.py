"""The proctor (03 §5.57 item 35): a reviewer's whole transcript (every command's and every read's output) is checked for
what it must never have seen: one of the unique marks Curmudgeon writes into every brief, scan report, tally, count,
dedup list, verification packet and reviewer's review (critic_findings.proctor_mark, listed in
.critic/proctor/marks.json, which agents can't read). A mark in a reviewer's tool output means it read that file. Its
own brief's and its own review's marks don't count.

Only marks count, never similar text: text two honest reviewers both saw (the same test failure, a project rule)
would void one of them (5.5.0 blind round: three reviewers showed it), and precision comes first. The marks go on
every line of a review (one finding per line) and of every scan row, at the top and the bottom of the counts and the
scan's markdown, as the first and last keys of the tally, the dedup list and each packet, and in a brief's own part
(its shared part stays byte-identical across briefs, for prompt caching). A grep of one line elsewhere may miss them;
the guard and the private copy stay the first layers there.

The check runs at the reviewer's stop (its record in .critic/stops/) and again at each tally, against every mark known
by then, so a reviewer that read a review stamped after it stopped is caught too. Only tool results are read: what the
agent was shown, never what it typed (a 96-bit mark can't be guessed). A script; no model judges. It reads only.

It also checks the review itself (03 §5.57 item 40): a passage of 48 characters or more in the reviewer's own prose
that stands in a review another reviewer wrote earlier, and that it never saw (in the project's files, its own brief or
any tool output in its transcript), is flagged as a possible copy: the counts and the teardown name it. It doesn't void
the review, because two honest reviewers wrote the same 48 characters in a real run (5.8.0 measurement). Reviewers
are told this is checked."""
import json, os, pathlib, re, time

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

WRITES = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

def _reads_own(item, own):
    """A Read tool call of .critic/reviews/<own>."""
    fp = str((item.get("input") or {}).get("file_path") or "") if isinstance(item.get("input"), dict) else ""
    return item.get("name") == "Read" and fp.replace("\\", "/").endswith(".critic/reviews/" + own)

def shown(transcript_path, deadline, reads_only=False, own=None):
    """The text of every tool result in the transcript, joined; None when it can't be read in time. With reads_only, the
    results of the agent's own Write and Edit calls are left out: they echo what it typed, which the copy check must
    never count as text it was shown (5.8.0 blind round C1). So are the results of any call that names its own review
    file (own) with the Read tool: reading back what it wrote is not being shown it (5.8.1 C3). Only a Read of that
    file counts: a command that merely mentions the name (a test the reviewer runs) still shows its output (5.8.1
    blind round: that wider rule flagged two honest reviewers)."""
    p = pathlib.Path(str(transcript_path or ""))
    try:
        if not str(transcript_path or "") or not p.is_file() or p.stat().st_size > MAX_TRANSCRIPT: return None
        parts, n, writes = [], 0, set()
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if time.time() > deadline: return None
                try: j = json.loads(line)
                except ValueError: continue
                if not isinstance(j, dict): continue
                c = (j.get("message") or {}).get("content") if isinstance(j.get("message"), dict) else None
                own_write = False
                for item in c if isinstance(c, list) else []:
                    if not isinstance(item, dict): continue
                    if item.get("type") == "tool_use" and (item.get("name") in WRITES or (reads_only and own and _reads_own(item, own))): writes.add(item.get("id"))
                    if item.get("type") == "tool_result":
                        if reads_only and item.get("tool_use_id") in writes: own_write = True; continue
                        n += _strings(item.get("content"), parts, MAX_TRANSCRIPT - n)
                if "toolUseResult" in j and not own_write: n += _strings(j["toolUseResult"], parts, MAX_TRANSCRIPT - n)
        return "\n".join(parts)
    except OSError: return None

def marks(root):
    """{mark: what it marks}; {} when no run has written any; None when the file is there but can't be read (a link,
    bad JSON, the wrong shape), so the check says unchecked rather than "saw nothing" (5.6.0 re-review C5)."""
    p = pathlib.Path(root) / ".critic" / "proctor" / "marks.json"
    if not p.exists() and not p.is_symlink(): return {}
    try: m = json.loads(p.read_text(encoding="utf-8")) if p.is_file() and not p.is_symlink() else None
    except (OSError, ValueError): return None
    m = m.get("marks") if isinstance(m, dict) else None
    return {k: str(v.get("what", "")) for k, v in m.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(m, dict) else None

COPY_MIN = 48          # characters of a passage, after lower-casing and squeezing spaces (03 §5.57 item 40)
SKIP_DIRS = {".critic", ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
MAX_ALLOWED = 32 * 1024 * 1024

def _norm(t): return re.sub(r"\s+", " ", str(t).lower())

PROSE = ("title", "evidence", "failing_case", "remediation", "why", "claim")  # a reviewer's own words; file, line, category and the code quote are shared by design

def _review_text(path):
    """A review's own words, field by field: [squeezed prose strings]; None when it can't be read. Fields are kept apart,
    so two lists of the same file paths, or a quote beside a category, never join into a passage (5.8.0 measurement)."""
    try: rows = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return None
    rows = rows.get("findings", []) if isinstance(rows, dict) else rows
    return [_norm(r[k]) for r in rows if isinstance(r, dict) for k in PROSE if isinstance(r.get(k), str) and len(r[k]) >= COPY_MIN] if isinstance(rows, list) else None

PIECE = 20             # characters: a passage made wholly of pieces this long that the reviewer was allowed to see is no copy (03 §5.57 item 53)

def _references():
    """Curmudgeon's own instructions every reviewer reads: the review skill's references and the agents' prompts, so
    their template words (the sandbox scenario names, say) are text a reviewer was allowed to see (03 §5.57 item 53:
    the Windows acceptance run flagged three honest reviews for them)."""
    here = pathlib.Path(__file__).resolve().parent.parent; out = []
    for f in sorted((here / "skills" / "review" / "references").rglob("*.md")) + sorted((here / "agents").glob("*.md")) + [here / "skills" / "review" / "SKILL.md"]:
        try: out.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError: pass
    return "\n".join(out)

def _explained(g, pool):
    """True when every character of the passage g lies in a piece of at least PIECE characters found in pool: a quote
    of the code followed by the reviewer's own words, or two template phrases side by side, is no copy."""
    covered = [False] * len(g)
    for i in range(len(g) - PIECE + 1):
        if g[i:i + PIECE] in pool:
            for k in range(i, i + PIECE): covered[k] = True
    return all(covered)

def _allowed(root, letter, deadline):
    """What the reviewer was allowed to see, squeezed: the project's own files (its private copy is a copy of them),
    its own brief and Curmudgeon's own instructions. A passage found here is a quote of the code, the brief or the
    instructions, never a copy."""
    root = pathlib.Path(root); parts, n = [_references()], 0
    if letter:
        b = root / ".critic" / "briefs" / f"brief-{letter}.md"
        try: parts.append(b.read_text(encoding="utf-8", errors="replace"))
        except OSError: pass
    for dp, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".critic")]
        for f in files:
            if time.time() > deadline: return None
            if n > MAX_ALLOWED: return _norm("\n".join(parts))  # a very large project: compare against what was read, never give up the check (5.9.2 lite review)
            fp = pathlib.Path(dp) / f
            try:
                if fp.is_symlink() or fp.stat().st_size > 2 * 1024 * 1024: continue
                t = fp.read_bytes()
            except OSError: continue
            if b"\0" in t[:4096]: continue
            parts.append(t.decode("utf-8", errors="replace")); n += len(t)
    return _norm("\n".join(parts))

def _stop_order(root):
    """{review file: the time of its first stop record}, from .critic/stops (the reviewer's own records, by agent)."""
    out = {}
    try: started = float(json.loads((pathlib.Path(root) / ".critic" / "ledger.json").read_text(encoding="utf-8")).get("started_at") or 0)
    except (OSError, ValueError, TypeError, AttributeError): started = 0
    for f in (pathlib.Path(root) / ".critic" / "stops").glob("*.json"):
        try: j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError): continue
        if isinstance(j, dict) and started and float(j.get("at") or 0) < started - 2: continue  # an earlier run's or round's stop never orders this one's reviewers, as the merge already skips them (5.8.1 blind round L7)
        r, at = (j.get("review"), j.get("first_at", j.get("at"))) if isinstance(j, dict) else (None, None)  # first_at: kept by write_stop when a reviewer stops twice (5.8.1)
        if isinstance(r, str) and isinstance(at, (int, float)) and not isinstance(at, bool) and (r not in out or at < out[r]): out[r] = float(at)
    return out

def copied(root, review_name, deadline, seen=""):
    """[what it copied] for 48-character passages in this review's own prose that also stand in the prose of a review
    another reviewer wrote before it (by the files' times), and that the reviewer never saw: not in the project's files,
    its own brief or any tool output in its own transcript (seen). Text it saw itself is either honest (a program's
    output, a vendor file) or carries a run mark, which the mark check catches; what is left came from nowhere, such
    as another review's words pasted into its start message. Only earlier reviews count, so the reviewer who wrote a
    passage first is never the one judged; tally, counts and packets come after the reviews and never count.
    None when it can't be checked in time (03 §5.57 item 40)."""
    rd = pathlib.Path(root) / ".critic" / "reviews"; own = rd / str(review_name or "")
    letter = re.fullmatch(r"review-([A-Za-z0-9]+)\.json", str(review_name or ""))
    if not letter or not own.is_file(): return []
    mine = _review_text(own)
    if not mine: return []
    order = _stop_order(root)
    t_own = order.get(own.name, time.time())  # at its own stop its record isn't written yet: it stops now
    hits, allowed, seen = [], ..., _norm(seen)
    for other in sorted(rd.glob("review-*.json")):
        if other.name == own.name or other.is_symlink(): continue
        t_other = order.get(other.name)
        if t_own is None or t_other is None or t_other >= t_own: continue  # earlier by the first stop record, not the file's time, which the stop hook resets when it stamps marks (5.8.0 blind round C6); a tie judges neither
        grams = set()
        for t in _review_text(other) or []:
            if time.time() > deadline: return None  # 5.8.0 blind round C3
            grams.update(t[i:i + COPY_MIN] for i in range(len(t) - COPY_MIN + 1))
        shared = set()
        for m in mine:
            if time.time() > deadline: return None
            shared.update(g for g in (m[i:i + COPY_MIN] for i in range(len(m) - COPY_MIN + 1)) if g in grams and g not in seen)
        if not shared: continue
        if allowed is ...: allowed = _allowed(root, letter.group(1), deadline)
        if allowed is None: return None
        pool = allowed + " " + seen
        if any(g not in allowed and not _explained(g, pool) for g in shared): hits.append(f"a {COPY_MIN}-character passage of {other.name} it never saw")
    return hits

def check(root, transcript_path, review_name):
    """{"checked": True, "saw": [...]} or {"checked": False, "why": ...}."""
    deadline = time.time() + BUDGET_S
    text = shown(transcript_path, deadline)
    if text is None: return {"checked": False, "why": "no readable transcript"}
    letter = re.fullmatch(r"review-([A-Za-z0-9]+)\.json", str(review_name or ""))
    own = {f"brief-{letter.group(1)}", f"review-{letter.group(1)}.json"} if letter else set()
    known = marks(root)
    if known is None: return {"checked": False, "why": "the run's marks can't be read"}
    saw = {f"the mark of {what}" for mark, what in known.items() if what not in own and mark in text}
    reads = shown(transcript_path, deadline, reads_only=True, own=str(review_name or "") or None)
    cp = copied(root, review_name, deadline, reads) if reads is not None else None
    if cp is None and not saw: return {"checked": False, "why": "the copy check couldn't finish in time"}  # never "no copy" (5.8.0 blind round C2); a mark it saw still voids it below
    return {"checked": True, "saw": sorted(saw), "copied": sorted(cp or [])}  # copied is flagged, not voided: honest reviewers write the same 48 characters too (5.8.0 measurement)
