#!/usr/bin/env python3
"""Change map and risk tier for a Curmudgeon run: how much review this change needs, where to start, and what else it
can break. Written to .critic/change-map.md (kept separate from the findings).

usage: critic_map.py [--files PATH ...] [--base GIT_REF] [--intent "what the change is meant to do"]
Without --files it uses `git diff --name-only` against --base (default HEAD), plus untracked files.

Tier: trivial (≤2 files, <20 changed lines, nothing sensitive), full (anything sensitive, >10 files or >400
lines), else lite. The tier sets the review size: trivial = one reviewer and no verification; lite = one reviewer
plus verification of Critical/High; full = three blind reviewers, verification and the full sandbox."""
import json, os, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import log_run, refuse_linked_state

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
# whole words only ("author" is not "auth"); paths may also match folder-style names
SENSITIVE = re.compile(r"(?<![A-Za-z])(auth|authn|authz|authenticate\w*|authoriz\w*|login|logout|sessions?|passwords?|secrets?|payments?|billing|refunds?|checkout|invoices?|crypto|encrypt\w*|decrypt\w*|permissions?|admin|migrations?|webhooks?|uploads?|credentials?|api[_-]?keys?|private[_-]?keys?|tokens?|jwts?|oauth\w*|sso|saml|roles?|rbac|acls?|security|privacy|pii|gdpr|csrf|xsrf|cors|csp|signatures?|hmac|hash(?:es|ing)?|salt|sanitiz\w*|schemas?)(?![A-Za-z])", re.I)
SENSITIVE_PATH = re.compile(r"(?:^|/)(\.env[\w.]*|config|settings|security|privacy|auth|admin|migrations?|schema)(?:/|\.|$)", re.I)
COMMON = {"main", "init", "run", "setup", "render", "test", "handle", "get", "set", "update", "load", "save", "start", "stop", "close", "open", "create", "delete", "parse", "read", "write", "show", "reset", "build", "apply", "check", "process"}
CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".html", ".css", ".vue", ".svelte", ".go", ".rb", ".php", ".java", ".cs", ".rs"}
DEF = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\*?\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(|def\s+([A-Za-z_]\w*)|class\s+([A-Za-z_]\w*))", re.M)

def git(*a):
    log_run(ROOT, "command", "git " + " ".join(a))
    try: return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout
    except Exception: return ""

def changed(base):
    files, lines = [], {}
    no_commit = base == "HEAD" and not git("rev-parse", "--verify", "-q", "HEAD").strip()
    for row in (git("diff", "--cached", "--numstat") if no_commit else git("diff", "--numstat", base)).splitlines():  # a repo with no commit yet: its staged files are the change
        p = row.split("\t")
        if len(p) == 3: files.append(p[2]); lines[p[2]] = (int(p[0]) if p[0].isdigit() else 0) + (int(p[1]) if p[1].isdigit() else 0)
    files = [x for x in files if not x.startswith(".critic/")]  # the plugin's own records are never part of the change
    lines = {k: v for k, v in lines.items() if not k.startswith(".critic/")}
    for u in git("ls-files", "--others", "--exclude-standard").splitlines():
        if u.startswith(".critic/"): continue
        if u not in lines and (ROOT / u).is_file():
            files.append(u)
            try: lines[u] = len((ROOT / u).read_text(errors="replace").splitlines())
            except OSError: lines[u] = 0
    return files, lines

def hunks(base, files):
    """The changed line ranges on the new side of the diff, per file: {file: [[start, count], ...]}. Untracked files are
    wholly new. Used by apply to tell findings this change introduced from ones that were already there (SC-43)."""
    no_commit = base == "HEAD" and not git("rev-parse", "--verify", "-q", "HEAD").strip()
    out = {}
    diff = git("diff", "--cached", "-U0") if no_commit else git("diff", "-U0", base)
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "): cur = line[6:] if line.startswith("+++ b/") else None; continue
        m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
        if m and cur: out.setdefault(cur, []).append([int(m.group(1)), int(m.group(2) or 1)])
    return {k: v for k, v in out.items() if k in files}

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
            if p.is_dir(): out += [str(q.relative_to(ROOT)) for q in p.rglob("*") if q.is_file() and q.suffix in CODE and not ({".critic", ".git", "node_modules", "__pycache__"} & set(q.parts))]
            elif p.is_file(): out.append(str(p.relative_to(ROOT)))
            else: print(f"critic_map: {x} does not exist; skipped", file=sys.stderr)
        files = out
        for x in files:
            try: lines[x] = len((ROOT / x).read_text(errors="replace").splitlines())
            except OSError: lines[x] = 0
    else:
        files, lines = changed(base)
    if not files: print("critic_map: nothing changed and no --files given"); return 2
    if not intent: intent = git("log", "-1", "--pretty=%s%n%n%b").strip()
    def sensitive(x):
        words = {m.lower() for m in SENSITIVE.findall(x)} | {m.lower() for m in SENSITIVE_PATH.findall(x)}
        if (ROOT / x).is_file() and (ROOT / x).suffix not in (".css", ".scss", ".md"):
            words |= {m.lower() for m in SENSITIVE.findall((ROOT / x).read_text(errors="replace")[:20000])}
        return sorted(words)
    sens = {x: sensitive(x) for x in files}
    total = sum(lines.values()); any_sens = any(sens[x] for x in files)
    tier = "trivial" if len(files) <= 2 and total < 20 and not any_sens else ("full" if any_sens or len(files) > 10 or total > 400 else "lite")
    # blast radius: callers elsewhere in the project of symbols defined in the changed files
    all_code = [q for q in ROOT.rglob("*") if q.is_file() and q.suffix in CODE and not ({".critic", ".git", "node_modules", "__pycache__", "dist", "build"} & set(q.parts))][:3000]
    texts = {}
    for q in all_code:
        try: texts[str(q.relative_to(ROOT))] = q.read_text(errors="replace")
        except OSError: pass
    radius = {}
    defined_in = {}
    for r, t in texts.items():
        for m in DEF.finditer(t): defined_in.setdefault(next(g for g in m.groups() if g), set()).add(r)
    for x in files:
        syms = {next(g for g in m.groups() if g) for m in DEF.finditer(texts.get(x, ""))}
        for s in syms:
            if len(s) < 4 or s.lower() in COMMON or len(defined_in.get(s, ())) > 1: continue  # common or ambiguous names link everything to everything
            users = [r for r, t in texts.items() if r != x and not r.endswith((".css", ".scss")) and re.search(rf"(?<![\w$.#-]){re.escape(s)}\s*\(|new\s+{re.escape(s)}\b|\bimport\b[^;\n]*\b{re.escape(s)}\b", t)]
            if users: radius[f"{x}: {s}"] = users[:6]
    order = sorted(files, key=lambda x: (-len(sens[x]), -sum(1 for k in radius if k.startswith(x + ":")), -lines.get(x, 0)))
    md = ["# Change map", "", f"**Tier: {tier}** · {len(files)} file(s) · {total} line(s) · sensitive: {', '.join(sorted({w for x in files for w in sens[x]})) or 'none'}", "",
          "## Stated intent", intent or "_None given: the intent check stays silent rather than guessing._", "",
          "## Files (start at the top)", "| File | Lines | Sensitive | Used elsewhere |", "| --- | --- | --- | --- |"]
    md += [f"| {x} | {lines.get(x, 0)} | {', '.join(sens[x]) or '-'} | {sum(1 for k in radius if k.startswith(x + ':'))} symbol(s) |" for x in order]
    md += ["", "## Blast radius (who calls the changed code)"] + ([f"- `{k}` ← {', '.join(v)}" for k, v in sorted(radius.items())[:40]] or ["- nothing outside the changed files refers to them"])
    edges = sorted({(u, k.split(':')[0]) for k, v in radius.items() for u in v})[:30]
    if edges:
        md += ["", "## Map", "```mermaid", "graph LR"] + [f'  "{u}" --> "{t}"' for u, t in edges] + ["```"]
    md += ["", "## Not reviewed", "_Filled in by Curmudgeon: files skipped for budget, binary or generated files, checks that could not run._"]
    D.mkdir(parents=True, exist_ok=True); (D / "change-map.md").write_text("\n".join(md) + "\n")
    from_git = "--files" not in a
    untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines()) if from_git else set()
    (D / "change-map.json").write_text(json.dumps({"tier": tier, "files": order, "lines": total, "sensitive": {x: sens[x] for x in files}, "radius": radius, "intent": intent,
        "mode": "diff" if from_git else "files", "base": base if from_git else None,
        "hunks": hunks(base, files) if from_git else {}, "new_files": sorted(x for x in files if x in untracked)}, indent=1))
    print(json.dumps({"tier": tier, "files": len(files), "lines": total, "sensitive": any_sens, "radius": len(radius)}))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
