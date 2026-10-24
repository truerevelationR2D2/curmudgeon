#!/usr/bin/env python3
"""Optional outside reviewer: a model from another family (another AI the user pastes a brief into) reviews the same
change blind, and its answer goes through the same quote check, vote count and blind verification as ours.
Reviewers from one model family share blind spots; in two double-blind tests the outside review and ours overlapped
on none of 23 real findings, then 2 of 14. Nothing here sends anything anywhere: the user copies the brief out and pastes the answer
back, and only when they said yes to the question in the skill.

usage (from the project root, or set CRITIC_ROOT):
  critic_outside.py brief [--goals TEXT] [--base REV] [--out PATH]
        writes .critic/outside/brief.md for the change in .critic/change-map.json: the commit, its parent, the repository
        link (any user:password@ removed), raw links to each file at that commit (GitHub only), the stated intent, and
        the output format. It never includes our findings, votes or reviewer notes, so the outside review stays blind.
        It warns when the outside reviewer can't see the change (uncommitted edits, a commit not pushed).
  critic_outside.py load ANSWER_FILE
        reads the pasted answer (JSON with or without ```json fences, as copied from a chat page), keeps every findings
        array (objects with an impact field; recheck rows and the inspection record are ignored), and writes
        .critic/outside/outside-review.json in our finding format. It repairs curly quotes, strips citation markers,
        and maps reproduced to executed. A claim of a run we can't see counts as traced, so the finding is verified.
        Every value becomes bounded text; a finding naming a file outside the project is not loaded.
        At most 200 findings and 1 MB are read.
Then: critic_merge.py tally <our reviews> --outside .critic/outside/outside-review.json [--scan ...] [--groups ...]"""
import json, os, pathlib, re, subprocess, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import IMPACTS, log_run, redact_secrets, refuse_linked_state

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch[\\/][A-Za-z0-9_-]{1,64}[\\/]payload(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"; OUT = D / "outside"
MAX_BYTES, MAX_FINDINGS = 1_000_000, 200
FIELDS = ("impact", "category", "file", "line", "quote", "title", "evidence", "failing_case", "verified", "remediation")

def die(m): print(f"critic_outside: {m}", file=sys.stderr); sys.exit(2)

def git_rc(*a):
    """(exit code, stdout unstripped). Logged like every outside command."""
    log_run(ROOT, "command", "git " + " ".join(a))
    try:
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired): return 1, ""

def git(*a):
    rc, out = git_rc(*a)
    return out.strip() if rc == 0 else ""

def public_url(remote):
    """https link with no credentials, or "" when the remote isn't a web URL. git@host:owner/repo.git becomes https."""
    remote = remote.strip()
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+?)(?:\.git)?/?$", remote)
    if m: return f"https://{m.group(1)}/{m.group(2)}"
    u = urllib.parse.urlsplit(remote)
    if u.scheme not in ("https", "http", "ssh", "git+ssh", "git") or not u.hostname: return ""
    host = u.hostname + (f":{u.port}" if u.port and u.scheme in ("https", "http") else "")  # an ssh port is not a web port
    return urllib.parse.urlunsplit(("https", host, re.sub(r"(\.git)?/*$", "", u.path), "", ""))

def is_github(url):
    try: return urllib.parse.urlsplit(url).hostname == "github.com"
    except ValueError: return False

def brief(args):
    goals, base = "", ""
    out = OUT / "brief.md"
    i = 0
    while i < len(args):
        if args[i] == "--goals" and i + 1 < len(args): goals = args[i + 1]; i += 2
        elif args[i] == "--base" and i + 1 < len(args): base = args[i + 1]; i += 2
        elif args[i] == "--out" and i + 1 < len(args): out = pathlib.Path(args[i + 1]); i += 2
        else: die(f"unknown option {args[i]}")
    try: cm = json.loads((D / "change-map.json").read_text())
    except Exception: die("run critic_map.py first: the brief is built from .critic/change-map.json")
    files = [f for f in cm.get("files", []) if not str(f).startswith(".critic/")]
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "--verify", "--quiet", (base or "HEAD~1") + "^{commit}") if head else ""
    prefix = git("rev-parse", "--show-prefix")  # the project's folder inside the repository ("" at the top)
    top = pathlib.Path(git("rev-parse", "--show-toplevel") or ROOT)
    url = public_url(git("remote", "get-url", "origin"))
    def repo_rel(f):  # the change map lists paths from the project root (--files) or from the repository root (git diff)
        return prefix + f if (ROOT / f).exists() or not (top / f).exists() else f
    # edits not in HEAD (staged, unstaged or untracked) for the files in this change, named from the repository top
    dirty = 0
    if head and files:
        spec = [":(top)" + repo_rel(f) for f in files]
        rc, _ = git_rc("diff", "--quiet", "HEAD", "--", *spec)
        dirty = (rc != 0) + bool(git("ls-files", "--others", "--exclude-standard", "--", *spec))
    pushed = bool(head) and bool(git("branch", "-r", "--contains", head))
    reviews_ignored = all(git_rc("check-ignore", "-q", p)[0] == 0 for p in (".critic/findings.jsonl", ".critic/counts.md"))  # raw reviews are ignored by default; our merged findings are not
    warn = []
    if not head: warn.append("This project has no commit yet: attach the files to the outside reviewer yourself.")
    if dirty: warn.append("Some files in this change have edits that aren't committed, so the outside reviewer can't see them online: commit and push first, or attach the files.")
    if not reviews_ignored: warn.append("The .critic/ folder isn't git-ignored here. If you commit and push for the outside reviewer, leave .critic/ out (or add it to .gitignore first): otherwise it can read our findings and the review stops being blind.")
    if head and not pushed: warn.append("This commit isn't pushed, so the links below won't open: push first, or attach the files.")
    if url and not is_github(url): warn.append("Raw links are made for GitHub only: for this host, attach the files or give the reviewer the repository link.")
    if not url: warn.append("No web link for this repository: attach the files to the outside reviewer yourself.")
    warn.append("A private repository can't be opened by the outside reviewer: attach the files, or skip this step.")
    def raw(f):
        if not (url and is_github(url) and head): return f
        return f"https://raw.githubusercontent.com/{url.split('github.com/', 1)[1]}/{head}/" + urllib.parse.quote(repo_rel(f))
    lines = ["# Outside review brief (paste everything below the line into the other AI)", "",
             "Before you paste: this sends the files listed here to that AI's service. Check:", ""] + [f"- {w}" for w in warn] + ["", "---", "",
             "## Request for an independent, double-blind code review", "",
             "You are an independent reviewer examining a code change that another AI reviewer has also examined. You will not see the other "
             "reviewer's findings. Your findings will be compared afterward, and every quote and line number will be checked by a script against "
             "the file at the commit below.", "",
             "Be skeptical, specific, and technically rigorous. Do not praise the implementation. Do not invent bugs to fill a quota. Prioritize "
             "concrete defects over speculative concerns.", "",
             "### 1. Review target", "",
             f"- **Repository:** {url or '(attached files)'}",
             f"- **Exact commit:** `{head or '(not committed)'}`",
             f"- **Parent commit** ({'the change starts after ' + base if base else 'the commit before it'}): `{parent or '(none)'}`",
             f"- **Stated intent of the change:** {redact_secrets(str(cm.get('intent') or 'not stated'))[:600]}"]
    if goals: lines.append(f"- **Primary design goals:** {redact_secrets(goals)[:1200]}")
    lines += ["", "**Files in the change** (raw text at the exact commit; use these for quotes and line numbers):", ""] + [f"- {raw(f)}" for f in files[:60]]
    if len(files) > 60: lines.append(f"- … and {len(files) - 60} more in the same folder layout")
    lines += ["", "### 2. Procedure", "",
              "Review the exact commit above, not the latest branch. If opening, cloning or running anything fails, say so.",
              "Evidence levels: **reproduced** (you ran it and saw the failure), **traced** (you followed the source to a concrete failing case "
              "without running it), **inferred** (a plausible risk without a complete failure path). Never call a traced issue reproduced.",
              "For each finding give the exact code path, the triggering input or sequence, the wrong result, which expected behaviour it breaks, "
              "and the smallest fix. With no credible failing case, list it under Unconfirmed concerns instead. Say whether the change "
              "introduced it.",
              "Take quotes and line numbers from the raw text, not a rendered page or memory: the quote is one complete source line, copied "
              "character for character, or empty if you couldn't open the file.", "",
              "Look at: correctness on ordinary, boundary, malformed and hostile input; security and trust boundaries; state and persistence; "
              "failure handling; compatibility; tests that pass while a defect remains; and documentation that disagrees with the code.", "",
              "Impact: **Critical** severe and broadly exploitable · **High** serious with credible material impact · **Medium** meaningful but "
              "bounded · **Low** small. Judge by real consequences and realistic prerequisites.", "",
              "### 3. Output", "",
              "Each JSON section is one fenced json block that parses as-is: straight double quotes only, and no citation markers, footnotes or "
              "links inside the values.", "",
              "**A. Inspection record:**", "```json",
              '{"commit_reviewed": "", "files_read": [], "tests_run": [{"command": "", "result": ""}], "not_run": [], "limitations": []}', "```", "",
              "**B. Findings** (`[]` if none qualify):", "```json",
              '[{"id": "N1", "impact": "Critical | High | Medium | Low", "category": "short category", "file": "path/to/file", "line": 123,',
              '  "quote": "exact source line or empty string", "title": "the defect in one line", "evidence": "code path and reasoning",',
              '  "failing_case": "triggering input or sequence and the wrong result", "verified": "reproduced | traced | inferred",',
              '  "introduced_by_change": "yes | no | uncertain", "remediation": "smallest practical fix"}]', "```", "",
              "**C. Unconfirmed concerns and test gaps** (prose), each with the evidence that would confirm or reject it.", "",
              "**D. Three highest-priority fixes** (prose), ranked, each with why it outranks the others.", "",
              "Be blunt but fair. Do not invent source lines, quotes, tests or runtime results. Prefer a few strong findings over many weak ones."]
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {len(files)} file(s), commit {head[:7] or '-'}")
    for w in warn: print("note: " + w)
    return 0

CITE = re.compile(r"\u3010[^\u3011]*\u3011")  # ChatGPT-style source markers; code like a[0] is never touched
TEXT_FIELDS = ("impact", "category", "file", "title", "evidence", "failing_case", "verified", "remediation", "quote")
MAX_FIELD = 4000

def as_text(v):
    """Pasted values can be anything: lists, numbers, objects. Everything becomes bounded text."""
    if v is None: return ""
    if not isinstance(v, str): v = json.dumps(v, ensure_ascii=False)
    return v[:MAX_FIELD]

def json_values(text, budget=20_000_000):
    """Every top-level JSON array or object in the text, fenced or not (a copy of a rendered chat page has no
    fences). Each [ or { that starts a line, a fence or follows a colon-free run is tried with a JSON decoder; a value
    found is skipped over whole. Work is bounded by the bytes the decoder has looked at, so a hostile paste (thousands
    of brackets before a huge unterminated array) stops in well under a second instead of re-parsing the tail each time."""
    dec, out, i, spent = json.JSONDecoder(), [], 0, 0
    while i < len(text) and spent < budget:
        j = min([k for k in (text.find("[", i), text.find("{", i)) if k >= 0], default=-1)
        if j < 0: break
        try:
            v, end = dec.raw_decode(text, j); out.append(v); i = end; spent += end - j
        except RecursionError:
            i = j + 1; spent += len(text) - j  # a run of brackets: the decoder read to the end, count it
        except ValueError as e:
            fail = getattr(e, "pos", j); spent += max(1, fail - j)  # how far the decoder got before it gave up
            nl = text.find("\n", j); i = nl + 1 if 0 < nl else j + 1  # a failed start is skipped to the next line
    return out

def findings_in(vals):
    """Every findings-shaped array: lists of objects with an impact field. Recheck rows (status, no impact) and the
    inspection record are not findings."""
    rows = []
    for v in vals:
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and any("impact" in x for x in v): rows += [x for x in v if "impact" in x]
    return rows

def inside_root(rel):
    """A finding must name a file inside the project: no absolute paths, no .., nothing that resolves outside."""
    parts = re.split(r"[/\\]", rel)
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) or ".." in parts or ".critic" in parts: return False
    try: (ROOT / rel).resolve().relative_to(ROOT)
    except (ValueError, OSError): return False
    return True

def load(args):
    if len(args) != 1: die("usage: load ANSWER_FILE")
    p = pathlib.Path(args[0])
    if p.is_symlink() or not p.is_file(): die(f"{p} is not a plain file")
    if p.stat().st_size > MAX_BYTES: die(f"{p} is over 1 MB; paste only the findings block")
    text = p.read_text(encoding="utf-8", errors="replace")
    vals = json_values(text)
    rows = findings_in(vals)
    straight = text.replace("\u201c", '"').replace("\u201d", '"')
    if straight != text:  # a chat page can turn straight quotes into curly ones: read it straightened too (duplicates are dropped below)
        rows += findings_in(json_values(straight))
    if not rows and not any(isinstance(v, list) and not v for v in vals):
        die("no findings found: paste the JSON findings list (objects with an impact field), with or without the ```json fences")
    uniq, seen_raw = [], set()
    for r in rows:  # the same row read twice (straight and straightened) counts once, before the limit applies
        key = json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        if key not in seen_raw: seen_raw.add(key); uniq.append(r)
    rows = uniq
    out, notes, seen = [], [], set()
    for k, r in enumerate(rows[:MAX_FINDINGS]):
        f = {x: as_text(r.get(x)) for x in TEXT_FIELDS}
        for x in TEXT_FIELDS:
            if x != "quote": f[x] = CITE.sub("", f[x]).strip()  # the quote is code: kept exactly
        oid = as_text(r.get("id") or f"N{k + 1}")[:20]
        f["file"] = f["file"].replace("\\", "/")
        while f["file"].startswith("./"): f["file"] = f["file"][2:]
        if not inside_root(f["file"]): notes.append(f"{oid}: names a file outside this project ({f['file'][:80]}), not loaded"); continue
        try: f["line"] = max(0, int(str(r.get("line") or 0).strip()))
        except ValueError: f["line"] = 0
        f["impact"] = f["impact"].strip().title()
        if f["impact"] not in IMPACTS:  # e.g. the brief's own template row, "Critical | High | Medium | Low", pasted back
            notes.append(f"{oid}: impact {f['impact'][:40]!r} is not Critical, High, Medium or Low, not loaded"); continue
        claimed = f["verified"].strip().lower()
        f["verified"] = "inferred" if claimed == "inferred" else "traced"  # we can't see the outside run: verification decides
        f["claimed_verified"] = claimed[:20]
        f["outside_id"] = oid
        f["introduced_by_change"] = as_text(r.get("introduced_by_change"))[:20]
        f["source"] = "outside"
        key = (oid, f["file"], f["line"], f["title"])
        if key in seen: continue  # the same finding pasted twice
        seen.add(key); out.append(f)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "outside-review.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    over = max(0, len(rows) - MAX_FINDINGS)
    print(f"wrote .critic/outside/outside-review.json: {len(out)} finding(s)" + (f", {over} over the limit of {MAX_FINDINGS} not read" if over else ""))
    for n in notes: print("note: " + n)
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or any(x in ("-h", "--help") for x in a): print(__doc__); sys.exit(0)
    refuse_linked_state(ROOT)
    log_run(ROOT, "script", "critic_outside.py " + " ".join(a))
    if a[0] == "brief": sys.exit(brief(a[1:]))
    if a[0] == "load": sys.exit(load(a[1:]))
    die("usage: brief [--goals TEXT] [--out PATH] | load ANSWER_FILE")
