"""Curmudgeon runs only its own scripts (5.9.1). When the project under review holds a copy of Curmudgeon (its own
repository, a fork, a vendored copy), a command like `python3 plugin/skills/review/scripts/critic_run.py` runs that
copy's scripts, an older or edited version, against this plugin's hooks. The 16 Nov 2026 Qodo replay hit it: the copy's
brief script wrote no claim tokens, so no reviewer could claim its review under 5.9.0's hooks, and the review stalled.

This refuses a command that RUNS (python or py as the command word, -m, or the file itself as the command) a file that
is another copy of one of this plugin's scripts: same name, in a folder laid out like Curmudgeon's
(.../skills/review/scripts/). A project's own scope.py or browse.py anywhere else is never touched, and a command that
only reads or names a copy (cat, grep, git add) runs (5.9.1 review C1). It follows cd and pushd, $PWD and simple
variables, and the command inside bash -c or sh -c (C2, L1). A path it can't work out is left alone."""
import os, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
OURS = HERE.parent / "skills" / "review" / "scripts"
ASSIGN = re.compile(r"(?:^|[;&|\s])([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s;&|]+)")
PY = re.compile(r"(?i)(?:python(?:\d+(?:\.\d+)*)?|py|pypy3?)(?:\.exe)?")
LAYOUT = re.compile(r"(?i)(?:^|[\\/])skills[\\/]review[\\/]scripts$")
SEPS = (";", "&&", "||", "|", "&", "(", ")", "|&", "\n")

def _fold(p): return os.path.normcase(os.path.realpath(str(p))).casefold()

def _names():
    try: return {f.name for f in OURS.glob("*.py")}
    except OSError: return set()

def _foreign(path, names):
    """True when path is an existing copy of one of our scripts that isn't ours."""
    name = os.path.basename(path)
    if name not in names or not os.path.isfile(path): return False
    if not LAYOUT.search(os.path.dirname(os.path.realpath(path))) and not LAYOUT.search(os.path.dirname(os.path.normpath(path))): return False
    return _fold(path) != _fold(OURS / name)

def problem(cmd, cwd, _depth=0):
    """Why the command runs a foreign copy of one of our scripts, or None."""
    names = _names()
    if not names or ".py" not in cmd and " -m " not in cmd: return None
    import conduct
    env = {m.group(1): m.group(2).strip("\"'") for m in ASSIGN.finditer(cmd)}
    here = [str(cwd or os.getcwd())]
    def expand(w):
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
                      lambda m: here[0] if (m.group(1) or m.group(2)) == "PWD" else env.get(m.group(1) or m.group(2), os.environ.get(m.group(1) or m.group(2), m.group(0))), w)
    def at(w):
        w = os.path.expanduser(w)
        return os.path.normpath(w if os.path.isabs(w) else os.path.join(here[0], w))
    toks = [expand(t.lstrip("\x01")) for t in (conduct._tokens(cmd) or [])]
    seg = []
    def judge(seg):
        while seg and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[0]): seg = seg[1:]
        while seg and seg[0] in ("env", "exec", "time", "nohup", "sudo", "command"): seg = seg[1:]
        if not seg: return None
        word = seg[0]; base = os.path.basename(word.replace("\\", "/"))
        if base in ("cd", "pushd", "Set-Location", "sl") and len(seg) > 1 and "$" not in seg[1]: here[0] = at(seg[1]); return None
        if base in ("bash", "sh", "zsh") and "-c" in seg[1:]:
            i = seg.index("-c")
            if i + 1 < len(seg) and _depth < 3: return problem(seg[i + 1], here[0], _depth + 1)
            return None
        if base.endswith(".py") and "$" not in word:
            return at(word) if _foreign(at(word), names) else None
        if PY.fullmatch(base):
            args = seg[1:]
            j = 0
            while j < len(args) and args[j].startswith("-") and args[j] != "-m": j += 1  # -3, -u, -I, -B ...
            if j < len(args) and args[j] == "-m" and j + 1 < len(args):
                p = at(args[j + 1].replace(".", os.sep) + ".py")
                return p if _foreign(p, names) else None
            if j < len(args) and args[j].endswith(".py") and "$" not in args[j]:
                return at(args[j]) if _foreign(at(args[j]), names) else None
        return None
    for t in toks + [";"]:
        if t in SEPS:
            hit = judge(seg); seg = []
            if hit: return hit if _depth else f"{hit} is another copy of Curmudgeon's {os.path.basename(hit)} (one inside the project, not this plugin's); run {OURS / os.path.basename(hit)} instead"
            continue
        seg.append(t)
    return None
