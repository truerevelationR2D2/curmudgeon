"""Opt-in mutation testing for Curmudgeon scan: do the tests actually catch bugs? The idea comes from Stryker
(Apache-2.0); this is our own small version with no install. It makes one small change at a time to the named files
(flip a comparison, swap && and ||, flip a boolean, swap + and -), runs the project's test command, and reports each
change the tests did not catch. The original file is restored after every mutant, even on errors or Ctrl+C.

The test command comes from --test-cmd or a line "Test command: ..." in .critic/rules.md."""
import atexit, pathlib, re, shutil, signal, subprocess, time
from critic_findings import log_run

OPS = [(r"===", "!=="), (r"!==", "==="), (r"(?<![<>=!])<=(?!=)", "<"), (r"(?<![<>=!])>=(?!=)", ">"), (r"(?<![<>=!-])<(?![<=])", "<="),
       (r"(?<![<>=!-])>(?![>=])", ">="), (r"&&", "||"), (r"\|\|", "&&"), (r"\btrue\b", "false"), (r"\bfalse\b", "true"),
       (r"(?<=[\w)\]])\s\+\s(?=[\w(])", " - "), (r"(?<=[\w)\]])\s-\s(?=[\w(])", " + ")]
SKIP_LINE = re.compile(r"^\s*(//|#|\*|/\*|import |from |export \{|console\.|<)")

def test_cmd(root, given):
    if given: return given
    p = root / ".critic" / "rules.md"
    if p.exists():
        m = re.search(r"(?im)^\s*test command\s*:\s*(.+)$", p.read_text(encoding="utf-8", errors="replace"))
        if m: return m.group(1).strip().strip("`")
    return None

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

def run(root, files, emit, state, given_cmd=None, cap=30, timeout=120):
    recover(root, emit)
    atexit.register(_restore_pending)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try: signal.signal(sig, lambda *a: (_restore_pending(), (_ for _ in ()).throw(SystemExit(130))))
        except (ValueError, OSError): pass
    cmd = test_cmd(root, given_cmd)
    if not cmd: state("mutation", "blocked", "no test command (add 'Test command: …' to .critic/rules.md or pass --test-cmd)"); return
    log_run(root, "command", f"mutation testing: {cmd} (once as a baseline, then once per mutant, up to {cap})")
    base = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=timeout)
    if base.returncode != 0: state("mutation", "blocked", "the test command fails before any mutation; fix the tests first"); return
    tried = killed = 0; survivors = []; t0 = time.time()
    for rel in files:
        p = (root / rel).resolve(); src = p.read_text(encoding="utf-8"); lines = src.split("\n")
        backup = p.with_name(p.name + BACKUP_SUFFIX); shutil.copy2(p, backup); _pending.append((p, backup))
        try:
            for i, line in enumerate(lines):
                if SKIP_LINE.match(line) or len(line) > 300: continue
                for pat, rep in OPS:
                    if tried >= cap: break
                    m = re.search(pat, line)
                    if not m: continue
                    mutated = line[:m.start()] + rep + line[m.end():]
                    p.write_text("\n".join(lines[:i] + [mutated] + lines[i + 1:]), encoding="utf-8"); tried += 1
                    try: r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, timeout=timeout); caught = r.returncode != 0
                    except subprocess.TimeoutExpired: caught = True
                    p.write_text(src, encoding="utf-8")
                    if caught: killed += 1
                    else: survivors.append((rel, i + 1, line.strip()[:80], mutated.strip()[:80]))
        finally:
            shutil.copy2(backup, p); backup.unlink(missing_ok=True)
            if (p, backup) in _pending: _pending.remove((p, backup))
    for rel, ln, before, after in survivors[:20]:
        emit("WARN", "mutant-survived", "tests", f"{rel}:{ln}", f"the tests still pass when `{before}` becomes `{after}`: this behaviour is untested", "")
    score = round(100 * killed / tried) if tried else 0
    state("mutation", "pass" if tried and not survivors else ("fail" if survivors else "blocked"), f"{tried} mutants, {killed} caught ({score}%), {time.time() - t0:.0f} s")
