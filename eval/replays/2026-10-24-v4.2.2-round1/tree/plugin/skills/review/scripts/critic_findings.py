#!/usr/bin/env python3
"""Shared finding format for every Curmudgeon script: stable fingerprints, the quote check, JSONL and SARIF.

A finding is a dict:
  id (stable, from the fingerprint), category, impact (Critical|High|Medium|Low), file, line, quote (the exact code
  or text the finding is about), title, evidence, failing_case, verified (executed|traced|inferred), remediation,
  source (reviewer name, "scan", or a tool), votes (filled by the tally)."""
import hashlib, json, pathlib, re, subprocess, time, os, sys

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

def relocate_quote(f, root):
    """For an outside reviewer whose viewer numbered lines differently: the line where a long quote appears, when it
    appears on exactly one line of the file; otherwise None. A short or repeated quote is never moved."""
    q = norm_code(f.get("quote"))
    if len(q) < 20 or "\n" in str(f.get("quote") or "").strip() or not f.get("file"): return None
    try: lines = (pathlib.Path(root) / f["file"]).read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError: return None
    hits = [i + 1 for i, l in enumerate(lines) if q in norm_code(l)]
    return hits[0] if len(hits) == 1 else None

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

_VAL = r"""("[^"]*"|'[^']*'|[^\s"'&;|<>]+)"""  # a shell redirect is never a value
# A secret-bearing name. Strong words count anywhere in a name, run together or camelCase (PGPASSWORD, dbPassword,
# accessToken, clientSecret, _authToken). Weak words count only as a whole _/./- segment (DB_PASS, x-pw, my.pwd), so
# author, bypass and session-dir stay readable. Bounded repeats keep it fast on long hyphenated text.
_STRONG = r"passw(?:or)?d|secret|api[_-]?key|apikey|private[_-]?key|access[_-]?key|credentials?|authorization|sessid|session[_-]?(?:id|key|token)|cookies?"
_WEAK = r"pass|pwd|pw|auth|token|session|sess"
# A whole name: a strong word anywhere (PGPASSWORD, dbPassword, clientSecret, _authToken via "token" below), or a weak
# word as a whole _/./- segment (DB_PASS, SESSION, x-pw). "token" is strong only when it ends the name (accessToken,
# AUTH_TOKEN, --api-token), so --max-tokens and --tokenizer stay readable; a weak word followed by type, mode, dir,
# file, through or stdin names a setting, not a secret (--auth-type, --password-stdin).
_NOT_SECRET_TAIL = r"(?![_.-]?(?:type|mode|dir|file|path|through|stdin|method|scheme|header|check|count|limit)s?(?![\w.-]))"
_NAME_BODY = (r"(?:[A-Za-z0-9_.-]{0,40}(?:" + _STRONG + r")[A-Za-z0-9_.-]{0,40}"
              r"|[A-Za-z0-9_.-]{0,40}(?:[Tt]oken|TOKEN)"
              r"|(?:[A-Za-z0-9]{1,40}[_.-]){0,4}(?:" + _WEAK + r")" + _NOT_SECRET_TAIL + r"(?:[_.-][A-Za-z0-9]{1,40}){0,4})(?![\w.-])")
_NAME = r"(?<![\w.-])" + _NAME_BODY
_CRED = r"(?=[A-Za-z0-9._~+/=-]{8,})(?=[A-Za-z0-9._~+/=-]*[0-9+/=_~.-])[A-Za-z0-9._~+/=-]+"  # 8+ chars with a digit or symbol: not a plain word
REDACT_RULES = [  # applied in order; each masks the value and keeps the label
    (re.compile(r"(?i)(\bcookie:\s*)([^\"'\n]+)"), lambda m: m.group(1) + "[redacted]"),                       # the whole Cookie header
    (re.compile(r"(?i)(\s(?:-b|--cookie)[=\s]\s*)" + _VAL), None),                                                # curl -b / --cookie value
    (re.compile(r"(?i)(\b(?:bearer|basic)\s+)(" + _CRED + ")"), lambda m: m.group(1) + "[redacted]"),          # Authorization: Bearer xxx
    (re.compile(r"(?i)(" + _NAME + r"[\"']?\s*[=:]\s*(?:(?:bearer|basic|token)\s+)?)" + _VAL), None),        # NAME=value, "password": "x", headers
    (re.compile(r"(?i)((?<![\w-])--?" + _NAME_BODY + r"(?:=|\s+))" + _VAL), None),                                          # --password value, --api-key=value
    (re.compile(r"(?<=://)([^/\s:@]+):([^@\s/]+)@"), lambda m: m.group(1) + ":[redacted]@"),                  # user:password@ in URLs
    (re.compile(r"(?i)(\bhttps?://)([^/\s:@]{8,})@"), lambda m: m.group(1) + "[redacted]@"),                  # token@ in web URLs (ssh user@ stays)
    (re.compile(r"(?i)([?&](?:x-(?:amz|goog)-signature|x-amz-credential|signature|sig)=)([^&\s\"'#]+)"), lambda m: m.group(1) + "[redacted]"),  # signed URLs
    (re.compile(r"(\s-u\s+)([^\s:]+):(\S+)"), lambda m: f"{m.group(1)}{m.group(2)}:[redacted]"),             # curl -u user:password
    (re.compile(r"(?i)(\b(?:mysql\w*|mariadb\w*)\b[^|;&\n]{0,200}?\s-p)(\S+)"), lambda m: m.group(1) + "[redacted]"),  # mysql -pPASSWORD
    (re.compile(r"(?i)(\bsshpass\s+-p\s*)(\S+)"), lambda m: m.group(1) + "[redacted]"),
    (re.compile(r"(?i)(\bredis-cli\b[^|;&\n]{0,200}?\s-a\s+)(\S+)"), lambda m: m.group(1) + "[redacted]"),
    (re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{4,}|\b(?:sk|rk|pk)_(?:live|test)_\w{8,}|\bsk-[\w-]{20,}|\bgh[pousr]_\w{20,}"
                r"|\bAKIA[0-9A-Z]{16}\b|\bxox[abposr]-[\w-]{10,}|\bAIza[\w-]{30,}"), lambda m: m.group(0)[:4] + "[redacted]"),  # JWTs and provider key shapes
]
def redact_secrets(text):
    """Mask credentials in anything written to a log: auth headers, NAME=value, "name": "value" and --name value
    secrets (passwords, tokens, keys, signed-URL signatures), cookies, user:password@ and token@ in URLs, curl -u,
    mysql -p, sshpass -p, redis-cli -a, JWTs and common provider key shapes. Ordinary words stay readable: `pytest -k
    "token production path"`, `--author=bob`, `--session-dir x` and `gcc -pthread` are left alone."""
    def keepq(v):  # keep the quotes, mask the inside
        return v[0] + "[redacted]" + v[-1] if len(v) > 1 and v[0] in "\"'" and v[-1] == v[0] else "[redacted]"
    text = str(text)
    for rx, fn in REDACT_RULES:
        text = rx.sub(fn or (lambda m: m.group(1) + keepq(m.group(2))), text)
    return text

FINDING_TEXT = ("quote", "title", "evidence", "failing_case", "remediation", "note", "refutation", "summary", "what")
def redact_finding_text(text):
    """Mask secrets in a finding's words before they are stored: every provider key shape and generic credential the
    secret scan knows (scan_secrets), then the log rules above. The quote check always runs on the raw text first, and
    ids are computed from it, so masking never retracts a finding or changes its id."""
    text = str(text)
    try:
        import scan_secrets
        spans = sorted(scan_secrets.secret_spans(text))
        out, last = [], 0
        for a, b in spans:
            if b <= last: continue
            a = max(a, last); out.append(text[last:a]); out.append(scan_secrets.mask(text[a:b])); last = b
        text = "".join(out) + text[last:]
    except ImportError: pass
    return redact_secrets(text)

def scrub(obj):
    """A copy of findings (or anything holding them) with every finding text field masked. A finding whose quote was
    masked is marked quote_redacted, so later steps never treat the masked quote as code to look for."""
    if isinstance(obj, list): return [scrub(x) for x in obj]
    if not isinstance(obj, dict): return obj
    out = {}
    for k, v in obj.items():
        if k in FINDING_TEXT and isinstance(v, str):
            out[k] = redact_finding_text(v)
            if k == "quote" and out[k] != v: out["quote_redacted"] = True
        else: out[k] = scrub(v)
    return out

RUNLOG_MAX = 1_000_000
# Local state that must never be committed: logs, restore copies, and the files that hold reviewers' raw quotes (a
# quote can contain a secret from the code under review; the outputs Curmudgeon writes itself are masked by scrub()).
IGNORED = ("runlog.jsonl", "refutations.jsonl", "spotcheck.md", "restore/", "reviews/", "history/", "outside/", "verify/",
           "tally.json", "dedup-candidates.json", "findings-import.jsonl")
_TRACKED = {}
def git_tracked(root, rel):
    """True when the repository tracks this file: ignore rules don't apply to a tracked file, so anything written to
    it would show up in the next commit. Asked once per process and file; not logged (it is the log's own check)."""
    key = (str(root), rel)
    if key not in _TRACKED:
        try:
            r = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=root, capture_output=True, timeout=5)
            _TRACKED[key] = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired): _TRACKED[key] = False
    return _TRACKED[key]

def runlog_tracked(root):
    t = git_tracked(root, ".critic/runlog.jsonl")
    if t and ("runlog", str(root)) not in _TRACKED:
        _TRACKED[("runlog", str(root))] = True
        print("curmudgeon: .critic/runlog.jsonl is tracked by git in this repository, so the run log is not written (it would go into "
              "your next commit). To keep a log, run: git rm --cached .critic/runlog.jsonl", file=sys.stderr)
    return t

def ensure_ignored(d):
    """.critic/.gitignore lists the local logs; missing entries are added to an existing file, never through a link and
    never to a file the repository tracks (that edit would land in the owner's next commit: they are told instead)."""
    gi = d / ".gitignore"
    if gi.is_symlink(): return
    have = gi.read_text(encoding="utf-8", errors="replace").splitlines() if gi.exists() else []
    missing = [x for x in IGNORED if x not in (h.strip() for h in have)]
    if not missing: return
    if gi.exists() and git_tracked(d.parent, ".critic/.gitignore"):
        if ("gitignore", str(d)) not in _TRACKED:
            _TRACKED[("gitignore", str(d))] = True
            print(f"curmudgeon: .critic/.gitignore is tracked by git, so it was left alone; add these lines to it yourself: {', '.join(missing)}", file=sys.stderr)
        return
    head = "" if have else "# Curmudgeon's local logs: never commit them\n"
    sep = "\n" if have and not gi.read_text(encoding="utf-8", errors="replace").endswith("\n") else ""
    with open(gi, "a", encoding="utf-8") as fh: fh.write(sep + head + "".join(x + "\n" for x in missing))

def log_run(root, what, detail=""):
    """Append one line to .critic/runlog.jsonl: every script the plugin starts and every outside command it runs, so a
    user can see exactly what ran on their machine. Never fails the caller; trims itself past about 1 MB."""
    try:
        d = pathlib.Path(root) / ".critic"; d.mkdir(exist_ok=True)
        p = d / "runlog.jsonl"
        line = json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "what": what, "detail": redact_secrets(str(detail)[:4000])[:400]}, ensure_ascii=False) + "\n"
        if p.is_symlink() or state_links(root): return  # never write through a link
        if runlog_tracked(root): return
        if p.exists() and p.stat().st_size > RUNLOG_MAX:
            with open(p, "rb") as fh:  # read only the tail, never the whole file
                fh.seek(max(0, p.stat().st_size - RUNLOG_MAX // 2)); tail = fh.read()
            keep = tail.decode("utf-8", errors="replace").splitlines(True)[1:]  # drop the partial first line
            tmp = p.with_name(p.name + ".tmp"); tmp.write_text("".join(keep), encoding="utf-8"); os.replace(tmp, p)
        ensure_ignored(d)
        append_line(p, line)
    except Exception: pass

