"""Opt-in mutation testing for Curmudgeon scan: do the tests actually catch bugs? The idea comes from Stryker
(Apache-2.0); this is our own small version with no install. It makes one small change at a time to the named files
(flip a comparison, swap && and || or and and or, flip a boolean, swap + and -), runs the project's test command, and
reports each change the tests did not catch. The original file is restored after every mutant, even on errors or Ctrl+C.

Precision rules (ideas from mutmut, cargo-mutants and PIT, rebuilt here): only code is mutated, never strings,
docstrings or comments (Python's tokenizer, or a small JS/TS scanner); comparisons need spaces, so generics are never
touched; imports, logging, decorators and type-only lines are skipped; each file is first broken on purpose, and a file
whose break the tests don't notice is reported as never loaded instead of filling the report with survivors; tests run
with PYTHONDONTWRITEBYTECODE=1 so a stale .pyc can't fake a survivor; a mutant that runs past 5x the clean run's time
counts as caught; and when git shows changes in a file, only the changed lines are mutated.

The test command comes from --test-cmd, or from a line "Test command: ..." in .critic/rules.md only when the user
approved that file (--project-checks): a cloned repository can ship its own rules.md, and its command must never run
without consent."""
import atexit, pathlib, re, shutil, signal, subprocess, time
from critic_findings import log_run

# Comparisons need a space on both sides, so TypeScript generics (Array<string>) and arrows are never mutated.
OPS = [(r"===", "!=="), (r"!==", "==="), (r"(?<=\s)==(?=\s)", "!="), (r"(?<=\s)!=(?=\s)", "=="),
       (r"(?<=\s)<=(?=\s)", "<"), (r"(?<=\s)>=(?=\s)", ">"), (r"(?<=\s)<(?=\s)", "<="), (r"(?<=\s)>(?=\s)", ">="),
       (r"&&", "||"), (r"\|\|", "&&"), (r"\band\b", "or"), (r"\bor\b", "and"),
       (r"\btrue\b", "false"), (r"\bfalse\b", "true"), (r"\bTrue\b", "False"), (r"\bFalse\b", "True"),
       (r"(?<=[\w)\]])\s\+\s(?=[\w(])", " - "), (r"(?<=[\w)\]])\s-\s(?=[\w(])", " + ")]
# Lines whose change says nothing about behaviour: imports, logging and printing, decorators, type-only lines.
SKIP_LINE = re.compile(r"^\s*(import |from \S+ import |export \{|export type |type \w|interface |@|"
                       r"(console|log|logger|logging|LOG|self\.log|this\.log)\.\w+\(|print\(|debug\()")
JS = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte"}

def code_view(path, src):
    """The file's lines with every string and comment blanked out (same length, same positions), so a mutation can
    only ever land on code: never inside "a < b" or after a # or //. Python uses its own tokenizer; JS and TS use a
    small scanner for quotes, template strings and comments. Other languages return None: not mutated."""
    lines = src.split("\n")
    if path.suffix == ".py":
        import io, tokenize
        out = [list(l) for l in lines]
        blank = {tokenize.STRING, tokenize.COMMENT} | {getattr(tokenize, n) for n in ("FSTRING_MIDDLE",) if hasattr(tokenize, n)}
        try:
            for t in tokenize.generate_tokens(io.StringIO(src).readline):
                if t.type not in blank: continue
                (r0, c0), (r1, c1) = t.start, t.end
                for r in range(r0, r1 + 1):
                    row = out[r - 1]; a_ = c0 if r == r0 else 0; b_ = c1 if r == r1 else len(row)
                    for c in range(a_, min(b_, len(row))): row[c] = " "
        except (tokenize.TokenError, SyntaxError, IndentationError): return None
        return ["".join(r) for r in out]
    if path.suffix in JS:
        out, st, i, n, chars = [], None, 0, len(src), list(src)
        while i < n:
            c, nx = chars[i], (chars[i + 1] if i + 1 < n else "")
            if st is None:
                if c == "/" and nx == "/": st = "line"; chars[i] = chars[i + 1] = " "; i += 2; continue
                if c == "/" and nx == "*": st = "block"; chars[i] = chars[i + 1] = " "; i += 2; continue
                if c in "'\"`": st = c; chars[i] = " "; i += 1; continue
            elif st == "line":
                if c == "\n": st = None
                else: chars[i] = " "
            elif st == "block":
                if c == "*" and nx == "/": chars[i] = chars[i + 1] = " "; st = None; i += 2; continue
                if c != "\n": chars[i] = " "
            else:  # inside a quote
                if c == "\\": chars[i] = " "; (chars.__setitem__(i + 1, " ") if i + 1 < n and chars[i + 1] != "\n" else None); i += 2; continue
                if c == st: st = None; chars[i] = " "
                elif c != "\n": chars[i] = " "
                if st in ("'", '"') and c == "\n": st = None
            i += 1
        return "".join(chars).split("\n")
    return None

def changed_lines(root, rel):
    """Line numbers changed against git HEAD, or None when git can't say (no repo, an untracked file, no changes)."""
    try:
        r = subprocess.run(["git", "diff", "-U0", "HEAD", "--", rel], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired): return None
    got = set()
    for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", r.stdout, re.M):
        start, count = int(m.group(1)), int(m.group(2) or 1); got.update(range(start, start + count))
    return got or None

SANITY = {".py": 'raise SystemExit("curmudgeon mutation sanity check")\n', **{e: 'throw new Error("curmudgeon mutation sanity check");\n' for e in JS}}

def rules_test_cmd(root):
    p = root / ".critic" / "rules.md"
    if p.exists():
        m = re.search(r"(?im)^\s*test command\s*:\s*(.+)$", p.read_text(encoding="utf-8", errors="replace"))
        if m: return m.group(1).strip().strip("`")
    return None

def test_cmd(root, given, allow_rules=False):
    """--test-cmd always wins. The rules.md command is used only when the user approved rules.md (--project-checks)."""
    if given: return given
    return rules_test_cmd(root) if allow_rules else None

BACKUP_SUFFIX = ".critic-mutation-backup"
_pending = []
def _restore_pending(*_):
    for p, backup in list(_pending):
        if backup.exists(): shutil.copy2(backup, p); backup.unlink(missing_ok=True)
        _pending.remove((p, backup))

def recover(root, emit):
    """A run that was killed earlier leaves backups beside the files: put them back before doing anything else."""
    for b in root.rglob("*" + BACKUP_SUFFIX):
        orig = b.with_name(b.name[: -len(BACKUP_SUFFIX)])
        shutil.copy2(b, orig); b.unlink()
        emit("WARN", "mutation-recovered", "tests", str(orig.relative_to(root)), "an earlier mutation run was interrupted; the original file was restored from its backup", "")

def run(root, files, emit, state, given_cmd=None, cap=30, timeout=120, allow_rules=False):
    recover(root, emit)
    atexit.register(_restore_pending)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try: signal.signal(sig, lambda *a: (_restore_pending(), (_ for _ in ()).throw(SystemExit(130))))
        except (ValueError, OSError): pass
    cmd = test_cmd(root, given_cmd, allow_rules)
    if not cmd:
        if rules_test_cmd(root):
            state("mutation", "blocked", "rules.md names a test command, but it runs only with --project-checks, after the user has read and approved that file (a cloned repository can ship its own); or pass --test-cmd")
        else: state("mutation", "blocked", "no test command (pass --test-cmd, or add 'Test command: …' to .critic/rules.md and run with --project-checks)")
        return
    log_run(root, "command", f"mutation testing: {cmd} (once as a baseline, once per file as a sanity check, then once per mutant, up to {cap})")
    import os
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")  # a stale .pyc from an earlier mutant can never fake a survivor
    def go(limit):
        try: return subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=limit, env=env).returncode != 0
        except subprocess.TimeoutExpired: return True
    t0 = time.time()
    try: base = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired: state("mutation", "blocked", f"the test command took over {timeout} s before any mutation"); return
    if base.returncode != 0: state("mutation", "blocked", "the test command fails before any mutation; fix the tests first"); return
    limit = min(timeout, max(10.0, 5 * (time.time() - t0)))  # a mutant that hangs counts as caught, after 5x the clean run
    tried = killed = 0; survivors = []; notes = []
    for rel in files:
        p = (root / rel).resolve(); src = p.read_text(encoding="utf-8"); lines = src.split("\n")
        view = code_view(p, src)
        if view is None: notes.append(f"{rel}: not mutated (no parser for this file type, or it does not parse)"); continue
        only = changed_lines(root, rel)
        backup = p.with_name(p.name + BACKUP_SUFFIX); shutil.copy2(p, backup); _pending.append((p, backup))
        try:
            if p.suffix in SANITY:  # break the file on purpose: if the tests still pass, they never load it
                p.write_text(SANITY[p.suffix] + src, encoding="utf-8"); caught = go(limit); p.write_text(src, encoding="utf-8")
                if not caught:
                    emit("WARN", "mutation-not-exercised", "tests", rel, "the tests still pass when this file is broken on purpose: the test command never loads it, so its mutants were not run", "")
                    continue
            for i, line in enumerate(lines):
                if only is not None and i + 1 not in only: continue
                if SKIP_LINE.match(line) or len(line) > 300: continue
                for pat, rep in OPS:
                    if tried >= cap: break
                    m = re.search(pat, view[i])
                    if not m: continue
                    mutated = line[:m.start()] + rep + line[m.end():]
                    p.write_text("\n".join(lines[:i] + [mutated] + lines[i + 1:]), encoding="utf-8"); tried += 1
                    caught = go(limit)
                    p.write_text(src, encoding="utf-8")
                    if caught: killed += 1
                    else: survivors.append((rel, i + 1, line.strip()[:80], mutated.strip()[:80]))
            if only is not None: notes.append(f"{rel}: {len(only)} changed line(s) only")
        finally:
            shutil.copy2(backup, p); backup.unlink(missing_ok=True)
            if (p, backup) in _pending: _pending.remove((p, backup))
    for rel, ln, before, after in survivors[:20]:
        emit("WARN", "mutant-survived", "tests", f"{rel}:{ln}", f"the tests still pass when `{before}` becomes `{after}`: this behaviour is untested", "")
    score = round(100 * killed / tried) if tried else 0
    extra = ("; " + "; ".join(notes[:5])) if notes else ""
    state("mutation", "pass" if tried and not survivors else ("fail" if survivors else "blocked"), f"{tried} mutants, {killed} caught ({score}%), {time.time() - t0:.0f} s{extra}")
