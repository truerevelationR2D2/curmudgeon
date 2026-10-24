#!/usr/bin/env python3
"""Grow the eval kit with planted defects that are proved real (SC-18). Our own planter, after the idea in SWE-smith
(MIT; method only): take a clean fixture, apply one small code mutation at a time (the operators the mutation tester
uses, on code only, never inside strings or comments), and keep a mutant only when a behaviour test that passed on the
clean fixture now fails. A plant nobody can show is broken is not a defect, so it never enters the kit.

usage:
  planter.py FIXTURE BEHAVIOUR.py --out NAME [--max N] [--files a.js,b.js] [--dest DIR]

FIXTURE is a clean fixture folder under eval/ (for example fixture-clean), BEHAVIOUR.py a behaviour module with
run(folder) -> {check: bool} (behaviour1.py, behaviour2.py). Each kept mutant becomes eval/NAME-<n>/ (the fixture with
that one change) and an entry in eval/answer_key_NAME.json: the file, the line, the checks it breaks, and patterns that
credit a review naming that file and line or quoting the changed code. Synthetic plants are reported apart from real
ones (they flatter reviewers: README, "Benchmarks"). Needs Playwright when the behaviour test does; never installs it."""
import importlib.util, json, pathlib, re, shutil, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin" / "skills" / "review" / "scripts"))
import scan_mutation as M

def behaviour(path):
    spec = importlib.util.spec_from_file_location("behaviour", path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.run

def mutants(folder, files):
    for rel in files:
        p = folder / rel; src = p.read_text(encoding="utf-8"); view = M.code_view(pathlib.PurePath(rel), src)
        if view is None: continue
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if M.SKIP_LINE.match(line) or i >= len(view): continue
            for pat, rep in M.OPS:
                for m in re.finditer(pat, view[i]):
                    new = line[:m.start()] + rep + line[m.end():]
                    if new != line: yield rel, i + 1, line, new

def main(a):
    if len(a) < 2 or a[0] in ("-h", "--help"): print(__doc__); return 0 if a[:1] in (["-h"], ["--help"]) else 2
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d
    src = (HERE / a[0]).resolve(); run_b = behaviour(HERE / a[1]); name = opt("--out"); cap = int(opt("--max", "10"))
    dest = pathlib.Path(opt("--dest", str(HERE))).resolve()
    if not name or not re.fullmatch(r"[\w-]+", name): sys.exit("planter: --out NAME (letters, digits, - and _)")
    files = opt("--files").split(",") if opt("--files") else [str(p.relative_to(src)) for p in src.rglob("*") if p.suffix in M.JS | {".py"} and p.is_file()]
    base = run_b(src)
    passing = {k for k, v in base.items() if v}
    if not passing: sys.exit("planter: no behaviour check passes on the clean fixture, so nothing can prove a plant")
    key, kept, tried = {}, 0, 0
    for rel, ln, old, new in mutants(src, files):
        if kept >= cap: break
        tried += 1
        with tempfile.TemporaryDirectory(prefix="plant-") as t:
            w = pathlib.Path(t) / "f"; shutil.copytree(src, w)
            lines = (w / rel).read_text(encoding="utf-8").split("\n"); lines[ln - 1] = new; (w / rel).write_text("\n".join(lines), encoding="utf-8")
            try: res = run_b(w)
            except Exception: continue
        broken = sorted(k for k in passing if not res.get(k))
        if not broken: continue
        kept += 1; out = dest / f"{name}-{kept}"
        if out.exists(): shutil.rmtree(out)
        shutil.copytree(src, out, ignore=shutil.ignore_patterns(".critic"))
        lines = (out / rel).read_text(encoding="utf-8").split("\n"); lines[ln - 1] = new; (out / rel).write_text("\n".join(lines), encoding="utf-8")
        snippet = re.escape(new.strip()[:60])
        key[f"S{kept} {rel}:{ln} changed to `{new.strip()[:60]}`; breaks: {', '.join(broken)}"] = {
            "file": pathlib.PurePath(rel).name, "at": [[rel, ln, ln]], "any": [rf"{re.escape(pathlib.PurePath(rel).name)}:({ln - 1}|{ln}|{ln + 1})\b", snippet], "synthetic": True, "fixture": out.name, "breaks": broken}
        print(f"kept {out.name}: {rel}:{ln} breaks {', '.join(broken)}")
    (dest / f"answer_key_{name}.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"planter: {kept} plant(s) kept of {tried} tried; answer key {dest / f'answer_key_{name}.json'}")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
