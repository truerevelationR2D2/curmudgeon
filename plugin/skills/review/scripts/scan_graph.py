"""Code-structure checks for Curmudgeon scan, in our own code. Ideas from dependency-cruiser (layer rules, cycles),
knip (dead code, unused exports) and jscpd (copy-paste); none of their code or rule text is used.

Layer rules: by default files are placed in layers by folder or file name (ui: ui, components, views, pages,
screens, app; domain: domain, model(s), core, logic, rules; data: data, api, store, repository, db, services, client).
domain -> ui and data -> ui imports are flagged. Projects can override in .critic/rules.md:
    ## Boundaries
    layer ui: src/components/** src/views/**
    forbid: domain -> ui
"""
import ast, fnmatch, hashlib, pathlib, re

JS = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"}
IMPORT = re.compile(r"""(?:^|\s)import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]|\bimport\(\s*['"]([^'"]+)['"]\s*\)|\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
EXPORT_NAMED = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.M)
DEFS = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", re.M)
DEFAULT_LAYERS = {"ui": ["ui", "components", "component", "views", "view", "pages", "screens", "widgets"],
                  "domain": ["domain", "model", "models", "core", "logic", "rules", "entities"],
                  "data": ["data", "api", "store", "stores", "repository", "repositories", "db", "services", "client", "clients"]}
DEFAULT_FORBID = [("domain", "ui"), ("data", "ui")]

def read_rules(root):
    layers, forbid = {}, []
    p = root / ".critic" / "rules.md"
    if not p.exists(): return None, None
    sec = False
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "): sec = line.strip().lower() == "## boundaries"; continue
        if not sec: continue
        m = re.match(r"\s*layer\s+(\w+)\s*:\s*(.+)", line)
        if m: layers[m.group(1)] = m.group(2).split()
        m = re.match(r"\s*forbid\s*:\s*(\w+)\s*->\s*(\w+)", line)
        if m: forbid.append((m.group(1), m.group(2)))
    return (layers or None), (forbid or None)

def layer_of(rel, layers, custom):
    parts = [x.lower() for x in pathlib.PurePath(rel).parts]; stem = pathlib.PurePath(rel).stem.lower()
    for name, pats in layers.items():
        if custom:
            if any(fnmatch.fnmatch(rel, g) for g in pats): return name
        elif any(p in pats for p in parts[:-1]) or stem in pats: return name
    return None

def resolve(src_rel, spec, files):
    if not spec.startswith("."): return None
    base = pathlib.PurePosixPath(src_rel).parent
    cand = (base / spec).as_posix()
    parts = []
    for seg in cand.split("/"):
        if seg == "..": parts and parts.pop()
        elif seg not in (".", ""): parts.append(seg)
    cand = "/".join(parts)
    for c in (cand, *(cand + e for e in JS), *(cand + "/index" + e for e in JS)):
        if c in files: return c
    return None

def python_graph(py):
    """Module-level imports between the Python files in scope, read with ast (imports inside functions are left out:
    they are how Python code breaks a cycle on purpose). Relative imports resolve from the file's folder; absolute
    ones match a dotted path that only one file in scope can be. Files that don't parse add no edges."""
    names = {}
    for r in py:
        parts = list(pathlib.PurePosixPath(r).with_suffix("").parts)
        if parts[-1] == "__init__": parts = parts[:-1]
        for k in range(len(parts)):
            names.setdefault(".".join(parts[k:]), set()).add(r)
    def unique(dotted):
        hit = names.get(dotted)
        return next(iter(hit)) if hit and len(hit) == 1 else None
    graph = {r: set() for r in py}
    for r, t in py.items():
        try: tree = ast.parse(t)
        except (SyntaxError, ValueError): continue
        pkg = list(pathlib.PurePosixPath(r).parent.parts)
        def top(nodes):
            for n in nodes:
                if isinstance(n, (ast.If, ast.Try)) or type(n).__name__ == "TryStar":
                    yield from top(getattr(n, "body", []) + getattr(n, "orelse", []) + [x for h in getattr(n, "handlers", []) for x in h.body] + getattr(n, "finalbody", []))
                elif isinstance(n, (ast.Import, ast.ImportFrom)): yield n
        for n in top(tree.body):
            cands = []
            if isinstance(n, ast.Import): cands = [a.name for a in n.names]
            elif n.level:
                base = pkg[: len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                mod = base + (n.module.split(".") if n.module else [])
                cands = [".".join(mod + [a.name]) for a in n.names] + [".".join(mod)]
                for c in cands:
                    path = "/".join(c.split("."))
                    for tgt in (path + ".py", path + "/__init__.py"):
                        if tgt in py and tgt != r: graph[r].add(tgt); break
                continue
            else: cands = [f"{n.module}.{a.name}" for a in n.names] + [n.module]
            for c in cands:
                tgt = unique(c)
                if tgt and tgt != r: graph[r].add(tgt); break
    return graph

def scan(root, texts, emit):
    """texts: {rel_path: text} for every source file in scope (posix rel paths). Builds the import graph for
    JavaScript/TypeScript and Python, and returns the file types it could not analyse."""
    js = {r: t for r, t in texts.items() if pathlib.PurePath(r).suffix in JS}
    py = {r: t for r, t in texts.items() if pathlib.PurePath(r).suffix == ".py"}
    layers, forbid = read_rules(root); custom = layers is not None
    layers = layers or DEFAULT_LAYERS; forbid = forbid or DEFAULT_FORBID
    graph = {r: set() for r in js}
    for r, t in js.items():
        for m in IMPORT.finditer(t):
            spec = next(g for g in m.groups() if g)
            tgt = resolve(r, spec, js)
            if tgt: graph[r].add(tgt)
    graph.update(python_graph(py))
    edges = sum(len(v) for v in graph.values())
    # layer rules
    for r, deps in graph.items():
        la = layer_of(r, layers, custom)
        for d in deps:
            lb = layer_of(d, layers, custom)
            if la and lb and (la, lb) in forbid:
                emit("WARN", "boundary", "domain", r, f"{la} code imports {lb} code ({d}): the {la} layer must not depend on the {lb} layer", "")
    # cycles (Tarjan)
    idx, low, on, st, out, n = {}, {}, set(), [], [], [0]
    def sc(v):
        idx[v] = low[v] = n[0]; n[0] += 1; st.append(v); on.add(v)
        for w in graph[v]:
            if w not in idx: sc(w); low[v] = min(low[v], low[w])
            elif w in on: low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v: break
            if len(comp) > 1 or v in graph[v]: out.append(sorted(comp))
    import sys; sys.setrecursionlimit(10000)
    for v in graph:
        if v not in idx: sc(v)
    for comp in out: emit("WARN", "import-cycle", "structure", comp[0], "import cycle: " + " → ".join(comp + [comp[0]]), "")
    # unused exports (module code only) and unreferenced functions (all code)
    all_text = "\n".join(texts.values())
    imported_names = set()
    for t in js.values():
        for m in re.finditer(r"import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from", t):
            if m.group(1): imported_names.add(m.group(1))
            for nm in (m.group(2) or "").split(","):
                nm = nm.strip().split(" as ")[0].strip()
                if nm: imported_names.add(nm)
    if edges:
        for r, t in js.items():
            for m in EXPORT_NAMED.finditer(t):
                name = m.group(1)
                if name not in imported_names and len(re.findall(rf"(?<![\w$]){re.escape(name)}(?![\w$])", all_text)) <= 1:
                    emit("NOTE", "unused-export", "structure", f"{r}:{t[:m.start()].count(chr(10)) + 1}", f"export `{name}` is never imported or used", "")
    for r, t in js.items():
        for m in DEFS.finditer(t):
            name = m.group(1) or m.group(2)
            if not name or name.startswith("_") or name in ("main", "init", "setup"): continue
            if len(re.findall(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", all_text)) <= 1:  # \b fails on names like $
                emit("NOTE", "dead-function", "structure", f"{r}:{t[:m.start()].count(chr(10)) + 1}", f"`{name}` is defined but never used", "")
    # copy-paste: 6-line windows of normalised, non-trivial lines
    W, seen, dups = 6, {}, []
    for r, t in texts.items():
        if pathlib.PurePath(r).suffix not in JS | {".py", ".css", ".scss"}: continue
        lines = [(i + 1, re.sub(r"\s+", " ", l.strip())) for i, l in enumerate(t.split("\n"))]
        lines = [(i, l) for i, l in lines if len(l) > 12 and not l.startswith(("//", "#", "/*", "*", "import ", "from "))]
        last = -99
        for k in range(len(lines) - W + 1):
            h = hashlib.sha1("\n".join(l for _, l in lines[k:k + W]).encode()).hexdigest()
            here = (r, lines[k][0])
            if h in seen and seen[h] != here and not (seen[h][0] == r and abs(seen[h][1] - here[1]) < W):
                if k - last >= W: dups.append((seen[h], here)); last = k
            else: seen.setdefault(h, here)
    for (fa, la), (fb, lb) in dups[:10]:
        emit("NOTE", "duplicate-code", "structure", f"{fb}:{lb}", f"{W}+ lines duplicated from {fa}:{la}: one fix will be missed", "")
    other = {}
    for r in texts:
        ext = pathlib.PurePath(r).suffix
        if ext not in JS and ext != ".py": other[ext] = other.get(ext, 0) + 1
    return {"modules": len(js) + len(py), "import_edges": edges, "cycles": len(out), "duplicates": len(dups), "not_analysed": other}
