"""Dependency checks for Curmudgeon scan. The idea comes from OSV-Scanner (Apache-2.0); no install is needed.
Offline: unpinned or wildcard versions, git/URL dependencies, install-time scripts, packages listed twice.
Online (--online): asks the free public OSV database (api.osv.dev) about the exact versions in lockfiles. When the
network is blocked the check reports "unavailable"; it never guesses."""
import json, pathlib, re, urllib.request

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
        if state: state("deps", "blocked", "no package manifest or lockfile")
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
