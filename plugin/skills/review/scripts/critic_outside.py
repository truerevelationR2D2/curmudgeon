#!/usr/bin/env python3
"""Optional outside reviewer: a model from another family (another AI the user pastes a brief into) reviews the same
change blind, and its answer goes through the same quote check, vote count and blind verification as ours.
Reviewers from one model family share blind spots; in our own double-blind test the outside review and ours overlapped
on none of 23 real findings. Nothing here sends anything anywhere: the user copies the brief out and pastes the answer
back, and only when they said yes to the question in the skill.

usage (from the project root, or set CRITIC_ROOT):
  critic_outside.py brief [--goals TEXT] [--out PATH]
        writes .critic/outside/brief.md for the change in .critic/change-map.json: the commit, its parent, the repository
        link (any user:password@ removed), raw links to each file at that commit (GitHub only), the stated intent, and
        the output format. It never includes our findings, votes or reviewer notes, so the outside review stays blind.
        It warns when the outside reviewer can't see the change (uncommitted edits, a commit not pushed).
  critic_outside.py load ANSWER_FILE
        reads the pasted answer (JSON, or text with ```json blocks), keeps the findings array, and writes
        .critic/outside/outside-review.json in our finding format. It repairs curly quotes, strips citation markers,
        and maps reproduced to executed. A claim of a run we can't see counts as traced, so the finding is verified.
        At most 200 findings and 1 MB are read.
Then: critic_merge.py tally <our reviews> --outside .critic/outside/outside-review.json [--scan ...] [--groups ...]"""
import json, os, pathlib, re, subprocess, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import log_run, redact_secrets, refuse_linked_state

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT", os.getcwd())).resolve(); D = ROOT / ".critic"; OUT = D / "outside"
MAX_BYTES, MAX_FINDINGS = 1_000_000, 200
FIELDS = ("impact", "category", "file", "line", "quote", "title", "evidence", "failing_case", "verified", "remediation")

def die(m): print(f"critic_outside: {m}", file=sys.stderr); sys.exit(2)

def git(*a):
    log_run(ROOT, "command", "git " + " ".join(a))
    try:
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired): return ""

def public_url(remote):
    """https link with no credentials, or "" when the remote isn't a web URL. git@host:owner/repo.git becomes https."""
    remote = remote.strip()
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+?)(?:\.git)?/?$", remote)
    if m: return f"https://{m.group(1)}/{m.group(2)}"
    u = urllib.parse.urlsplit(remote)
    if u.scheme not in ("https", "http") or not u.hostname: return ""
    host = u.hostname + (f":{u.port}" if u.port else "")
    return urllib.parse.urlunsplit(("https", host, re.sub(r"\.git/?$", "", u.path), "", ""))

def brief(args):
    goals = ""
    out = OUT / "brief.md"
    i = 0
    while i < len(args):
        if args[i] == "--goals" and i + 1 < len(args): goals = args[i + 1]; i += 2
        elif args[i] == "--out" and i + 1 < len(args): out = pathlib.Path(args[i + 1]); i += 2
        else: die(f"unknown option {args[i]}")
    try: cm = json.loads((D / "change-map.json").read_text())
    except Exception: die("run critic_map.py first: the brief is built from .critic/change-map.json")
    files = [f for f in cm.get("files", []) if not str(f).startswith(".critic/")]
    head, parent = git("rev-parse", "HEAD"), git("rev-parse", "HEAD~1")
    url = public_url(git("remote", "get-url", "origin"))
    dirty = [l[3:] for l in git("status", "--porcelain").splitlines() if l[3:] in files]
    pushed = bool(head) and bool(git("branch", "-r", "--contains", head))
    warn = []
    if not head: warn.append("This project has no commit yet: attach the files to the outside reviewer yourself.")
    if dirty: warn.append(f"{len(dirty)} file(s) in this change aren't committed, so the outside reviewer can't see those edits online: commit and push first, or attach the files.")
    if head and not pushed: warn.append("This commit isn't pushed, so the links below won't open: push first, or attach the files.")
    if url and "github.com" not in url: warn.append("Raw links are made for GitHub only: for this host, attach the files or give the reviewer the repository link.")
    if not url: warn.append("No web link for this repository: attach the files to the outside reviewer yourself.")
    warn.append("A private repository can't be opened by the outside reviewer: attach the files, or skip this step.")
    def raw(f): return f"https://raw.githubusercontent.com/{url.split('github.com/', 1)[1]}/{head}/{f}" if url and "github.com/" in url and head else f
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
             f"- **Parent commit:** `{parent or '(none)'}`",
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

CITE = re.compile(r"【[^】]*】")  # ChatGPT-style source markers; code like a[0] is never touched
def clean(v):
    return CITE.sub("", v).strip() if isinstance(v, str) else v

def arrays(text):
    """Every JSON value in the answer: the whole text, then each ```json block."""
    found = []
    for t in [text] + re.findall(r"```(?:json)?\s*\n(.*?)```", text, re.S):
        for attempt in (t, t.replace("“", '"').replace("”", '"')):
            try: found.append(json.loads(attempt)); break
            except json.JSONDecodeError: continue
    return found

def load(args):
    if len(args) != 1: die("usage: load ANSWER_FILE")
    p = pathlib.Path(args[0])
    if p.is_symlink() or not p.is_file(): die(f"{p} is not a plain file")
    if p.stat().st_size > MAX_BYTES: die(f"{p} is over 1 MB; paste only the findings block")
    vals = arrays(p.read_text(encoding="utf-8", errors="replace"))
    rows = next((v for v in vals if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and any("impact" in x for x in v)), None)
    if rows is None:
        if any(isinstance(v, list) and not v for v in vals): rows = []
        else: die("no findings array found (a JSON list of objects with an impact field)")
    out, skipped = [], max(0, len(rows) - MAX_FINDINGS)
    for k, r in enumerate(rows[:MAX_FINDINGS]):
        f = {x: (r.get(x) if x == "quote" else clean(r.get(x))) for x in FIELDS}  # the quote is code: kept exactly
        f["impact"] = str(f.get("impact") or "").strip().title()
        claimed = str(f.get("verified") or "").strip().lower()
        f["verified"] = "inferred" if claimed == "inferred" else "traced"  # we can't see the outside run: verification decides
        f["claimed_verified"] = claimed
        f["quote"] = f.get("quote") or ""
        f["outside_id"] = str(r.get("id") or f"N{k + 1}")[:20]
        if r.get("introduced_by_change") is not None: f["introduced_by_change"] = str(r["introduced_by_change"])[:20]
        f["source"] = "outside"
        out.append(f)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "outside-review.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote .critic/outside/outside-review.json: {len(out)} finding(s)" + (f", {skipped} over the limit of {MAX_FINDINGS} not read" if skipped else ""))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or any(x in ("-h", "--help") for x in a): print(__doc__); sys.exit(0)
    refuse_linked_state(ROOT)
    log_run(ROOT, "script", "critic_outside.py " + " ".join(a))
    if a[0] == "brief": sys.exit(brief(a[1:]))
    if a[0] == "load": sys.exit(load(a[1:]))
    die("usage: brief [--goals TEXT] [--out PATH] | load ANSWER_FILE")
