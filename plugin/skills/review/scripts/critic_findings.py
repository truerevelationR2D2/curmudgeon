#!/usr/bin/env python3
"""Shared finding format for every Curmudgeon script: stable fingerprints, the quote check, JSONL and SARIF.

A finding is a dict:
  id (stable, from the fingerprint), category, impact (Critical|High|Medium|Low), file, line, quote (the exact code
  or text the finding is about), title, evidence, failing_case, verified (executed|traced|inferred), remediation,
  source (reviewer name, "scan", or a tool), votes (filled by the tally)."""
import hashlib, json, pathlib, re, subprocess, time, os, sys

IMPACTS = ("Critical", "High", "Medium", "Low")  # the counted levels: the verdict, the ledger and SARIF use only these
NIT = "Nit"  # SC-79: below Low; listed under Nits, never counted, never verified, never blocking
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

def fingerprint2(f):
    """A second fingerprint without the category (SC-39, after PR-Agent's two-key matching; our own code): file plus the
    normalised quote. The same bug filed under another category keeps its history. None without a usable quote."""
    q = norm_code(f.get("quote"))
    if len(q) < 12 or "[redacted]" in q: return None
    return "Q-" + hashlib.sha1(f"{str(f.get('file') or '').lower()}|{q}".encode()).hexdigest()[:8]

def similar(a, b):
    """Same issue? Same file, and either the quotes overlap or the titles share most words, and lines are close."""
    if str(a.get("file") or "").lower() != str(b.get("file") or "").lower(): return False
    ta, tb = tokens(a.get("title")) | tokens(a.get("category")), tokens(b.get("title")) | tokens(b.get("category"))
    jac = len(ta & tb) / max(1, len(ta | tb))
    same_kind = str(a.get("category") or "").lower() == str(b.get("category") or "").lower() or jac >= 0.25
    qa, qb = norm_code(a.get("quote")), norm_code(b.get("quote"))
    close = abs(safe_int(a.get("line")) - safe_int(b.get("line"))) <= 5
    short = min(len(qa), len(qb))
    if qa and qb and (qa in qb or qb in qa) and same_kind and short >= 12 and (short >= 30 or abs(safe_int(a.get("line")) - safe_int(b.get("line"))) <= 15):
        return True  # same code, same kind of problem: a long quote wherever it is cited, a short one only nearby
    for s_, o_ in ((a, b), (b, a)):  # a reviewer restating a scripted row: the row's flagged line is in the reviewer's quote
        if s_.get("source") == "scan" and o_.get("source") != "scan" and close:
            seen_, q_ = norm_code(s_.get("failing_case")), norm_code(o_.get("quote"))
            if len(seen_) >= 6 and q_ and (seen_ in q_ or q_ in seen_): return True
    return jac >= 0.5 and close or jac >= 0.7

def quote_text(s):
    """A quote as the quote check compares it: runs of spaces and tabs made one space, ends trimmed. Case and quote marks
    are kept (§5.56): `Foo` is not `foo`, and 'a' is not "a"."""
    return re.sub(r"\s+", " ", str(s or "")).strip()

QUOTE_MIN = 12  # characters, after quote_text: shorter quotes (";", "return") are found almost anywhere

def quote_problem(q):
    """Why a quote is too weak for the quote check to mean anything, or None (§5.56: at least 12 characters, with a name in them)."""
    t = quote_text(q)
    if len(t) < QUOTE_MIN: return f"quote too short to check ({len(t)} characters): quote at least {QUOTE_MIN} characters of the line, exactly as written"
    if not re.search(r"[^\W\d]\w", t): return "quote has no name or word in it: quote the part of the line that names what is wrong"
    return None

def _quote_at(lines, want, i):
    """True when the quote lines `want` (already quote_text) start on lines[i] and go on, in order, over the next
    non-blank lines (blank lines between them are skipped)."""
    if not (0 <= i < len(lines)) or not lines[i].strip(): return False
    src = [quote_text(x) for x in lines[i:i + 4 * len(want) + 40] if x.strip()]
    return len(src) >= len(want) and all(w in s_ for w, s_ in zip(want, src))

def _quote_lines(q): return [quote_text(x) for x in str(q or "").split("\n") if x.strip()]

def quote_check(f, root):
    """True when the quote is at file:line (§2 invariant 3, made strict by §5.56): its first line starts on the cited line
    or one either side (an off-by-one), and each further line of a multi-line quote is on the next non-blank line, in
    order. Case and quote marks count; only runs of whitespace are evened out. A quote at line 0 is never confirmed.
    No quote or no file: None (nothing to check)."""
    q = str(f.get("quote") or "")
    if not q.strip() or not f.get("file"): return None
    p = pathlib.Path(root) / f["file"]
    try: lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError: return False
    ln = safe_int(f.get("line"))
    if ln < 1: return False
    want = _quote_lines(q)
    return any(_quote_at(lines, want, i) for i in (ln - 1, ln - 2, ln))

def relocate_quote(f, root):
    """For an outside reviewer whose viewer numbered lines differently: the line where a long quote appears, when it
    appears on exactly one line of the file; otherwise None. A short or repeated quote is never moved."""
    q = quote_text(f.get("quote"))  # case and quote marks count here too (§5.56)
    if len(q) < 20 or "\n" in str(f.get("quote") or "").strip() or not f.get("file"): return None
    try: lines = (pathlib.Path(root) / f["file"]).read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError: return None
    hits = [i + 1 for i, l in enumerate(lines) if q in quote_text(l)]
    return hits[0] if len(hits) == 1 else None

def find_quote(f, root):
    """Every line where the quote starts, compared as the quote check compares it (any length, multi-line in order):
    for critic_ledger.py fresh, which asks whether reviewed code has moved, not whether a citation was exact."""
    q = str(f.get("quote") or "")
    if not q.strip() or not f.get("file"): return []
    try: lines = (pathlib.Path(root) / f["file"]).read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError: return []
    want = _quote_lines(q)
    return [i + 1 for i in range(len(lines)) if want and want[0] in quote_text(lines[i]) and _quote_at(lines, want, i)]

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
    if f.get("impact") not in IMPACTS + (NIT,): errs.append("impact must be Critical, High, Medium, Low or Nit")
    for k in ("category", "title", "file"):
        if not f.get(k): errs.append(f"missing {k}")
    if f.get("impact") in ("Critical", "High", "Medium"):
        for k in ("evidence", "failing_case"):
            if not str(f.get(k) or "").strip(): errs.append(f"missing {k} (no case, no finding)")
    if f.get("verified") not in VERIFIED: errs.append("verified must be executed, traced or inferred")
    if "difficulty" in f and f["difficulty"] not in ("Low", "Medium", "High"): errs.append("difficulty must be Low, Medium or High (audit mode: how hard the failure is to trigger)")
    for k in ("exploit_scenario", "fix_short", "fix_long"):  # optional, audit mode (after Trail of Bits' report format)
        if k in f and not isinstance(f[k], str): errs.append(f"{k} must be text when given")
    if "requirement" in f:  # optional (SC-55): the requirement the finding rests on, stated (with where) or inferred (with why)
        r = f["requirement"]
        if not isinstance(r, dict) or r.get("basis") not in ("stated", "inferred"): errs.append("requirement must be an object with basis stated or inferred")
        elif r["basis"] == "stated" and not LOCATION.search(str(r.get("where") or "")): errs.append("a stated requirement needs where: the file:line that states it")
        elif r["basis"] == "inferred" and not str(r.get("why") or "").strip(): errs.append("an inferred requirement needs why: what it was inferred from")
    for k in ("preconditions", "root_cause"):  # optional (SC-61): what the failure needs, and the decision behind the bug
        if k in f and not isinstance(f[k], str): errs.append(f"{k} must be text when given")
    if f.get("source") != "scan" and str(f.get("quote") or "").strip() and f.get("impact") != NIT:  # §5.56: a quote the check can't place, or one too weak to mean anything, proves nothing
        if safe_int(f.get("line")) < 1: errs.append("a quoted finding needs its line number (1 or more): the quote check looks for the quote at that line")
        qp = quote_problem(f.get("quote"))
        if qp and "[redacted]" not in str(f.get("quote")): errs.append(qp)
    if f.get("source") != "scan" and f.get("impact") in ("Critical", "High", "Medium") and str(f.get("file") or "").lower().endswith(CODE_EXT) and safe_int(f.get("line")) and not str(f.get("quote") or "").strip():
        # scanner rows are exempt: they come from the scan's own match, and quoting the line would copy a found secret into the reports
        errs.append("missing quote: a finding about a line of a file must quote it exactly, so the quote check can confirm it exists")
    return errs

def verdict_required(tier, f, contested=False):
    """Whether a finding's packet must have a verifier's verdict in this tier (SKILL.md step 4.2; §5.56). Every tier: a
    contested finding, one only the outside reviewer raised, and one whose reviewers disagreed on its impact. Full: every
    packet. Lite: Critical and High. Trivial: nothing more. critic_run.py asks for these; apply marks the run DEGRADED
    when one has no verdict."""
    if contested or f.get("outside_only") or f.get("impact_split"): return True
    if tier == "trivial": return False
    if tier == "lite": return f.get("impact") in ("Critical", "High")
    return True

LOCATION = re.compile(r"([\w./-]+\.\w+):(\d+)")
HEDGE = re.compile(r"(?i)\b(i (?:do not|don't) think|i think|i believe|i guess|i assume|i suspect|i doubt|presumably|apparently|supposedly|seems?|probably|maybe|perhaps|possibly|unlikely|not sure|unclear|afaict|as far as i (?:can )?(?:tell|know|see)|likely (?:fine|ok|safe)|looks? (?:fine|ok|safe)|should be (?:fine|ok|safe))\b")
WORKSPACE_PREFIX = re.compile(r"(?:(?:[A-Za-z]:)?[^\s'\"`(\[]*?[\\/])?\.critic[\\/]scratch[\\/][A-Za-z0-9_-]{1,64}[\\/]payload[\\/]")
def strip_workspace(text):
    """A blind agent works in a private copy of the project (hooks/workspace.py); a path it cites inside that copy is the
    same path in the project, so the copy's prefix is removed before any check."""
    return WORKSPACE_PREFIX.sub("", str(text or ""))

def strip_workspace_path(path):
    """The same for one path field, where spaces are part of the path (C:\\Users\\John Smith\\...): anchored at the start."""
    return re.sub(r"^(?:.*?[\\/])?\.critic[\\/]scratch[\\/][A-Za-z0-9_-]{1,64}[\\/]payload[\\/]", "", str(path or ""))

def _cites_real_line(text, root):
    locs = LOCATION.findall(strip_workspace(text))
    if not locs: return False
    if root is None: return True
    rt = pathlib.Path(root).resolve()
    for f, n in locs:
        if f.startswith("/") or ".." in pathlib.PurePath(f).parts or ".critic" in pathlib.PurePath(f).parts: continue
        p = (rt / f).resolve()
        try:
            if not p.is_file() and "/" not in f:  # a bare file name: accept it when exactly one project file has that name
                same = [x for x in rt.rglob(f) if x.is_file() and ".critic" not in x.parts and ".git" not in x.parts][:2]
                p = same[0] if len(same) == 1 else p
            if p.is_relative_to(rt) and p.is_file() and 1 <= int(n) <= len(p.read_text(encoding="utf-8", errors="replace").split("\n")): return True
        except (OSError, ValueError): continue
    return False

SECURITY = re.compile(r"(?i)\b(?:xss|inject\w*|secrets?|credentials?|auth\w*|csrf|ssrf|traversal|deserial\w*|eval|rce|privileges?|tokens?|passwords?|crypto\w*|sanitiz\w*|leak\w*|exposure|security)\b")
SECURITY_REASONS = ("no_untrusted_input", "guard_blocks", "not_reachable", "no_privilege_gain", "already_public", "platform_escapes")
def confirmation_problem(v, root=None):
    """A `confirmed` verdict must show its evidence (SC-42, SC-44): the entry point and the path to the failing line, at
    least 60 characters in all, citing a file:line that exists. Without it the verdict counts as unclear, so a bare
    'confirmed' can never raise confidence. Returns None when the evidence is there."""
    text = " ".join(str(v.get(k) or "") for k in ("entry", "path", "note", "evidence") if not isinstance(v.get(k), list)) + " " + \
           " ".join(str(x) for k in ("path",) if isinstance(v.get(k), list) for x in v[k])
    if len(text.strip()) < 60: return "a confirmed verdict needs its evidence: the entry point and the path to the failing line (60+ characters)"
    if not _cites_real_line(text, root): return "a confirmed verdict must cite the failing path as file:line that exists"
    return None

def security_refutation_problem(v, finding):
    """Refuting a security finding also names who the attacker is, what they would gain, and one reason from a fixed list
    (SC-44, after claude-security's structured answers; our own wording)."""
    if not SECURITY.search(f"{finding.get('category', '')} {finding.get('title', '')}"): return None
    missing = [k for k in ("attacker", "gain") if not str(v.get(k) or "").strip()]
    if missing: return f"a security refutation must name the {' and the '.join(missing)}"
    if v.get("reason") not in SECURITY_REASONS: return "a security refutation's reason must be one of " + ", ".join(SECURITY_REASONS)
    return None

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
def plugin_version():
    try: return json.loads((pathlib.Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json").read_text()).get("version", "unknown")
    except (OSError, ValueError, IndexError): return "unknown"

def to_sarif(findings, tool="critic", version=None):
    version = version or plugin_version()
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
    files outside the project. Returns what's wrong; scripts refuse to run until it's empty. Inside an agent's scratch
    folder, a link that stays inside that folder is allowed (its contents are the agent's own copy and notes)."""
    d = pathlib.Path(root) / ".critic"
    if d.is_symlink(): return [".critic itself is a link"]
    if not d.is_dir(): return []
    bad = []
    for dirpath, dirs, files in os.walk(d):  # os.walk never follows a link to a folder
        here = pathlib.Path(dirpath); rel = here.relative_to(d).parts
        for name in dirs + files:
            if (here / name).is_symlink(): bad.append(str((here / name).relative_to(root)))
        # An agent's own scratch folder (.critic/scratch/<id>/, or an archived one under history/) holds its private copy
        # and notes, and no script writes inside it. A link an agent made there that stays inside that same folder is
        # its own business (reviewers build test repos in their notes); one that reaches out of it is refused.
        if rel[-1:] == ("scratch",):
            for agent in dirs:
                home = here / agent
                if home.is_symlink(): continue  # already listed above
                top = os.path.realpath(home)
                for dp, ds, fs in os.walk(home):
                    for nm in ds + fs:
                        q = pathlib.Path(dp) / nm
                        if q.is_symlink():
                            t = os.path.realpath(q); proj = os.path.realpath(root); crit = os.path.realpath(d)
                            dep = (t == proj or t.startswith(proj + os.sep)) and not (t == crit or t.startswith(crit + os.sep))  # a copy's node_modules link to the project's own (workspace.py): no script writes through it
                            if t != top and not t.startswith(top + os.sep) and not dep: bad.append(str(q.relative_to(root)))
                    if len(bad) >= 5: break
            dirs[:] = []; continue
        dirs[:] = [x for x in dirs if not (here / x).is_symlink()]
        if len(bad) >= 5: break
    return bad[:5]

def in_scratch():
    """True when this process runs inside an agent's private workspace (.critic/scratch/...)."""
    return bool(re.search(r"[\\/]\.critic[\\/]scratch(?:[\\/]|$)", os.getcwd()))

def refuse_linked_state(root):
    """Every script that changes the run's state calls this first. It refuses (exit 2) when .critic holds a link, and
    when it is started from inside an agent's workspace: a reviewer who runs critic_ledger.py start there would
    otherwise reset the real run, since the scripts find the project above .critic/scratch."""
    if in_scratch():
        print("critic: refusing to run from inside an agent's workspace (.critic/scratch): this script changes the review's own state, "
              "which only the lead does. A reviewer or verifier may run the project's code and ast_view.py or browse.py, never the run's scripts.", file=sys.stderr)
        sys.exit(2)
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

FINDING_TEXT = ("quote", "title", "evidence", "failing_case", "remediation", "note", "refutation", "reason", "why", "summary", "what", "guard",
                "preconditions", "root_cause", "entry", "path", "attacker", "gain")
_NAMED_RULES = (REDACT_RULES[3], REDACT_RULES[4])  # NAME=value, "name": "value", --name value
_EXTRA_NAMED = [(re.compile(r"(?i)(" + _NAME + r"[\"']?\s*(?::=|=>)\s*)" + _VAL), None),
                (re.compile(r"(?i)(" + _NAME + r"[\"']?\s*[=:]\s*)(<[^<>\s]{4,}>)"), None)]  # NAME=<value> (a placeholder is masked too: harmless)  # Go password := "x"; PHP and Ruby 'password' => 'x'
_TYPE_WORDS = {"none", "null", "nil", "true", "false", "str", "string", "int", "bytes", "bool", "boolean", "number", "any",
               "optional", "required", "undefined", "secretstr", "object", "dict", "list"}
_CONFIG_OBJECTS = {"settings", "config", "conf", "cfg", "env", "environ", "os", "process", "self", "this", "app", "options", "opts",
                   "args", "params", "secrets", "vault", "creds", "credentials", "keys", "props", "context", "ctx", "request", "req"}
def _literal_value(label, value):
    """True when the value after a secret-bearing name may be data (mask it), False only when it is clearly code that
    names one (keep it). When in doubt it masks: a masked identifier costs a little readability, a leaked password
    costs a rotation. Code that is kept: a call or subscript (get_password(), os.environ[...], params[:password]), an
    attribute on a config object or one ending in the same name (settings.API_KEY, form.password), a comparison
    (==), a variable reference ($DB_PASSWORD, ${DB_PASSWORD}), a type (str, Optional[str], None), or a multi-word
    variable name (new_password, newPassword)."""
    v = value
    if v[:1] in "\"'": return len(v) > 2                       # a quoted literal; an empty one holds nothing
    if v.startswith("="): return False                          # ==
    bare = v.rstrip(",;")
    if re.fullmatch(r"\$\{?[A-Z_][A-Z0-9_]*\}?", bare): return False   # a reference to an environment variable
    if re.fullmatch(r"[A-Za-z_$][A-Za-z_$]*(?:\.[A-Za-z_$][\w$]*)*[(\[][\w$.:]*,?", bare): return False   # a call or subscript cut at a quote or space: get(, HTTPBasicAuth(user,
    m = re.fullmatch(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(\(.*\)|\[.*\])((?:\.[A-Za-z_$][\w$]*(?:\(\))?)*)\)*", bare)
    if m and re.fullmatch(r"[\w$.:'\"\s,]*", m.group(2)[1:-1]): return False   # a whole call or subscript: get(x), uuid4().hex
    name = (re.search(r"[A-Za-z0-9_.-]+(?=[\"']?\s*[=:]|\s*$|=$)", label.lstrip("-")) or re.search(r"\w+", label) or [label])[0]
    words = lambda t: {w for w in re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", t).lower()) if w}
    if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+", bare.rstrip(")")):   # an attribute path
        head, last = bare.split(".")[0], bare.rstrip(")").split(".")[-1]
        return not (head.lower() in _CONFIG_OBJECTS or words(last) & words(name))
    if re.fullmatch(r"[A-Za-z_$][\w$]*", bare.rstrip(")")):
        b = bare.rstrip(")")
        if b.lower() in _TYPE_WORDS or b.lower() in {"input", "getpass", "password", "secret", "token"}: return False
        parts = [x for x in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", b) if x]
        if b[0].islower() and len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z]{3,}\d?", x) and _pronounceable(re.sub(r"\d", "", x)) and _VOWEL.search(x) for x in parts):
            return False                                        # new_password, newPassword: a multi-word variable name
        if words(b) & words(name) and not re.search(r"\d", b): return False   # token = user_token style reuse of the name
        return True
    return True

_KEY_TOKEN = re.compile(r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{20,}(?![A-Za-z0-9_+/=-])")
_PIECE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_VOWEL = re.compile(r"[aeiouyAEIOUY]")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HASH_CONTEXT = re.compile(r"(?i)(?:(?:commit|sha\d*|rev|revision|hash|digest|checksum|tree|blob|ref|checkout|in|at|from|pick|revert|reset|show|diff|bisect)\W{0,3}|@)$")
def _entropy(t):
    import math
    return -sum(c / len(t) * math.log2(c / len(t)) for c in (t.count(ch) for ch in set(t)))
def _pronounceable(run):
    """A letter run reads as a word or a common abbreviation: short (xml, cgi, utf), or holding a vowel with no
    consonant cluster longer than four (scripts, length, request). Long random letter runs almost always break this."""
    lr = run.lower()
    if len(lr) <= 4: return True
    return any(c in "aeiouy" for c in lr) and max(len(x) for x in re.split(r"[aeiouy]+", lr)) <= 4
def _wordy(tok):
    """True when a long token reads as words: snake_case, kebab-case, CONSTANT_CASE, camelCase, a path or a number, as
    names, test names, file paths and constants do. A random key doesn't: its letters and digits keep alternating, and
    its letter runs are short or unpronounceable. Tuned on random keys of eight kinds against every 20+ character token
    in Python's standard library."""
    tok = _UUID.sub("-", tok)  # a uuid is an id, not a key
    letters = sum(c.isalpha() for c in tok)
    if letters < 3: return True
    if "abcdef" in tok.lower() or "0123456" in tok: return True  # an alphabet or digit run, as in a charset constant
    good = 0
    for seg in re.split(r"[/_+=.-]+", tok):
        if not seg: continue
        flips = sum(1 for x, y in zip(seg, seg[1:]) if x.isdigit() != y.isdigit())
        if len(seg) >= 10 and flips >= 4 and flips / len(seg) > 0.2: continue  # letters and digits alternating: random
        if seg.upper() == seg or seg.lower() == seg:  # one case: CONSTANT_CASE, snake or a plain word
            good += sum(len(x) for x in re.findall(r"[A-Za-z]+", seg) if _pronounceable(x)); continue
        for p in _PIECE.findall(seg):  # camelCase pieces
            if p.isdigit(): continue
            if p.isupper(): good += len(p) if 2 <= len(p) <= 8 else 0
            elif len(p) >= 3 and _VOWEL.search(p) and _pronounceable(p): good += len(p)
    return good / letters >= 0.75
def _keylike(tok, before):
    if "[redacted]" in tok: return False
    if re.fullmatch(r"[0-9a-f]+|[0-9A-F]+", tok):  # hex: a key from 32 characters, except a commit or hash named as one
        if len(tok) in (40, 64) and _HASH_CONTEXT.search(before): return False
        return len(tok) >= 32 and any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok)
    return not _wordy(tok) and _entropy(tok) >= 3.5

def redact_finding_text(text):
    """Mask secrets in a finding's words before they are stored, without mangling ordinary code or prose. Masks every
    provider key shape and quoted credential the secret scan knows (scan_secrets); every log rule (auth headers,
    cookies, user:password@, curl -u, mysql -p, redis-cli -a, JWTs, provider shapes); NAME=value and --name value
    secrets (also Go := and PHP/Ruby =>) unless the value is clearly code (see _literal_value: when in doubt it
    masks); and any other 20+ character token that reads as random rather than as words (an unnamed key).
    Measured on 24 Oct 2026: random keys of 20-40 characters are missed 0-6.4% of the time depending on the character
    mix (scan_secrets.redact misses fewer, but masks far more code), and about 0.5% of the 20+ character tokens in
    Python's standard library are masked. Known limits: an identifier holding digits after a secret name (token =
    token2) is masked, and prose such as "the password is x" is not. The quote check always runs on the raw text
    first, and ids are computed from it, so masking never retracts a finding or changes its id."""
    text = str(text)
    try:
        import scan_secrets
        spans = sorted(scan_secrets.secret_spans(text)); mask = scan_secrets.mask
    except ImportError: spans, mask = [], (lambda v: v[:4] + "…[redacted]")
    out, last = [], 0
    for a, b in spans:
        if b <= last or re.fullmatch(r"\$\{?[A-Z_][A-Z0-9_]*\}?", text[a:b]): continue  # a reference to an env variable holds no secret
        a = max(a, last); out.append(text[last:a]); out.append(mask(text[a:b])); last = b
    text = "".join(out) + text[last:]
    def keepq(v): return v[0] + "[redacted]" + v[-1] if len(v) > 1 and v[0] in "\"'" and v[-1] == v[0] else "[redacted]"
    for rule in _EXTRA_NAMED + REDACT_RULES:
        rx, fn = rule
        if rule in _NAMED_RULES or rule in _EXTRA_NAMED:
            text = rx.sub(lambda m: m.group(1) + keepq(m.group(2)) if "[redacted]" not in m.group(2) and _literal_value(m.group(1), m.group(2)) else m.group(0), text)
        else: text = rx.sub(fn or (lambda m: m.group(1) + keepq(m.group(2))), text)
    return _KEY_TOKEN.sub(lambda m: mask(m.group(0)) if _keylike(m.group(0), text[max(0, m.start() - 12):m.start()]) else m.group(0), text)

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

MANIFEST_FILES = ("findings.jsonl", "findings.sarif", "counts.md", "tally.json", "refutations.jsonl", "ledger.json", "ledger.md")
def write_manifest(d):
    """Record a sha256 of each output a review wrote (SC-72, roadmap item 14), so a later hand edit is visible. It makes
    tampering detectable, not impossible: anyone who can edit the outputs can also rewrite the manifest, which is why
    the manifest also records its own time and the run, and why `integrity` is a check, not a lock."""
    d = pathlib.Path(d); man = {"written": time.strftime("%Y-%m-%d %H:%M:%S"), "files": {}}
    try: man["run"] = json.loads((d / "ledger.json").read_text()).get("run")
    except Exception: man["run"] = None
    for name in MANIFEST_FILES:
        p = d / name
        if p.is_file() and not p.is_symlink(): man["files"][name] = hashlib.sha256(p.read_bytes()).hexdigest()
    if not (d / "manifest.json").is_symlink(): (d / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    return man

def check_manifest(d):
    """Files changed, added or removed since the last manifest: [(name, what)]. None when there is no manifest."""
    d = pathlib.Path(d); mp = d / "manifest.json"
    if not mp.is_file() or mp.is_symlink(): return None
    try: man = json.loads(mp.read_text())
    except ValueError: return [("manifest.json", "unreadable")]
    out = []
    for name, h in man.get("files", {}).items():
        p = d / name
        if not p.is_file(): out.append((name, "removed"))
        elif hashlib.sha256(p.read_bytes()).hexdigest() != h: out.append((name, "changed"))
    for name in MANIFEST_FILES:
        if name not in man.get("files", {}) and (d / name).is_file(): out.append((name, "added"))
    return out

RUNLOG_MAX = 1_000_000
# Local state that must never be committed: logs, restore copies, and the files that hold reviewers' raw quotes (a
# quote can contain a secret from the code under review; the outputs Curmudgeon writes itself are masked by scrub()).
IGNORED = ("runlog.jsonl", "refutations.jsonl", "cost.jsonl", "scratch/", "manifest.json", "spotcheck.md", "restore/", "reviews/", "history/", "outside/", "verify/",
           "tally.json", "dedup-candidates.json", "findings-import.jsonl", "briefs/", "scan-only.txt", "verdicts/", "verdicts-variants/", "verify-variants/", "variants.jsonl", "scan-skipped")
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

APPROVABLE = ("rules.md", "scope.json")  # the owner's files that can make Curmudgeon run commands, drop findings or load live sites

def _sha(p):
    try: return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
    except OSError: return None

def owner_state(root, kind):
    """The owner's own record for this project, kept outside it in ~/.curmudgeon (CURMUDGEON_STATE_DIR overrides), one
    file per project path: a repository can't ship it, whatever it commits (03 §5.56 batch 2 review: an approval kept in
    .critic/ could be committed along with the files it approved). Not CLAUDE_PLUGIN_DATA: the hooks may have it and
    the lead's shell may not, and both must read the same record."""
    base = owner_state_base()
    key = hashlib.sha256(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:16]
    return base / kind / f"{key}.json"

def owner_state_base():
    return pathlib.Path(os.environ.get("CURMUDGEON_STATE_DIR") or pathlib.Path.home() / ".curmudgeon")

def read_owner_state(root, kind):
    f = owner_state(root, kind)
    if not f.is_file() or f.is_symlink(): return {}
    try: j = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    return j if isinstance(j, dict) and j.get("root") == str(pathlib.Path(root).resolve()) else {}

def write_owner_state(root, kind, data):
    f = owner_state(root, kind)
    if f.is_symlink() or f.parent.is_symlink(): raise OSError(f"{f} is a link; refusing")
    f.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(json.dumps(dict(data, root=str(pathlib.Path(root).resolve())), indent=1) + "\n")

def approved_state(root, rel):
    """True when the owner approved this exact .critic/<rel> (its sha256 in their own record outside the project,
    written by critic_ledger.py approve after they saw what it does). 03 §5.56 item 9."""
    p = pathlib.Path(root) / ".critic" / rel
    if not p.is_file() or p.is_symlink(): return False
    return (read_owner_state(root, "approvals").get("files") or {}).get(rel) == _sha(p)

def is_git_work_tree(root):
    try: return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True, text=True, timeout=5).stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError): return False

def state_trusted(root, rel):
    """A .critic/<rel> that git tracks could have come with a clone, and in a folder that isn't a git work tree (a
    downloaded zip) nothing tells the owner's file from a shipped one: either way it counts only once approved. An
    untracked file in a git work tree is the owner's own (03 §5.56 item 9)."""
    if approved_state(root, rel): return True
    return owner_untracked(root, rel)

def owner_untracked(root, rel):
    """True only when this project is a git work tree's top folder, .critic is a plain folder (not a link, not a
    submodule), and git tracks nothing at .critic/<rel> under any spelling of its case (03 §5.56 batch 2 round 2: a zip
    unpacked inside another repository, a submodule or tracked link at .critic, and .critic/Rules.md on a case-blind
    disk each passed the old test)."""
    r = pathlib.Path(root); c = r / ".critic"
    if c.is_symlink() or not c.is_dir() or (c / ".git").exists(): return False
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=r, capture_output=True, text=True, timeout=5)
        if top.returncode or os.path.normcase(os.path.realpath(top.stdout.strip())) != os.path.normcase(os.path.realpath(r)): return False
        ls = subprocess.run(["git", "ls-files", "-z", "-s", "--", ".critic"], cwd=r, capture_output=True, text=True, timeout=10)
        if ls.returncode: return False
    except (OSError, subprocess.SubprocessError): return False
    want = f".critic/{rel}".casefold()
    for rec in ls.stdout.split("\0"):
        if not rec: continue
        meta, _, path = rec.partition("\t")
        if path.casefold() in (want, ".critic") or meta.startswith("160000"): return False
    return True

def consent_given(root, kind, host=None):
    """True when the owner's consent for this run is on file (03 §5.56 item 12): kind "live" with the host they typed,
    or "writes". Written by critic_ledger.py consent, which the lead runs after the owner says yes, into the owner's
    own record outside the project; a flag on its own is never consent."""
    j = read_owner_state(root, "consent")
    try: led = json.loads((pathlib.Path(root) / ".critic" / "ledger.json").read_text())
    except (OSError, ValueError): return False
    if not j or j.get("run") != led.get("run") or j.get("started_at") != led.get("started_at") or not led.get("started_at"): return False  # consent is per run (and round)
    if kind == "writes": return j.get("writes") is True
    return kind == "live" and str(host or "").strip().lower() in [str(x).lower() for x in j.get("live") or []]

RULES_SECTION = re.compile(r"(?im)^##[ \t]+(.+?)[ \t]*$")
def rules_sections(text, name):
    """Every '## <name>' section of a rules.md (any case), as one text: the scan, the test command and approve all read
    the file the same way, so what approve shows is what runs (03 §5.56 batch 2 review)."""
    parts = RULES_SECTION.split(text or "")
    return "\n".join(parts[i + 1] for i in range(1, len(parts) - 1, 2) if parts[i].strip().lower() == name.lower())

def rules_commands(text):
    """[(name, command)] under every '## Scripted checks' section of a rules.md."""
    return [(m.group(1).strip(), m.group(2).strip()) for m in re.finditer(r"(?m)^\s*-\s*([\w .-]+?)\s*:\s*`?(.+?)`?\s*$", rules_sections(text, "Scripted checks"))]

def rules_test_command(text):
    m = re.search(r"(?im)^\s*test command\s*:\s*(.+)$", text or "")
    return m.group(1).strip().strip("`") if m else None

def ledger_shipped(root):
    """True when git tracks .critic/ledger.json: then a cloned repository could have written it, so its rulings and
    decisions are never applied (the merge, the scan and the brief all check this)."""
    return git_tracked(root, ".critic/ledger.json")

def one_line(text, cap=600):
    """Text someone else wrote (a commit message, a recorded decision), as one line that can't add a heading, a list
    item or a code fence to a document an agent reads; capped at cap characters."""
    lines = [re.sub(r"^\s*(?:#{1,6}\s+|[-*+>]\s+|\d+[.)]\s+|-{3,}\s*$|`{3,}.*$)", "", x).strip() for x in str(text or "").splitlines()]
    one = " / ".join(x for x in lines if x).replace('"', "'").replace("`", "'")
    return one[:cap] + " [cut]" if len(one) > cap else one

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

def warn_tracked_state(root):
    """Ignore rules never apply to a file git already tracks. Warn once per process when the repository tracks any
    .critic/ file that can hold a raw quote or a log, because writing to it would put that text in the next commit."""
    if ("tracked-state", str(root)) in _TRACKED: return
    _TRACKED[("tracked-state", str(root))] = True
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", ".critic"], cwd=root, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired): return
    if r.returncode != 0: return
    tracked = [f for f in r.stdout.decode("utf-8", "replace").split("\0") if f and f != ".critic/runlog.jsonl"]  # runlog_tracked names that one
    hit = sorted(f for f in tracked for x in IGNORED
                 if (f[len(".critic/"):].startswith(x) if x.endswith("/") else f == ".critic/" + x))
    if hit:
        shown = ", ".join(hit[:8]) + (f" and {len(hit) - 8} more" if len(hit) > 8 else "")
        print(f"curmudgeon: git tracks {len(hit)} .critic/ file(s) that can hold quoted code or logs ({shown}); ignore rules "
              "don't cover tracked files, so new text in them would go into your next commit. To stop tracking them "
              "(your copies stay): git rm -r --cached " + " ".join(sorted({h if h.count('/') == 1 else '/'.join(h.split('/')[:2]) for h in hit})),
              file=sys.stderr)

def log_run(root, what, detail=""):
    """Append one line to .critic/runlog.jsonl: every script the plugin starts and every outside command it runs, so a
    user can see exactly what ran on their machine. Never fails the caller; trims itself past about 1 MB."""
    try:
        d = pathlib.Path(root) / ".critic"; d.mkdir(exist_ok=True)
        warn_tracked_state(root)
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

