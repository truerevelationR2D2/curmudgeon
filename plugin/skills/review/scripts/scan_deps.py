"""Dependency checks for Curmudgeon scan. The idea comes from OSV-Scanner (Apache-2.0); no install is needed.
Offline: unpinned or wildcard versions, git/URL dependencies, install-time scripts, packages listed twice.
Online (--online): asks the free public OSV database (api.osv.dev) about the exact versions in lockfiles. When the
network is blocked the check reports "unavailable"; it never guesses."""
import json, pathlib, re, sys, urllib.request
from critic_findings import log_run

UNREAD_LOCKS = ("yarn.lock", "pnpm-lock.yaml")  # lockfiles whose format is not read: their packages are never counted as checked

def _lock_npm(p):
    """(ecosystem, name, version, dev) for each package in a package-lock.json. Raises ValueError when the file can't be
    read, so the caller reports it instead of passing it as "0 packages"."""
    try: j = json.loads(p.read_text(encoding="utf-8-sig"))  # a BOM is allowed
    except (OSError, ValueError) as e: raise ValueError(f"not readable as JSON: {type(e).__name__}") from None
    if not isinstance(j, dict): raise ValueError("not a lockfile object")
    out = []
    for path, meta in (j.get("packages") or {}).items():
        if not path or not isinstance(meta, dict) or not meta.get("version"): continue
        if "node_modules/" not in path or meta.get("link"): continue  # a workspace folder (packages/internal-x) is not a registry package, and its path never goes to OSV
        out.append(("npm", meta.get("name") or path.split("node_modules/")[-1], meta["version"], meta.get("dev", False)))  # an alias (mylodash: npm:lodash@4) records its real name
    if not out:  # lockfile version 1: nested dependencies, each possibly an alias ("npm:real@1.0.0" in version)
        def walk(deps):
            for name, meta in (deps or {}).items():
                if not isinstance(meta, dict): continue
                v = str(meta.get("version") or "")
                m = re.match(r"^npm:((?:@[^/@]+/)?[^@]+)@(.+)$", v)
                if m: name, v = m.group(1), m.group(2)
                if v: out.append(("npm", name, v, meta.get("dev", False)))
                walk(meta.get("dependencies"))
        walk(j.get("dependencies"))
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

DEV_REQS = re.compile(r"(?i)(^|[-_.])(dev|test|tests|testing|lint|docs?)([-_.]|$)")
def _reqs(p, wildcards=None):
    """Exact pins (name==version) in a requirements file. A file named for development (requirements-dev.txt,
    requirements_test.txt, dev-requirements.txt) is dev-only. A wildcard pin (==1.0.*) is not a version: it is never
    looked up, and its name goes to wildcards so the scan can say so."""
    out = []; dev = bool(DEV_REQS.search(p.name.replace("requirements", "")))
    for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.\-\[\]]+)\s*===?\s*([\w.\-+*!]+)", line)
        if not m: continue
        name = re.sub(r"\[.*\]", "", m.group(1))
        if "*" in m.group(2):
            if wildcards is not None: wildcards.append(f"{name}=={m.group(2)}")
            continue
        out.append(("PyPI", name, m.group(2), dev))
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
                if v in ("*", "latest", "") or (v.startswith(">") and "<" not in v): emit("WARN", "deps-unpinned", "deps", rel, f"`{n}` accepts any future version ({v or 'empty'}): a bad release goes straight in", "")
                elif re.match(r"^(git|https?|github:|file:)", v) or "/" in v and not v.startswith(("@", "npm:")): emit("NOTE", "deps-url", "deps", rel, f"`{n}` comes from a URL or repo ({v[:60]}), not the registry", "")
        if not (pj.parent / "package-lock.json").exists() and not (pj.parent / "yarn.lock").exists() and not (pj.parent / "pnpm-lock.yaml").exists() and (j.get("dependencies") or j.get("devDependencies")):
            emit("NOTE", "deps-no-lock", "deps", rel, "no lockfile: installs can differ from machine to machine", "")
    pkgs = []; unread = []; wild = []
    for lf in root.rglob("package-lock.json"):
        if _skip(lf, root): continue
        found_manifest = True
        try: pkgs += [(lf, *x) for x in _lock_npm(lf)]
        except ValueError as e:
            unread.append(str(lf.relative_to(root)))
            emit("WARN", "deps-lock-unreadable", "deps", str(lf.relative_to(root)), f"the lockfile can't be read ({e}): none of its packages were checked", "")
    for n in UNREAD_LOCKS:
        for x in root.rglob(n):
            if _skip(x, root) or (x.parent / "package-lock.json").exists(): continue
            found_manifest = True; unread.append(str(x.relative_to(root)))
            emit("WARN", "deps-lock-unread", "deps", str(x.relative_to(root)), f"{n} is not a format the dependency check reads: none of its packages were checked for known vulnerabilities", "")
    for rf in root.rglob("requirements*.txt"):
        if not _skip(rf, root): pkgs += [(rf, *x) for x in _reqs(rf, wild)]; found_manifest = True
    if wild: emit("NOTE", "deps-not-exact", "deps", "requirements", f"{len(wild)} wildcard pin(s) are not exact versions, so they were not looked up: {', '.join(wild[:5])}{' …' if len(wild) > 5 else ''}", "")
    gap = f"; {len(unread)} lockfile(s) not read: {', '.join(unread[:3])}" if unread else ""
    if not found_manifest:
        if state: state("deps", "n/a", "no package manifest or lockfile")
        return
    if not online:
        try:
            import security_feed; cfg = security_feed.load_cfg(); got = security_feed.match(pkgs)
        except Exception as e:  # never a silent pass when the user switched the feed on
            got = ([], 0, len(pkgs), f"the feed check failed ({type(e).__name__})") if "security_feed" in sys.modules and security_feed.switched_on(cfg) else None
        if got is None:
            if state: state("deps", "pass", f"{len(pkgs)} pinned packages; vulnerability lookup off (use --online, or switch on the local security feed)" + gap)
            return
        rows, checked, unchecked, problem = got
        if problem:  # switched on but unreadable: never reported as a pass with the lookup off
            emit("WARN", "deps-feed-unreadable", "deps", "lockfiles", f"the local security database could not be read: {problem}; no package was checked against it", "")
            if state: state("deps", "blocked", f"the local security database could not be read ({problem}); {len(pkgs)} packages not checked")
            return
        if unchecked: emit("NOTE", "deps-feed-gap", "deps", "lockfiles", f"{unchecked} package(s) were not checked: the local security feed has no readable table for their ecosystem (run security_feed.py update, or add the ecosystem)", "")
        for lf, eco, n, v, dev, ids, exploited in rows:  # SC-75: the local feed copy; nothing about the project left the machine
            sev = "FAIL" if exploited and not dev else "NOTE" if dev else "WARN"
            emit(sev, "deps-vulnerable", "deps", str(lf.relative_to(root)), f"{n} {v} has known vulnerabilities: {', '.join(ids[:5])}{' — exploited in the wild (CISA KEV)' if exploited else ''}{' (dev only)' if dev else ''}", "")
        worst = "fail" if any(not dev for *_, dev, _ids, _x in rows) else "pass"  # a dev-only package is a NOTE, so it doesn't fail the check
        if unread and worst == "pass": worst = "unavailable"  # a lockfile nobody read is not a pass
        if state: state("deps", worst, f"{checked} of {len(pkgs)} packages checked against the local security feed of {str(cfg.get('last_update', ''))[:10]} (nothing sent), {len(rows)} vulnerable"
                        + (f" ({sum(1 for r in rows if r[4])} dev only)" if any(r[4] for r in rows) else "") + (f"; {unchecked} not checked (no table for their ecosystem)" if unchecked else "") + gap)
        return
    if not pkgs:
        if state: state("deps", "unavailable" if unread else "pass", "no pinned versions to look up" + gap)
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
                    vulns += not dev
                    emit("NOTE" if dev else "WARN", "deps-vulnerable", "deps", str(lf.relative_to(root)), f"{n} {v} has known vulnerabilities: {', '.join(ids[:5])}{' (dev only)' if dev else ''}", "")
        if state: state("deps", "fail" if vulns else "unavailable" if unread else "pass", f"{len(pkgs)} packages looked up in OSV, {vulns} vulnerable outside dev" + gap)
    except Exception as e:
        if state: state("deps", "unavailable", f"OSV lookup failed ({type(e).__name__}); offline checks still ran")
