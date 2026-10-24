"""The CI and supply-chain lens (SC-51), our own rules and code. Ideas from zizmor (MIT), actionlint (MIT), OpenSSF
Scorecard (Apache-2.0) and poutine (Apache-2.0), and GitHub's own security hardening guide; no rule text copied.
Workflows are read with yaml_lite (strict, standard library); a file it can't read safely is reported as not checked,
never guessed at.

GitHub workflows (.github/workflows/*.yml|yaml):
  ci-injection          FAIL  an attacker-controlled value (a PR or issue title, a comment, a branch name, a commit
                              message ...) pasted into a run: script with ${{ }}, when the workflow's trigger can supply
                              it; WARN on plain pull_request, where the author of the PR already controls the code.
                              Not when the expression can only be true or false (startsWith, endsWith, contains, a
                              comparison).
  ci-pwn-request        FAIL  pull_request_target or workflow_run checks out the pull request's own code (head sha or
                              ref): untrusted code runs with the base repository's secrets and write token. Not when
                              the job's or step's if: lets only this repository's own commits through (workflow_run
                              event == 'push', or head repository == github.repository, with no ||).
  ci-if-always-true     FAIL  an if: that mixes ${{ }} with other text, so it is a non-empty string and always true.
  ci-no-permissions     WARN  a risky trigger (pull_request_target, workflow_run, issue_comment, issues) with no
                              permissions: block anywhere, so the token gets the repository's default (often write).
  ci-unpinned-action    WARN  a third-party action used by tag or branch instead of a full commit SHA, unless
                              .github/workflows/actions.lock (GitHub's workflow lockfile) lists it.
  ci-secret-in-run      WARN  ${{ secrets.X }} pasted into a run: script (it can leak through command echo, process
                              lists or error output; pass it through env: instead).
  ci-upload-checkout    WARN  an artifact upload of the whole workspace after a checkout that keeps credentials: the
                              token in .git/config ships inside the artifact. Only for upload-artifact before v4.4,
                              or with include-hidden-files: true (v4.4 on leaves hidden files out).
  ci-not-checked        NOTE  a workflow the strict reader refused, with the line and why.
Anywhere (workflow run: scripts, shell scripts, Dockerfiles, requirement files):
  curl-pipe-shell       WARN  curl or wget piped into sh or bash: whatever the server sends runs.
  pip-extra-index       WARN  --extra-index-url: a package name on the public index can win over your private one.
  docker-latest         NOTE  FROM image:latest or with no tag: the build changes under you (a FROM naming an
                              earlier stage of the same Dockerfile is not an image).
Lockfiles:
  npm-resolved-host     WARN  a package-lock.json entry resolved from somewhere other than registry.npmjs.org, or
                              over plain http.
  npm-no-integrity      NOTE  a package-lock.json entry with a resolved URL and no integrity hash."""
import json, pathlib, re
import yaml_lite

PRIVILEGED = {"pull_request_target", "workflow_run", "issue_comment", "issues", "discussion", "discussion_comment",
              "pull_request_review", "pull_request_review_comment", "push", "commit_comment", "gollum", "fork", "watch", "release"}
# attacker-controlled expressions, and the triggers that can supply each (pull_request is added on its own, as a WARN)
TAINT = [
    (r"github\.event\.pull_request\.(?:title|body|head\.ref|head\.label|head\.repo\.default_branch)|github\.head_ref", {"pull_request", "pull_request_target", "pull_request_review", "pull_request_review_comment"}),
    (r"github\.event\.issue\.(?:title|body)", {"issues", "issue_comment"}),
    (r"github\.event\.comment\.body", {"issue_comment", "pull_request_review_comment", "commit_comment", "discussion_comment"}),
    (r"github\.event\.review\.body", {"pull_request_review"}),
    (r"github\.event\.review_comment\.body", {"pull_request_review_comment"}),
    (r"github\.event\.discussion\.(?:title|body)", {"discussion", "discussion_comment"}),
    (r"github\.event\.(?:head_commit\.(?:message|author\.(?:email|name))|commits\[?[^\]\s}]*\]?\.(?:message|author\.(?:email|name)))", {"push"}),
    (r"github\.event\.workflow_run\.(?:head_branch|head_commit\.(?:message|author\.(?:email|name))|display_title)", {"workflow_run"}),
    (r"github\.event\.pages\[?[^\]\s}]*\]?\.page_name", {"gollum"}),
]
PR_HEAD = re.compile(r"github\.event\.pull_request\.head\.(?:sha|ref)|github\.head_ref|refs/pull/|github\.event\.workflow_run\.head_(?:sha|branch)|pull_request\.head")
SHA = re.compile(r"^[0-9a-f]{40}$")
FIRST_PARTY = {"actions", "github"}
LINE_RULES = [
    ("curl-pipe-shell", "WARN", re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"), "curl or wget piped into a shell: whatever the server sends runs (download, check a hash, then run)"),
    ("pip-extra-index", "WARN", re.compile(r"--extra-index-url\b"), "--extra-index-url: a same-named package on the public index can win over your private one (use --index-url, or pin hashes)"),
]

SAME_REPO_GUARD = re.compile(r"github\.event\.workflow_run\.event\s*==\s*'push'|github\.event\.workflow_run\.head_repository\.full_name\s*==\s*github\.repository"
                             r"|github\.event\.pull_request\.head\.repo\.full_name\s*==\s*github\.repository|github\.repository\s*==\s*github\.event\.(?:workflow_run\.head_repository|pull_request\.head\.repo)\.full_name")

def _same_repo_only(*conds):
    """An if: that lets only this repository's own commits through (a push, or a head repository equal to this one),
    joined with && only, so no || can open it again."""
    for c in conds:
        c = str(c or "")
        if SAME_REPO_GUARD.search(c) and "||" not in c: return True
    return False

def _upload_takes_hidden(uses, w):
    """upload-artifact leaves hidden files (.git/config among them) out from v4.4 on, unless include-hidden-files is
    true. A pinned SHA can't be dated here, so it is given the benefit of the doubt."""
    if str(w.get("include-hidden-files", "")).strip().lower() == "true": return True
    m = re.match(r"v?(\d+)(?:\.(\d+))?", uses.rsplit("@", 1)[1])
    if not m: return False
    major, minor = int(m.group(1)), m.group(2)
    return major < 4 or major == 4 and minor is not None and int(minor) < 4

BOOLEAN_EXPR = re.compile(r"\s*!?\s*(?:startsWith|endsWith|contains)\s*\(.*\)\s*|[^|&]*(?:==|!=|<=|>=)[^|&]*", re.S)

def triggers(doc):
    on = doc.get("on", doc.get(True, ""))
    if isinstance(on, str): return {on} if on else set()
    if isinstance(on, list): return {str(x) for x in on}
    if isinstance(on, dict): return {str(k) for k in on}
    return set()

def _line_of(raw, start, needle):
    """The first raw line at or after start that holds needle (1-based); start when none does."""
    for i in range(max(start, 1) - 1, len(raw)):
        if needle in raw[i]: return i + 1
    return start

def _walk_jobs(doc):
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict): return
    for name, job in jobs.items():
        if isinstance(job, dict): yield name, job

def scan_workflow(rel, text, emit, lock_text=""):
    raw = text.split("\n"); seen = set(); outer = emit
    def emit(sev, rid, area, where, what, ev=""):  # one row per rule and place
        if (rid, where) not in seen: seen.add((rid, where)); outer(sev, rid, area, where, what, ev)
    try: doc = yaml_lite.loads(text)
    except yaml_lite.Refused as e:
        emit("NOTE", "ci-not-checked", "supply-chain", f"{rel}:{e.line}", f"workflow not checked: the strict reader refused it ({e.why})", raw[e.line - 1] if 0 < e.line <= len(raw) else ""); return
    if not isinstance(doc, dict): return
    trig = triggers(doc)
    risky = trig & {"pull_request_target", "workflow_run", "issue_comment", "issues"}
    has_perm = "permissions" in doc or any("permissions" in j for _, j in _walk_jobs(doc))
    if risky and not has_perm:
        ln = doc.key_lines.get("on", 1)
        emit("WARN", "ci-no-permissions", "supply-chain", f"{rel}:{ln}", f"{', '.join(sorted(risky))} with no permissions: block: the token gets the repository's default, often write", raw[ln - 1] if ln <= len(raw) else "")
    def check_if(v):
        if isinstance(v, str) and "${{" in v:
            s = v.strip()
            if not (s.startswith("${{") and s.endswith("}}") and s.count("${{") == 1):
                emit("FAIL", "ci-if-always-true", "supply-chain", f"{rel}:{v.line}", "this if: mixes ${{ }} with other text, so it is a non-empty string and always true: put the whole condition inside one ${{ }}", raw[v.line - 1] if v.line <= len(raw) else "")
    for jname, job in _walk_jobs(doc):
        check_if(job.get("if"))
        steps = job.get("steps")
        if not isinstance(steps, list): continue
        checkout_keeps_creds = False
        for st in steps:
            if not isinstance(st, dict): continue
            check_if(st.get("if"))
            uses = st.get("uses")
            if isinstance(uses, str):
                u = uses.strip()
                if u.startswith("actions/checkout@"):
                    w = st.get("with") if isinstance(st.get("with"), dict) else {}
                    ref = str(w.get("ref", "")) + " " + str(w.get("repository", ""))
                    if trig & {"pull_request_target", "workflow_run"} and PR_HEAD.search(ref) and not _same_repo_only(job.get("if"), st.get("if")):
                        ln = _line_of(raw, uses.line, "ref:") if "ref" in w else uses.line
                        emit("FAIL", "ci-pwn-request", "supply-chain", f"{rel}:{ln}", f"{' and '.join(sorted(trig & {'pull_request_target', 'workflow_run'}))} checks out the pull request's own code: it then runs with this repository's secrets and write token", raw[ln - 1] if ln <= len(raw) else "")
                    checkout_keeps_creds = str(w.get("persist-credentials", "true")).strip().lower() != "false"
                elif u.startswith("actions/upload-artifact@") and checkout_keeps_creds:
                    w = st.get("with") if isinstance(st.get("with"), dict) else {}
                    path = str(w.get("path", "")).strip()
                    if _upload_takes_hidden(u, w) and path in (".", "./", "*", "**", "${{ github.workspace }}") or path.startswith(("./**", "**")):
                        emit("WARN", "ci-upload-checkout", "supply-chain", f"{rel}:{uses.line}", "the whole workspace is uploaded after a checkout that kept its credentials: the token in .git/config ships in the artifact (set persist-credentials: false, or upload only the build output)", raw[uses.line - 1])
                if not u.startswith(("./", "docker://")) and "@" in u:
                    owner = u.split("/", 1)[0]; ref = u.rsplit("@", 1)[1]
                    if owner not in FIRST_PARTY and not SHA.match(ref) and u.split("@")[0] not in lock_text:
                        emit("WARN", "ci-unpinned-action", "supply-chain", f"{rel}:{uses.line}", f"{u.split('@')[0]} is used by the tag or branch {ref}, which its owner can move: pin a full commit SHA (or list it in .github/workflows/actions.lock)", raw[uses.line - 1])
            run = st.get("run")
            if isinstance(run, str):
                for expr in re.findall(r"\$\{\{(.*?)\}\}", run, re.S):
                    boolean = bool(BOOLEAN_EXPR.fullmatch(expr))  # startsWith(...), a == b: only true or false reaches the script
                    for pat, can in TAINT:
                        if boolean: break
                        m = re.search(pat, expr)
                        if not m: continue
                        hit = trig & can
                        if not hit: continue
                        sev = "FAIL" if hit & PRIVILEGED else "WARN"
                        ln = _line_of(raw, run.line, m.group(0))
                        emit(sev, "ci-injection", "supply-chain", f"{rel}:{ln}", f"{m.group(0)} is chosen by whoever opens the pull request, issue or comment, and it is pasted into a shell script: pass it through env: and quote \"$VAR\"", raw[ln - 1] if ln <= len(raw) else "")
                        break
                    if re.search(r"\bsecrets\.", expr):
                        ln = _line_of(raw, run.line, expr.strip())
                        emit("WARN", "ci-secret-in-run", "supply-chain", f"{rel}:{ln}", "a secret pasted into a run: script can leak through command echo or error output: pass it through env:", raw[ln - 1] if ln <= len(raw) else "")
                for rid, sev, rx, msg in LINE_RULES:
                    m = rx.search(run)
                    if m: ln = _line_of(raw, run.line, m.group(0)[:20]); emit(sev, rid, "supply-chain", f"{rel}:{ln}", msg, raw[ln - 1] if ln <= len(raw) else "")

def scan_text(rel, text, emit):
    """Shell scripts, Dockerfiles and requirement files: the line rules, and docker-latest."""
    name = pathlib.PurePosixPath(rel).name
    stages = {m.group(1).lower() for m in re.finditer(r"(?im)^\s*FROM\s+(?:--platform=\S+\s+)?\S+\s+AS\s+(\S+)", text)}  # FROM build uses a stage, not an image
    for i, l in enumerate(text.split("\n"), 1):
        if len(l) > 2000 or l.lstrip().startswith("#"): continue
        for rid, sev, rx, msg in LINE_RULES:
            if rx.search(l): emit(sev, rid, "supply-chain", f"{rel}:{i}", msg, l)
        if name.startswith("Dockerfile") or name.endswith(".dockerfile"):
            m = re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", l, re.I)
            if m:
                img = m.group(1)
                if img.lower() != "scratch" and img.lower() not in stages and "@sha256:" not in img and "$" not in img and (img.endswith(":latest") or ":" not in img.rsplit("/", 1)[-1]):
                    emit("NOTE", "docker-latest", "supply-chain", f"{rel}:{i}", f"{img} has no fixed tag: the build changes when the image does (pin a version, or a digest)", l)

def scan_npm_lock(rel, text, emit):
    try: j = json.loads(text)
    except ValueError: return
    pk = j.get("packages") if isinstance(j, dict) else None
    if not isinstance(pk, dict): return
    raw = text.split("\n")
    for name, meta in pk.items():
        if not isinstance(meta, dict) or not meta.get("resolved"): continue
        r = str(meta["resolved"])
        if r.startswith("file:") or r.startswith("git+"): continue
        ln = _line_of(raw, 1, json.dumps(r)[1:-1][:60])
        if r.startswith("http://") or not re.match(r"https://registry\.npmjs\.org/", r):
            emit("WARN", "npm-resolved-host", "supply-chain", f"{rel}:{ln}", f"{name or '(root)'} is resolved from {r[:80]}: not the public npm registry over https (check it is meant to be)", raw[ln - 1] if ln <= len(raw) else "")
        if not meta.get("integrity"):
            emit("NOTE", "npm-no-integrity", "supply-chain", f"{rel}:{ln}", f"{name or '(root)'} has no integrity hash in the lockfile: a changed download wouldn't be noticed", raw[ln - 1] if ln <= len(raw) else "")

def is_workflow(rel):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    return p.suffix in (".yml", ".yaml") and len(p.parts) >= 3 and p.parts[-3:-1] == (".github", "workflows")

def wants_text(rel):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    return p.suffix in (".sh", ".bash") or p.name.startswith("Dockerfile") or p.name.endswith(".dockerfile") or re.fullmatch(r"requirements[\w.-]*\.(txt|in)", p.name) is not None
