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
import atexit, hashlib, json, os, pathlib, re, shutil, signal, subprocess, time
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
    """The file's lines with every string and comment blanked out with underscores (same length, same positions; not
    spaces, which the comparison rules read as operator spacing), so a mutation can
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
                    for c in range(a_, min(b_, len(row))): row[c] = "_"
        except (tokenize.TokenError, SyntaxError, IndentationError): return None
        return ["".join(r) for r in out]
    if path.suffix in JS:
        out, st, i, n, chars = [], None, 0, len(src), list(src)
        if path.suffix in (".vue", ".svelte"):  # only <script> blocks are code; template text and CSS are never mutated
            keep = [False] * n
            for m in re.finditer(r"(<script\b[^>]*>)(.*?)(</script\s*>)", src, re.S | re.I):
                for k in range(m.start(2), m.end(2)): keep[k] = True
            for k in range(n):
                if not keep[k] and chars[k] != "\n": chars[k] = "_"
        while i < n:
            c, nx = chars[i], (chars[i + 1] if i + 1 < n else "")
            if st is None:
                if c == "/" and nx == "/": st = "line"; chars[i] = chars[i + 1] = "_"; i += 2; continue
                if c == "/" and nx == "*": st = "block"; chars[i] = chars[i + 1] = "_"; i += 2; continue
                if c in "'\"`": st = c; chars[i] = "_"; i += 1; continue
            elif st == "line":
                if c == "\n": st = None
                else: chars[i] = "_"
            elif st == "block":
                if c == "*" and nx == "/": chars[i] = chars[i + 1] = "_"; st = None; i += 2; continue
                if c != "\n": chars[i] = "_"
            else:  # inside a quote
                if c == "\\": chars[i] = "_"; (chars.__setitem__(i + 1, "_") if i + 1 < n and chars[i + 1] != "\n" else None); i += 2; continue
                if c == st: st = None; chars[i] = "_"
                elif c != "\n": chars[i] = "_"
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
def sanity_break(suffix, src):
    """The file with a line that makes loading it fail, or None when there is no safe place for one. A Vue or Svelte
    component gets it inside its first <script> block (text outside a script block is markup, not code)."""
    if suffix in (".vue", ".svelte"):
        m = re.search(r"<script\b[^>]*>", src)
        return src[:m.end()] + "\n" + SANITY[suffix] + src[m.end():] if m else None
    return SANITY[suffix] + src if suffix in SANITY else None

def rules_test_cmd(root):
    from critic_findings import rules_test_command
    p = root / ".critic" / "rules.md"
    return rules_test_command(p.read_text(encoding="utf-8", errors="replace")) if p.exists() else None

def test_cmd(root, given, allow_rules=False):
    """--test-cmd always wins. The rules.md command is used only when the user approved rules.md (--project-checks)."""
    if given: return given
    from critic_findings import approved_state
    return rules_test_cmd(root) if allow_rules and approved_state(root, "rules.md") else None  # only from the rules.md the owner approved (03 §5.56 item 9)

BACKUP_SUFFIX = ".critic-mutation-backup"
_pending = []
def _restore_pending(*_):
    for p, backup in list(_pending):
        try:
            if backup.exists(): shutil.copy2(backup, p); backup.unlink(missing_ok=True)
        except OSError: pass  # restored already (a signal arrived during the finally); never raise from here
        if (p, backup) in _pending: _pending.remove((p, backup))

def _record_path(root):
    """The list of backups this tool made, kept outside the project in Curmudgeon's own data folder
    (CLAUDE_PLUGIN_DATA, else ~/.curmudgeon; CURMUDGEON_STATE_DIR overrides), one file per project path. A repository
    can't ship it, whatever it commits (round 3, F-c3c59c4f)."""
    base = pathlib.Path(os.environ.get("CURMUDGEON_STATE_DIR") or os.environ.get("CLAUDE_PLUGIN_DATA") or pathlib.Path.home() / ".curmudgeon")
    key = hashlib.sha256(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:16]
    return base / "mutation" / f"{key}.json"

def _read_record(root):
    f = _record_path(root)
    if not f.is_file() or f.is_symlink(): return []
    try: x = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError): return []
    if not isinstance(x, dict) or x.get("root") != str(pathlib.Path(root).resolve()): return []
    return [e for e in x.get("entries", []) if isinstance(e, dict) and isinstance(e.get("file"), str) and isinstance(e.get("sha256"), str)]

def _write_record(root, entries):
    f = _record_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    try: os.chmod(f.parent, 0o700)
    except OSError: pass
    if not entries: f.unlink(missing_ok=True); return
    tmp = f.with_name(f.name + ".tmp"); tmp.write_text(json.dumps({"root": str(pathlib.Path(root).resolve()), "entries": entries}), encoding="utf-8"); os.replace(tmp, f)

def pending(root):
    """Files a killed run left mutated (read only: nothing is restored or changed)."""
    return [e["file"] for e in _read_record(root)]

def _sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def _inside(root, path):
    try: path.resolve().relative_to(root.resolve()); return True
    except (ValueError, OSError): return False

def recover(root, emit):
    """A run that was killed earlier leaves backups beside the files. Only backups this tool listed in its private
    record are put back, and only when the backup is a plain file inside the project whose content still has the
    hash recorded when it was made. A backup file that is not in the record (one a cloned repository ships, say) is
    never restored: it is reported and left alone."""
    entries = _read_record(root)
    for e in entries:
        orig = root / e["file"]; b = orig.with_name(orig.name + BACKUP_SUFFIX); rel = e["file"]
        why = None
        if pathlib.PurePath(rel).is_absolute() or ".." in pathlib.PurePath(rel).parts: why = "the recorded path leaves the project"
        elif orig.is_symlink() or b.is_symlink() or any(q.is_symlink() for q in orig.parents if _inside(root, q) and q != root): why = "the file, its backup or a folder on the way is a link"
        elif not _inside(root, orig) or not _inside(root, b): why = "the file or its backup is outside the project"
        elif not b.is_file(): why = None if not b.exists() else "the backup is not a plain file"
        elif _sha(b) != e["sha256"]: why = "the backup's content changed after it was made"
        if why: emit("WARN", "mutation-backup-ignored", "tests", rel, f"a backup from an interrupted mutation run was not restored: {why}. Check the file by hand", ""); continue
        if b.is_file():
            shutil.copy2(b, orig); b.unlink()
            emit("WARN", "mutation-recovered", "tests", rel, "an earlier mutation run was interrupted; the original file was restored from its backup", "")
    if entries: _write_record(root, [])
    for b in root.rglob("*" + BACKUP_SUFFIX):
        if ".git" in b.relative_to(root).parts: continue
        emit("NOTE", "mutation-backup-unlisted", "tests", str(b.relative_to(root)), "a file named like a mutation backup that this tool did not record; it was not used", "")

def run(root, files, emit, state, given_cmd=None, cap=30, timeout=120, allow_rules=False):
    files = list(files)
    atexit.register(_restore_pending)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try: signal.signal(sig, lambda *a: (_restore_pending(), (_ for _ in ()).throw(SystemExit(130))))
        except (ValueError, OSError): pass
    cmd = test_cmd(root, given_cmd, allow_rules)
    left = pending(root)
    if left and not cmd:  # read only: a killed run left these mutated, and restoring them waits for a run the user allows
        emit("WARN", "mutation-pending", "tests", ", ".join(left[:5]), f"an earlier mutation run was killed and left {len(left)} file(s) changed; their originals are beside them as *{BACKUP_SUFFIX}. They are put back at the start of the next run that has a test command", "")
    if not cmd:
        if rules_test_cmd(root):
            state("mutation", "blocked", "rules.md names a test command, but it runs only with --project-checks, after the user has read and approved that file (a cloned repository can ship its own); or pass --test-cmd")
        else: state("mutation", "blocked", "no test command (pass --test-cmd, or add 'Test command: …' to .critic/rules.md and run with --project-checks)")
        return
    recover(root, emit)  # after the consent gate: nothing in the project is rewritten until the user has allowed a run
    log_run(root, "command", f"mutation testing: {cmd} (once as a baseline, once per file as a sanity check, then once per mutant, up to {cap})")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")  # a stale .pyc from an earlier mutant can never fake a survivor
    def go(limit):
        """True when the tests fail (the mutant is caught). The command runs in its own process group, so a mutant
        that hangs is stopped with everything it started, not only the shell."""
        pr = subprocess.Popen(cmd, shell=True, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        try: return pr.wait(timeout=limit) != 0
        except subprocess.TimeoutExpired:
            try: os.killpg(pr.pid, signal.SIGKILL)
            except OSError: pass
            pr.wait(); return True
    t0 = time.time()
    try: base = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired: state("mutation", "blocked", f"the test command took over {timeout} s before any mutation"); return
    if base.returncode != 0: state("mutation", "blocked", "the test command fails before any mutation; fix the tests first"); return
    limit = min(timeout, max(10.0, 5 * (time.time() - t0)))  # a mutant that hangs counts as caught, after 5x the clean run
    tried = killed = 0; survivors = []; notes = []; not_mutated = []
    for n_file, rel in enumerate(files):
        if tried >= cap: not_mutated = list(files[n_file:]); break  # the cap is spent: say which files were left, never run them
        p = (root / rel).resolve(); src = p.read_text(encoding="utf-8"); lines = src.split("\n")
        view = code_view(p, src)
        if view is None: notes.append(f"{rel}: not mutated (no parser for this file type, or it does not parse)"); continue
        only = changed_lines(root, rel)
        backup = p.with_name(p.name + BACKUP_SUFFIX)
        if backup.exists() or backup.is_symlink(): notes.append(f"{rel}: not mutated (a file named {backup.name} is already there)"); continue
        if not _inside(root, p): notes.append(f"{rel}: not mutated (it leads outside the project)"); continue
        key = p.relative_to(root.resolve()).as_posix()
        shutil.copy2(p, backup); _pending.append((p, backup)); _write_record(root, _read_record(root) + [{"file": key, "sha256": _sha(backup)}])
        try:
            broken = sanity_break(p.suffix, src)
            if broken is not None:  # break the file on purpose: if the tests still pass, they never load it
                p.write_text(broken, encoding="utf-8"); caught = go(limit); p.write_text(src, encoding="utf-8")
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
            if backup.exists(): shutil.copy2(backup, p); backup.unlink(missing_ok=True)  # a signal handler may have restored it already
            if (p, backup) in _pending: _pending.remove((p, backup))
            _write_record(root, [e for e in _read_record(root) if e["file"] != key])
    for rel, ln, before, after in survivors[:20]:
        emit("WARN", "mutant-survived", "tests", f"{rel}:{ln}", f"the tests still pass when `{before}` becomes `{after}`: this behaviour is untested", "")
    score = round(100 * killed / tried) if tried else 0
    if not_mutated:
        emit("NOTE", "mutation-cap-reached", "tests", not_mutated[0], f"the mutant cap ({cap}) was reached: {len(not_mutated)} file(s) not mutated ({', '.join(map(str, not_mutated[:5]))}); raise the cap to test them", "")
        notes.insert(0, f"cap of {cap} reached, {len(not_mutated)} file(s) not mutated")
    extra = ("; " + "; ".join(notes[:5])) if notes else ""
    if not tried and not survivors:  # the check ran; there was nothing to mutate on the lines in scope
        state("mutation", "n/a", f"nothing to mutate in the lines in scope{extra}"); return
    state("mutation", "pass" if not survivors else "fail", f"{tried} mutants, {killed} caught ({score}%), {time.time() - t0:.0f} s{extra}")
