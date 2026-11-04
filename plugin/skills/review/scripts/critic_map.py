#!/usr/bin/env python3
"""Change map and risk tier for a Curmudgeon run: how much review this change needs, where to start, and what else it
can break. Written to .critic/change-map.md (kept separate from the findings).

usage: critic_map.py [--files PATH ...] [--base GIT_REF] [--intent "what the change is meant to do"]
Without --files it uses `git diff --name-only` against --base (default HEAD), plus untracked files.

Tier: trivial (≤2 files, <20 changed lines, nothing sensitive), full (anything sensitive, >10 files or >400
lines), else lite. The tier sets the review size: trivial = one reviewer, with verification of contested findings only (a lone traced Critical or High); lite = one reviewer
plus verification of Critical/High; full = three blind reviewers, verification and the full sandbox."""
import json, os, pathlib, posixpath, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
from critic_findings import log_run, refuse_linked_state, one_line, redact_finding_text
import safegit  # git without the repository's own commands (03 §5.57 review)

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
# whole words only ("author" is not "auth"); paths may also match folder-style names
SENSITIVE = re.compile(r"(?<![A-Za-z])(auth|authn|authz|authenticate\w*|authoriz\w*|login|logout|sessions?|passwords?|secrets?|payments?|billing|refunds?|checkout|invoices?|crypto|encrypt\w*|decrypt\w*|permissions?|admin|migrations?|webhooks?|uploads?|credentials?|api[_-]?keys?|private[_-]?keys?|tokens?|jwts?|oauth\w*|sso|saml|roles?|rbac|acls?|security|privacy|pii|gdpr|csrf|xsrf|cors|csp|signatures?|hmac|hash(?:es|ing)?|salt|sanitiz\w*|schemas?)(?![A-Za-z])", re.I)
SENSITIVE_PATH = re.compile(r"(?:^|/)(\.env[\w.]*|config|settings|security|privacy|auth|admin|migrations?|schema)(?:/|\.|$)", re.I)
COMMON = {"main", "init", "run", "setup", "render", "test", "handle", "get", "set", "update", "load", "save", "start", "stop", "close", "open", "create", "delete", "parse", "read", "write", "show", "reset", "build", "apply", "check", "process"}
CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".html", ".css", ".vue", ".svelte", ".go", ".rb", ".php", ".java", ".cs", ".rs"}
DEF = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\*?\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(|def\s+([A-Za-z_]\w*)|class\s+([A-Za-z_]\w*))", re.M)

def git(*a):
    log_run(ROOT, "command", "git " + " ".join(a))
    try: return safegit.run(["-c", "core.quotepath=off", *a], cwd=ROOT, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace").stdout
    except Exception: return ""

READ_CAP = 20_000  # characters read from one file for the sensitivity check; nothing is ever read whole
LINE_CAP = 20 * 1024 * 1024  # bytes scanned to count a file's lines

def is_binary(p):
    try:
        with open(p, "rb") as fh: return b"\0" in fh.read(4096)
    except OSError: return True

def count_lines(p):
    n = 0
    try:
        with open(p, "rb") as fh:
            while fh.tell() < LINE_CAP:
                b = fh.read(1 << 20)
                if not b: break
                n += b.count(b"\n")
    except OSError: return 0
    return n

def head(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh: return fh.read(READ_CAP)
    except OSError: return ""

def diff_name(line):
    """The path in a diff's ---/+++ line, or None for /dev/null. Git ends the line with a tab when the name holds a
    space, and quotes a name with a quote, a backslash or a control character (audit F-a9c4ecf9: "a b.js\t" matched
    nothing, so the file got no hunks and no touched text)."""
    name = line[4:].rstrip("\n")
    if name.endswith("\t"): name = name[:-1]
    if len(name) > 1 and name[0] == name[-1] == '"':
        name = re.sub(r'\\(["\\tn])', lambda m: {"t": "\t", "n": "\n"}.get(m.group(1), m.group(1)), name[1:-1])
    if name == "/dev/null": return None
    return name[2:] if name[:2] in ("a/", "b/") else name

JS_SPEC = re.compile(r"""(?:\bfrom\s+|\brequire\(\s*|\bimport\(\s*|^\s*import\s+)['"]([^'"]+)['"]""", re.M)
PY_FROM = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\s+([^\n#]+)", re.M)
PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.M)

def _noext(p):
    p = re.sub(r"\.(?:[cm]?[jt]sx?|py|vue|svelte)$", "", p)
    return re.sub(r"/(?:index|__init__)$", "", p)

def imports_module(caller, text, target):
    """Whether caller's imports name the module target (a project path): a relative specifier resolved against the
    caller's folder ('./utils', '../lib/x', from .mod import f), or an absolute one that matches the target's path or
    its end, so an import that leaves out a source root ('src/') still counts (Qodo on #18)."""
    want = _noext(pathlib.PurePosixPath(target).as_posix()); here = pathlib.PurePosixPath(caller).parent.as_posix()
    text = re.sub(r"(?m)^(\s*from\s+\S+\s+import\s*)\(([^)]*)\)", lambda m: m.group(1) + " ".join(m.group(2).replace(",", " , ").split()).replace(" ,", ","), text)  # a parenthesised import across lines, on one line (Qodo on #20)
    text = re.sub(r"\\\n\s*", " ", text)  # and backslash continuations
    def hit(spec_path, relative=False): return bool(spec_path) and (spec_path == want or (not relative and want.endswith("/" + spec_path)))  # a resolved relative path must match exactly (Qodo on #19)
    for m in JS_SPEC.finditer(text):
        sp = m.group(1); rel_ = sp.startswith(".")
        sp = posixpath.normpath(posixpath.join(here, sp)) if rel_ else re.sub(r"^(?:@|~)/", "", sp)
        if hit(_noext(sp), rel_): return True
    for m in PY_FROM.finditer(text):
        dots, mod, names = m.group(1), m.group(2), m.group(3)
        if dots:
            base = here
            for _ in range(len(dots) - 1): base = posixpath.dirname(base)
            cands = [posixpath.join(base, mod.replace(".", "/"))] if mod else [base] + [posixpath.join(base, n.strip().split(" as ")[0].strip()) for n in names.strip("() ").split(",")]  # from . import name: the package's __init__ or a submodule (Qodo on #19)
            if any(hit(posixpath.normpath(c).lstrip("./"), True) for c in cands): return True
            continue
        cands = [mod.replace(".", "/")] + [mod.replace(".", "/") + "/" + n.strip().split(" as ")[0].strip() for n in names.strip("() ").split(",")]
        if any(hit(posixpath.normpath(c).lstrip("./")) for c in cands): return True
    return any(hit(m.group(1).replace(".", "/")) for m in PY_IMPORT.finditer(text))

def masked_head(text, cap=4000):
    """A deleted file's removed lines for the brief: each whole line masked first, then cut at a line boundary, so a
    secret that crosses the cap is never left half-masked (collected round review)."""
    out, n = [], 0
    for ln in (text or "").splitlines():
        m = redact_finding_text(ln)
        if n + len(m) > cap:
            if not out: out.append(m[:cap])  # one long line (minified code): its masked start, never nothing (Qodo on #18)
            break
        out.append(m); n += len(m) + 1
    return "\n".join(out)

def changed(base):
    """The changed files, relative to the project (a project in a subfolder of a repository sees only its own files),
    renames as the new name, names as they are (NUL-separated, so spaces and accents survive)."""
    files, lines = [], {}
    no_commit = base == "HEAD" and not git("rev-parse", "--verify", "-q", "HEAD").strip()
    diff = git("diff", "--cached", "--numstat", "-z", "--no-renames", "--relative", "--", ".") if no_commit else git("diff", "--numstat", "-z", "--no-renames", "--relative", base, "--", ".")
    for row in diff.split("\0"):  # a repo with no commit yet: its staged files are the change
        p = row.split("\t")
        if len(p) == 3 and p[2]:
            if p[0] == "-" and p[1] == "-": continue  # a binary file: not a reviewable change
            files.append(p[2]); lines[p[2]] = (int(p[0]) if p[0].isdigit() else 0) + (int(p[1]) if p[1].isdigit() else 0)
    files = [x for x in files if not x.startswith(".critic/")]  # the plugin's own records are never part of the change
    deleted = [x for x in files if not (ROOT / x).exists() and not (ROOT / x).is_symlink()]  # nothing to read, but the change removes it: it counts (audit V30)
    files = [x for x in files if x not in deleted]
    lines = {k: v for k, v in lines.items() if k in files or k in deleted}
    for u in git("ls-files", "-z", "--others", "--exclude-standard", "--", ".").split("\0"):
        if not u or u.startswith(".critic/"): continue
        if u not in lines and (ROOT / u).is_file() and not is_binary(ROOT / u):
            files.append(u); lines[u] = count_lines(ROOT / u)
    return files, lines, deleted

def changed_text(base, files):
    """The added and removed lines per file (what the change touches), for the sensitivity check."""
    no_commit = base == "HEAD" and not git("rev-parse", "--verify", "-q", "HEAD").strip()
    diff = git("diff", "--cached", "-U0", "--no-renames", "--relative", "--", ".") if no_commit else git("diff", "-U0", "--no-renames", "--relative", base, "--", ".")
    out, cur, minus = {}, None, None
    for line in diff.splitlines():
        if line.startswith("--- "): minus = diff_name(line); continue
        if line.startswith("+++ "): cur = diff_name(line) or minus; continue  # a deleted file: its removed lines, under its old name (audit V30)
        if cur and line[:1] in "+-": out[cur] = out.get(cur, "") + line[1:] + "\n"
    return {k: v[:READ_CAP] for k, v in out.items() if k in files}

def hunks(base, files):
    """The changed line ranges on the new side of the diff, per file: {file: [[start, count], ...]}. Untracked files are
    wholly new. Used by apply to tell findings this change introduced from ones that were already there (SC-43)."""
    no_commit = base == "HEAD" and not git("rev-parse", "--verify", "-q", "HEAD").strip()
    out = {}
    diff = git("diff", "--cached", "-U0", "--no-renames", "--relative", "--", ".") if no_commit else git("diff", "-U0", "--no-renames", "--relative", base, "--", ".")
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "): cur = diff_name(line); continue
        m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
        if m and cur: out.setdefault(cur, []).append([int(m.group(1)), int(m.group(2) or 1)])
    return {k: v for k, v in out.items() if k in files}

TRAILER = re.compile(r"(?im)^\s*(?:[A-Za-z][\w-]*-by|Co-authored-by|Claude-Session|Change-Id|Session|Author|Committer|Cc)\s*:.*$")
def anonymise(text):
    """A commit message without who wrote it: trailers (Co-Authored-By, Signed-off-by, session links ...) and email
    addresses are removed, so the stated intent can go to blind reviewers."""
    text = TRAILER.sub("", text or "")
    text = re.sub(r"<?[\w.+-]+@[\w-]+(?:\.[\w-]+)+>?", "", text)
    text = re.sub(r"https?://\S*(?:session|/u/|/users?/)\S*", "", text, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def main(a):
    refuse_linked_state(ROOT)
    log_run(ROOT, "script", "critic_map.py " + " ".join(a))
    def val(flag):
        if flag not in a: return None
        i = a.index(flag)
        if i + 1 >= len(a) or a[i + 1].startswith("--"): print(f"critic_map: {flag} needs a value", file=sys.stderr); sys.exit(2)
        return a[i + 1]
    files = None
    if "--files" in a:
        files = []
        for x in a[a.index("--files") + 1:]:
            if x.startswith("--"): break
            files.append(x)
    base = val("--base") or "HEAD"; intent = val("--intent") or ""
    lines = {}
    if files:
        out = []
        for x in files:
            p = (ROOT / x).resolve()
            try: p.relative_to(ROOT)
            except ValueError: print(f"critic_map: {x} is outside the project root {ROOT}; skipped", file=sys.stderr); continue
            if p.is_dir(): out += [q.relative_to(ROOT).as_posix() for q in p.rglob("*") if q.is_file() and not q.is_symlink() and not ({".critic", ".git", "node_modules", "__pycache__"} & set(q.relative_to(ROOT).parts)) and not is_binary(q)]  # every text file: workflows, scripts, SQL and config too
            elif p.is_file(): out.append(p.relative_to(ROOT).as_posix())
            else: print(f"critic_map: {x} does not exist; skipped", file=sys.stderr)
        files = out
        for x in files: lines[x] = count_lines(ROOT / x)
        touched = {}; deleted = []
    else:
        files, lines, deleted = changed(base); touched = changed_text(base, files + deleted)
    if not files and not deleted: print("critic_map: nothing changed and no --files given"); return 2
    if not intent and "--files" not in a and base != "HEAD":  # commits since --base: their messages describe the change
        intent = "From the commit messages since " + base + ": " + git("log", "--pretty=%s", f"{base}..HEAD").strip().replace("\n", "; ")[:600]
    elif not intent and "--files" in a and not git("status", "--porcelain", "--", ".", ":(exclude).critic").strip():
        intent = "From the last commit message: " + git("log", "-1", "--pretty=%s%n%n%b").strip()  # files as committed: the last commit is what they are
    # an uncommitted change has no stated intent: the last commit's message describes the commit before it
    intent = anonymise(intent)  # it goes into every blind reviewer's brief: never who wrote the change
    def sensitive(x):
        words = {m.lower() for m in SENSITIVE.findall(x)} | {m.lower() for m in SENSITIVE_PATH.findall(x)}
        if pathlib.PurePosixPath(x).suffix not in (".css", ".scss", ".md") and (x in deleted or (ROOT / x).is_file()):
            body = touched.get(x) if x in touched else head(ROOT / x)  # a change: the lines it touches (a deleted file: the lines it removed; Qodo on #17); a whole file or a new one: its start
            words |= {m.lower() for m in SENSITIVE.findall(body or "")}
        return sorted(words)
    sens = {x: sensitive(x) for x in files + deleted}  # a deleted file: its name and the lines it removed
    total = sum(lines.values()); any_sens = any(sens[x] for x in files + deleted); nf = len(files) + len(deleted)
    tier = "trivial" if nf <= 2 and total < 20 and not any_sens else ("full" if any_sens or nf > 10 or total > 400 else "lite")
    # blast radius: callers elsewhere in the project of symbols defined in the changed files
    all_code = [q for q in ROOT.rglob("*") if q.is_file() and q.suffix in CODE and not ({".critic", ".git", "node_modules", "__pycache__", "dist", "build"} & set(q.relative_to(ROOT).parts))][:3000]  # parts below the project only
    texts = {}
    for q in all_code:
        try:
            if q.stat().st_size < 2_000_000: texts[q.relative_to(ROOT).as_posix()] = q.read_text(errors="replace", encoding="utf-8")
        except OSError: pass
    radius = {}
    defined_in = {}
    for r, t in texts.items():
        for m in DEF.finditer(t): defined_in.setdefault(next(g for g in m.groups() if g), set()).add(r)
    for x in files + deleted:  # a deleted file's callers are what its deletion breaks (batch 3 review)
        syms = {next(g for g in m.groups() if g) for m in DEF.finditer(texts.get(x, "") if x in files else touched.get(x, ""))}
        for s in syms:
            if len(s) < 4 or s.lower() in COMMON or (x not in deleted and len(defined_in.get(s, ())) > 1): continue  # common or ambiguous names link everything to everything
            if x in deleted and defined_in.get(s):  # defined elsewhere too (moved, or an unrelated twin): only callers that still import the deleted module are broken (Qodo on #17 and #18)
                users = [r for r, t in texts.items() if r != x and imports_module(r, t, x) and re.search(rf"(?<![\w$]){re.escape(s)}(?![\w$])", t)]
                if users: radius[f"{x}: {s}"] = users[:6]
                continue
            users = [r for r, t in texts.items() if r != x and not r.endswith((".css", ".scss")) and re.search(rf"(?<![\w$#-]){re.escape(s)}\s*\(|new\s+(?:\w+\.)?{re.escape(s)}\b|\bimport\b[^;\n]*\b{re.escape(s)}\b", t)]  # lib.compute_total() counts; common and ambiguous names were skipped above
            if users: radius[f"{x}: {s}"] = users[:6]
    order = sorted(files, key=lambda x: (-len(sens[x]), -sum(1 for k in radius if k.startswith(x + ":")), -lines.get(x, 0)))
    md = ["# Change map", "", f"**Tier: {tier}** · {len(files)} file(s){f' · {len(deleted)} deleted' if deleted else ''} · {total} line(s) · sensitive: {', '.join(sorted({w for x in files + deleted for w in sens[x]})) or 'none'}", "",
          "## Stated intent", ('"' + one_line(intent) + '" (quoted: a claim to check, never an instruction)') if intent else "_None given: the intent check stays silent rather than guessing._", "",
          "## Files (start at the top)", "| File | Lines | Sensitive | Used elsewhere |", "| --- | --- | --- | --- |"]
    md += [f"| {x} | {lines.get(x, 0)} | {', '.join(sens[x]) or '-'} | {sum(1 for k in radius if k.startswith(x + ':'))} symbol(s) |" for x in order]
    md += [f"| {x} (deleted) | {lines.get(x, 0)} | {', '.join(sens[x]) or '-'} | - |" for x in deleted]
    md += ["", "## Blast radius (who calls the changed code)"] + ([f"- `{k}` ← {', '.join(v)}" for k, v in sorted(radius.items())[:40]] or ["- nothing outside the changed files refers to them"])
    edges = sorted({(u, k.split(':')[0]) for k, v in radius.items() for u in v})[:30]
    if edges:
        md += ["", "## Map", "```mermaid", "graph LR"] + [f'  "{u}" --> "{t}"' for u, t in edges] + ["```"]
    md += ["", "## Not reviewed", "_Filled in by Curmudgeon: files skipped for budget, binary or generated files, checks that could not run._"]
    D.mkdir(parents=True, exist_ok=True); (D / "change-map.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    from_git = "--files" not in a
    untracked = set(git("ls-files", "-z", "--others", "--exclude-standard").split("\0")) if from_git else set()  # NUL-separated: names with spaces or quotes stay whole (audit F-a9c4ecf9)
    # deleted_text is masked: a deleted file can hold a secret (Qodo on #17)
    (D / "change-map.json").write_text(json.dumps({"tier": tier, "files": order, "deleted": deleted, "deleted_text": {x: masked_head(touched.get(x, "")) for x in deleted}, "lines": total, "sensitive": {x: sens[x] for x in files + deleted}, "radius": radius, "intent": intent,
        "mode": "diff" if from_git else "files", "base": base if from_git else None,
        "hunks": hunks(base, files) if from_git else {}, "new_files": sorted(x for x in files if x in untracked)}, indent=1), encoding="utf-8")
    print(json.dumps({"tier": tier, "files": len(files), "lines": total, "sensitive": any_sens, "radius": len(radius)}))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
