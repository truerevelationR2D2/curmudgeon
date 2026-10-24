"""Dependency checks for Curmudgeon scan. The idea comes from OSV-Scanner (Apache-2.0); no install is needed.
Offline: unpinned or wildcard versions, git/URL dependencies, install-time scripts, packages listed twice.
Online (--online): asks the free public OSV database (api.osv.dev) about the exact versions in lockfiles. When the
network is blocked the check reports "unavailable"; it never guesses."""
import json, pathlib, re, urllib.request
from critic_findings import log_run

def _lock_npm(p):
    try: j = json.loads(p.read_text())
    except Exception: return []
    out = []
    for path, meta in (j.get("packages") or {}).items():
        if not path or not isinstance(meta, dict) or not meta.get("version"): continue
        out.append(("npm", path.split("node_modules/")[-1], meta["version"], meta.get("dev", False)))
    if not out:
        for name, meta in (j.get("dependencies") or {}).items():
            if isinstance(meta, dict) and meta.get("version"): out.append(("npm", name, meta["version"], meta.get("dev", False)))
    return out

COPYLEFT = re.compile(r"\b(A?GPL|SSPL|EUPL|OSL|CC-BY-SA|CC-BY-NC)", re.I)  # LGPL/MPL are weaker; reported as NOTE
WEAK = re.compile(r"\b(LGPL|MPL|EPL|CDDL)", re.I)
PERMISSIVE = re.compile(r"^(MIT(-0)?|ISC|0BSD|BSD-[0-4]-Clause(-\w+)?|BSD|Apache-2\.0|Apache-1\.1|Zlib|Unlicense|CC0-1\.0|CC-BY-[34]\.0|WTFPL|BlueOak-1\.0\.0|Python-2\.0|PSF-2\.0|Artistic-2\.0|BSL-1\.0|Unicode-DFS-2016|Unicode-3\.0|X11|AFL-[23]\.\d|Ruby|PostgreSQL|NCSA)(\+)?$", re.I)
def _one(term):
    """strong / weak copyleft, a recognised permissive licence, or unknown (UNLICENSED, LicenseRef-…, SEE LICENSE IN …,
    NOASSERTION, typos): unknown is never assumed permissive."""
    if COPYLEFT.search(term) and not WEAK.search(term): return "strong"
    if WEAK.search(term): return "weak"
    return "permissive" if PERMISSIVE.match(term.strip()) else "unknown"
RANK = {"permissive": 0, "unknown": 1, "weak": 2, "strong": 3}
def spdx_kind(expr):
    """Reads an SPDX expression with its parentheses: OR lets you pick the least restrictive side, AND makes every
    part apply, so the most restrictive counts. "MIT OR GPL-3.0" is permissive; "GPL-3.0 AND (MIT OR Apache-2.0)"
    is strong. An expression that doesn't parse is judged by its most restrictive name (the safe side)."""
    toks = re.findall(r"\(|\)|[^\s()]+", expr); pos = [0]
    if toks.count("(") > 50 or len(toks) > 400:  # absurd nesting or length: judge by the strictest name in it (the safe side)
        return max((_one(t) for t in toks if t not in ("(", ")")), key=RANK.get, default="permissive")
    def peek(): return toks[pos[0]].upper() if pos[0] < len(toks) else None
    def take(): pos[0] += 1; return toks[pos[0] - 1]
    def factor():
        if peek() == "(":
            take(); k = alt()
            if peek() != ")": raise ValueError("unbalanced")
            take(); return k
        if peek() in (None, ")", "AND", "OR", "WITH"): raise ValueError("expected a licence")
        k = _one(take())
        if peek() == "WITH": take(); take()  # an exception (for example Classpath-exception) never makes it stricter
        return k
    def term():
        k = factor()
        while peek() == "AND": take(); k = max(k, factor(), key=RANK.get)
        return k
    def alt():
        k = term()
        while peek() == "OR": take(); k = min(k, term(), key=RANK.get)
        return k
    try:
        k = alt()
        if pos[0] != len(toks): raise ValueError("trailing text")
        return k
    except (ValueError, IndexError, RecursionError):
        return max((_one(t) for t in toks if t not in ("(", ")")), key=RANK.get, default="permissive")

def licences(root, emit):
    """Licence check, offline: the project's own licence field, then every locked npm package's declared licence.
    Missing or unusual licences are NOTE; strong copyleft (GPL, AGPL, SSPL...) is WARN, since shipping it inside closed
    code has obligations. Informational, never legal advice. Idea from license checkers such as licensee (MIT)."""
    for pj in root.rglob("package.json"):
        if _skip(pj, root): continue
        try: j = json.loads(pj.read_text())
        except Exception: continue
        if not j.get("private") and not j.get("license"): emit("NOTE", "licence-missing-own", "deps", str(pj.relative_to(root)), "the package declares no licence: others can't legally reuse it", "")
    for lf in root.rglob("package-lock.json"):
        if _skip(lf, root): continue
        try: j = json.loads(lf.read_text())
        except Exception: continue
        missing, strong, weak, unknown = [], [], [], []
        if not j.get("packages") and j.get("dependencies"):
            emit("NOTE", "licence-not-checked", "deps", str(lf.relative_to(root)), "an old (v1) lockfile records no licences, so dependency licences were not checked (npm 7+ writes them)", ""); continue
        for path, meta in (j.get("packages") or {}).items():
            if not path or not isinstance(meta, dict): continue
            if meta.get("link") or "node_modules/" not in path: continue  # workspace links and the project itself aren't third-party packages
            name = path.split("node_modules/")[-1]; lic = meta.get("license")
            lic = lic.get("type") if isinstance(lic, dict) else lic
            if not lic: missing.append(name); continue
            kind = spdx_kind(str(lic))
            if kind == "strong": strong.append(f"{name} ({lic})")
            elif kind == "weak": weak.append(f"{name} ({lic})")
            elif kind == "unknown": unknown.append(f"{name} ({lic})")
        rel = str(lf.relative_to(root))
        if strong: emit("WARN", "licence-copyleft", "deps", rel, f"{len(strong)} package(s) under a strong copyleft licence: {', '.join(strong[:5])}{' …' if len(strong) > 5 else ''} (check the obligations before shipping)", "")
        if weak: emit("NOTE", "licence-weak-copyleft", "deps", rel, f"{len(weak)} package(s) under a weak copyleft licence: {', '.join(weak[:5])}{' …' if len(weak) > 5 else ''}", "")
        if unknown: emit("NOTE", "licence-unknown", "deps", rel, f"{len(unknown)} package(s) under a licence that isn't a recognised open-source one (check the terms): {', '.join(unknown[:5])}{' …' if len(unknown) > 5 else ''}", "")
        if missing: emit("NOTE", "licence-missing", "deps", rel, f"{len(missing)} package(s) declare no licence in the lockfile: {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}", "")

def _reqs(p):
    out = []
    for line in p.read_text(errors="replace").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.\-\[\]]+)\s*==\s*([\w.\-+]+)", line)
        if m: out.append(("PyPI", re.sub(r"\[.*\]", "", m.group(1)), m.group(2), False))
    return out

SKIP = {"node_modules", ".critic", ".venv", "venv", ".git"}  # never our own outputs or restore copies, never vendored code
def _skip(p, root): return bool(SKIP & set(p.relative_to(root).parts))

def scan(root, emit, online=False, state=None):
    found_manifest = False
    try: licences(root, emit)
    except Exception: pass  # informational; never blocks the dependency check
    for pj in root.rglob("package.json"):
        if _skip(pj, root): continue
        found_manifest = True; rel = str(pj.relative_to(root))
        try: j = json.loads(pj.read_text())
        except Exception: emit("WARN", "deps-manifest", "deps", rel, "package.json is not valid JSON", ""); continue
        for k in ("preinstall", "install", "postinstall", "prepare"):
            if (j.get("scripts") or {}).get(k): emit("NOTE", "deps-install-script", "deps", rel, f"`{k}` script runs on every install: check what it does", j["scripts"][k][:100])
        both = set(j.get("dependencies") or {}) & set(j.get("devDependencies") or {})
        for n in sorted(both): emit("NOTE", "deps-duplicate", "deps", rel, f"`{n}` is in both dependencies and devDependencies", "")
        for sect in ("dependencies", "devDependencies", "optionalDependencies"):
            for n, v in (j.get(sect) or {}).items():
                v = str(v)
                if v in ("*", "latest", "") or v.startswith(">="): emit("WARN", "deps-unpinned", "deps", rel, f"`{n}` accepts any future version ({v or 'empty'}): a bad release goes straight in", "")
                elif re.match(r"^(git|https?|github:|file:)", v) or "/" in v and not v.startswith("@"): emit("NOTE", "deps-url", "deps", rel, f"`{n}` comes from a URL or repo ({v[:60]}), not the registry", "")
        if not (pj.parent / "package-lock.json").exists() and not (pj.parent / "yarn.lock").exists() and not (pj.parent / "pnpm-lock.yaml").exists() and (j.get("dependencies") or j.get("devDependencies")):
            emit("NOTE", "deps-no-lock", "deps", rel, "no lockfile: installs can differ from machine to machine", "")
    pkgs = []
    for lf in root.rglob("package-lock.json"):
        if not _skip(lf, root): pkgs += [(lf, *x) for x in _lock_npm(lf)]; found_manifest = True
    for rf in root.rglob("requirements*.txt"):
        if not _skip(rf, root): pkgs += [(rf, *x) for x in _reqs(rf)]; found_manifest = True
    if not found_manifest:
        if state: state("deps", "n/a", "no package manifest or lockfile")
        return
    if not online:
        if state: state("deps", "pass", f"{len(pkgs)} pinned packages; vulnerability lookup off (use --online)")
        return
    if not pkgs:
        if state: state("deps", "pass", "no pinned versions to look up")
        return
    vulns = 0
    try:
        for i in range(0, len(pkgs), 500):
            batch = pkgs[i:i + 500]
            body = json.dumps({"queries": [{"package": {"name": n, "ecosystem": eco}, "version": v} for _, eco, n, v, _ in batch]}).encode()
            log_run(root, "network", f"OSV lookup (--online): {len(batch)} package name(s) and version(s) sent to api.osv.dev")
            req = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=body, headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=20).read())
            for (lf, eco, n, v, dev), r in zip(batch, res.get("results", [])):
                ids = [x.get("id") for x in (r.get("vulns") or [])]
                if ids:
                    vulns += 1
                    emit("NOTE" if dev else "WARN", "deps-vulnerable", "deps", str(lf.relative_to(root)), f"{n} {v} has known vulnerabilities: {', '.join(ids[:5])}{' (dev only)' if dev else ''}", "")
        if state: state("deps", "fail" if vulns else "pass", f"{len(pkgs)} packages looked up in OSV, {vulns} vulnerable")
    except Exception as e:
        if state: state("deps", "unavailable", f"OSV lookup failed ({type(e).__name__}); offline checks still ran")
