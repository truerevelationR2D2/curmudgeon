#!/usr/bin/env python3
"""Shared finding format for every Curmudgeon script: stable fingerprints, the quote check, JSONL and SARIF.

A finding is a dict:
  id (stable, from the fingerprint), category, impact (Critical|High|Medium|Low), file, line, quote (the exact code
  or text the finding is about), title, evidence, failing_case, verified (executed|traced|inferred), remediation,
  source (reviewer name, "scan", or a tool), votes (filled by the tally)."""
import hashlib, json, pathlib, re, time, os, sys

IMPACTS = ("Critical", "High", "Medium", "Low")
VERIFIED = ("executed", "traced", "inferred")
CODE_EXT = (".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".html", ".htm", ".css", ".scss", ".vue", ".svelte", ".go", ".rb", ".php", ".java", ".cs", ".rs", ".sh", ".json", ".md")

def safe_int(v):
    """Line numbers arrive as 12, "12", "12-14" or junk: take the first number, else 0. Never raises."""
    m = re.match(r"\s*(\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else 0

STOP = set("a an the of to in on at for and or is are be it its this that with without by from as not no into".split())

def norm_code(s):
    """Whitespace- and quote-insensitive form of a code snippet."""
    return re.sub(r"\s+", " ", str(s or "")).replace("'", '"').strip().lower()

def tokens(s):
    return {w for w in re.findall(r"[a-z0-9_]+", str(s or "").lower()) if w not in STOP and len(w) > 2}

def fingerprint(f):
    """Stable across runs and rewordings: file + category + the normalised quote (or the title words when no quote)."""
    key = norm_code(f.get("quote")) or " ".join(sorted(tokens(f.get("title"))))
    if f.get("source") == "scan" and not f.get("quote"): key += f"|line {f.get('line') or 0}"  # two keys of one kind in a file are two findings
    raw = f"{str(f.get('file') or '').lower()}|{str(f.get('category') or '').lower()}|{key}"
    return "F-" + hashlib.sha1(raw.encode()).hexdigest()[:8]

def similar(a, b):
    """Same issue? Same file, and either the quotes overlap or the titles share most words, and lines are close."""
    if str(a.get("file") or "").lower() != str(b.get("file") or "").lower(): return False
    ta, tb = tokens(a.get("title")) | tokens(a.get("category")), tokens(b.get("title")) | tokens(b.get("category"))
    jac = len(ta & tb) / max(1, len(ta | tb))
    same_kind = str(a.get("category") or "").lower() == str(b.get("category") or "").lower() or jac >= 0.25
    qa, qb = norm_code(a.get("quote")), norm_code(b.get("quote"))
    if qa and qb and (qa in qb or qb in qa) and same_kind: return True  # same code, same kind of problem
    close = abs(safe_int(a.get("line")) - safe_int(b.get("line"))) <= 5
    return jac >= 0.5 and close or jac >= 0.7

def quote_check(f, root):
    """True when the quote appears (normalised) within 5 lines of file:line. No quote, no file: can't be checked."""
    q = norm_code(f.get("quote"))
    if not q or not f.get("file"): return None
    p = pathlib.Path(root) / f["file"]
    try: lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError: return False
    ln = safe_int(f.get("line"))
    lo, hi = (max(0, ln - 6), min(len(lines), ln + 5)) if ln else (0, len(lines))
    window = norm_code("\n".join(lines[lo:hi]))
    if q in window: return True
    # long quotes may span the window edge: accept when every quote line is in the file near the line
    parts = [norm_code(x) for x in str(f.get("quote")).split("\n") if x.strip()]
    whole = [norm_code(x) for x in lines[max(0, lo - 10):hi + 10]]
    return bool(parts) and all(any(p_ in w for w in whole) for p_ in parts)

def read_jsonl(path):
    out = []
    p = pathlib.Path(path)
    if not p.exists(): return out
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except json.JSONDecodeError as e: raise ValueError(f"{path}:{i}: not JSON ({e})")
    return out

def write_jsonl(path, rows):
    p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp"); tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"); tmp.replace(p)

def extract_findings(text):
    """Pull finding objects out of an agent reply: a ```json block holding a list, or JSONL lines."""
    rows = []
    for blk in re.findall(r"```(?:json|jsonl)?\s*\n(.*?)```", text, re.S):
        blk = blk.strip()
        try:
            v = json.loads(blk); rows += v if isinstance(v, list) else [v]; continue
        except json.JSONDecodeError: pass
        for line in blk.splitlines():
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    return [r for r in rows if isinstance(r, dict)]

def validate(f):
    """Return a list of problems with one finding (empty when it meets the contract)."""
    errs = []
    if f.get("impact") not in IMPACTS: errs.append("impact must be Critical, High, Medium or Low")
    for k in ("category", "title", "file"):
        if not f.get(k): errs.append(f"missing {k}")
    if f.get("impact") in ("Critical", "High", "Medium"):
        for k in ("evidence", "failing_case"):
            if not str(f.get(k) or "").strip(): errs.append(f"missing {k} (no case, no finding)")
    if f.get("verified") not in VERIFIED: errs.append("verified must be executed, traced or inferred")
    if f.get("source") != "scan" and f.get("impact") in ("Critical", "High", "Medium") and str(f.get("file") or "").lower().endswith(CODE_EXT) and safe_int(f.get("line")) and not str(f.get("quote") or "").strip():
        # scanner rows are exempt: they come from the scan's own match, and quoting the line would copy a found secret into the reports
        errs.append("missing quote: a finding about a line of a file must quote it exactly, so the quote check can confirm it exists")
    return errs

LOCATION = re.compile(r"([\w./-]+\.\w+):(\d+)")
HEDGE = re.compile(r"(?i)\b(i (?:do not|don't) think|i think|i believe|i guess|i assume|i suspect|i doubt|presumably|apparently|supposedly|seems?|probably|maybe|perhaps|possibly|unlikely|not sure|unclear|afaict|as far as i (?:can )?(?:tell|know|see)|likely (?:fine|ok|safe)|looks? (?:fine|ok|safe)|should be (?:fine|ok|safe))\b")
def refutation_problem(why, impact, reproduced, root=None):
    """One rule for what may drop a finding, shared by the verifier's stop check and apply. A refutation must state the
    guard as fact (no hedging), run to at least 60 characters, come from a run or a trace, and cite the guard as a
    file:line that exists (checked against root when given). A platform rule is cited at the line that relies on it.
    Returns None when the refutation is concrete. Errs toward keeping the finding. A Critical needs an executed run.
    A pattern check can't tell whether the cited line really is the guard; the verifier's brief and the default of
    "not a defect unless reproduced" carry that part."""
    why = str(why or "").replace("\u2019", "'").replace("\u2018", "'")
    if len(why) < 60: return "too short (at least 60 characters: a full sentence naming the guard)"
    if HEDGE.search(why): return "hedged (doubt is not a refutation: state the guard as fact, or return unclear)"
    if str(reproduced or "") not in ("executed", "traced"): return "needs a run or a trace (reproduced: executed or traced)"
    if impact == "Critical" and str(reproduced) != "executed": return "refuting a Critical needs a run (reproduced: executed), not only a trace"
    locs = LOCATION.findall(why)
    if not locs: return "no location (cite the guard, or the line that relies on a platform rule, as file:line)"
    if root is not None:
        rt = pathlib.Path(root).resolve()
        def exists(f, n):  # a project file under the root, never the plugin's own .critic/ records
            if f.startswith("/") or ".." in pathlib.PurePath(f).parts or ".critic" in pathlib.PurePath(f).parts: return False
            p = (rt / f).resolve()
            try: return p.is_relative_to(rt) and p.is_file() and 1 <= int(n) <= len(p.read_text(encoding="utf-8", errors="replace").split("\n"))
            except (OSError, ValueError): return False
        if not any(exists(f, n) for f, n in locs): return "the cited file:line does not exist"
    return None

SARIF_LEVEL = {"Critical": "error", "High": "error", "Medium": "warning", "Low": "note"}
def to_sarif(findings, tool="critic", version="4.0.0"):
    rules, results = {}, []
    for f in findings:
        rid = str(f.get("category") or "finding")
        rules.setdefault(rid, {"id": rid, "shortDescription": {"text": rid}})
        loc = {"physicalLocation": {"artifactLocation": {"uri": f.get("file") or ""}, "region": {"startLine": max(1, safe_int(f.get("line")) or 1)}}}
        results.append({"ruleId": rid, "level": SARIF_LEVEL.get(f.get("impact"), "note"), "message": {"text": f.get("title", "")},
                        "locations": [loc], "partialFingerprints": {"criticId": f.get("id") or fingerprint(f)},
                        "properties": {"impact": f.get("impact"), "verified": f.get("verified"), "votes": f.get("votes")}})
    return {"version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": tool, "version": version, "rules": list(rules.values())}}, "results": results}]}

def state_links(root):
    """Links inside .critic/ (or .critic itself being one) would let a cloned repository point the plugin's writes at
    files outside the project. Returns what's wrong; scripts refuse to run until it's empty."""
    d = pathlib.Path(root) / ".critic"
    if d.is_symlink(): return [".critic itself is a link"]
    if not d.is_dir(): return []
    bad = []
    for p in d.rglob("*"):
        if p.is_symlink(): bad.append(str(p.relative_to(root)))
        if len(bad) >= 5: break
    return bad

def refuse_linked_state(root):
    bad = state_links(root)
    if bad:
        what = ".critic itself is a link" if "itself" in bad[0] else ", ".join(bad) + (" is a link" if len(bad) == 1 else " are links") + " inside .critic/"
        print(f"critic: refusing to run: {what}. A link there could make the plugin write to files outside this project. Remove the link(s), then rerun.", file=sys.stderr)
        sys.exit(2)

def append_line(path, line):
    """Append without ever following a link at the target (O_NOFOLLOW)."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as fh: fh.write(line)

_VAL = r"""("[^"]*"|'[^']*'|[^\s"'&;|]+)"""
_NAME = r"[\w.-]*(?:secret|token|passw(?:or)?d|pwd|api[_-]?key|private[_-]?key|access[_-]?key|auth|credential|cookie|session)[\w.-]*"
SECRET_IN_TEXT = re.compile(
    r"(?i)(\b(?:bearer|basic|token)\s+)([A-Za-z0-9._~+/=-]{8,})"          # Authorization: Bearer xxx / Basic xxx
    r"|(\b" + _NAME + r"\s*[=:]\s*(?:(?:bearer|basic|token)\s+)?)" + _VAL +                          # NAME=value, NAME: value (env vars, headers, config)
    r"|(--?" + _NAME + r"(?:=|\s+))" + _VAL +                          # --password value, --api-key=value
    r"|(\bcookie:\s*)([^\"']+)"                                       # Cookie: header
    r"|(?<=://)([^/\s:@]+):([^@\s/]+)@"                                    # user:password@ in URLs
    r"|(\s-u\s+)([^\s:]+):(\S+)"                                           # curl -u user:password
    r"|(\s-p)(\S+)"                                                        # mysql -pPASSWORD
    r"|\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{4,}"                               # JWTs
    r"|\b(?:sk|rk|pk)_(?:live|test)_\w{8,}|\bsk-[\w-]{20,}|\bgh[pousr]_\w{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abposr]-[\w-]{10,}|\bAIza[\w-]{30,}")
def redact_secrets(text):
    """Mask credentials in anything written to a log: auth headers, NAME=value and --name value secrets, cookies,
    user:password@ in URLs, curl -u, mysql -p, JWTs and common provider key shapes. A plain word after "token" (as
    in `pytest -k "token and not slow"`) is left alone: only an assignment, a flag value or a header is masked."""
    def keepq(v):  # keep the quotes, mask the inside
        return v[0] + "[redacted]" + v[-1] if len(v) > 1 and v[0] in "\"'" and v[-1] == v[0] else "[redacted]"
    def sub(m):
        g = m.groups()
        if g[0] is not None: return g[0] + "[redacted]"
        if g[2] is not None: return g[2] + keepq(g[3])
        if g[4] is not None: return g[4] + keepq(g[5])
        if g[6] is not None: return g[6] + "[redacted]"
        if g[8] is not None: return f"{g[8]}:[redacted]@"
        if g[10] is not None: return f"{g[10]}{g[11]}:[redacted]"
        if g[13] is not None: return g[13] + "[redacted]"
        return m.group(0)[:4] + "[redacted]"
    return SECRET_IN_TEXT.sub(sub, text)

RUNLOG_MAX = 1_000_000
def log_run(root, what, detail=""):
    """Append one line to .critic/runlog.jsonl: every script the plugin starts and every outside command it runs, so a
    user can see exactly what ran on their machine. Never fails the caller; trims itself past about 1 MB."""
    try:
        d = pathlib.Path(root) / ".critic"; d.mkdir(exist_ok=True)
        p = d / "runlog.jsonl"
        line = json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "what": what, "detail": redact_secrets(str(detail))[:400]}, ensure_ascii=False) + "\n"
        if p.is_symlink() or state_links(root): return  # never write through a link
        if p.exists() and p.stat().st_size > RUNLOG_MAX:
            with open(p, "rb") as fh:  # read only the tail, never the whole file
                fh.seek(max(0, p.stat().st_size - RUNLOG_MAX // 2)); tail = fh.read()
            keep = tail.decode("utf-8", errors="replace").splitlines(True)[1:]  # drop the partial first line
            tmp = p.with_name(p.name + ".tmp"); tmp.write_text("".join(keep), encoding="utf-8"); os.replace(tmp, p)
        gi = d / ".gitignore"
        if not gi.exists(): gi.write_text("# Curmudgeon's local logs: never commit them\nrunlog.jsonl\nrefutations.jsonl\nspotcheck.md\nrestore/\n", encoding="utf-8")
        append_line(p, line)
    except Exception: pass

