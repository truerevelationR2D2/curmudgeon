"""Curmudgeon runs only its own scripts (5.9.1). When the project under review holds a copy of Curmudgeon (its own
repository, a fork, a vendored copy), a command like `python3 plugin/skills/review/scripts/critic_run.py` runs that
copy's scripts, an older or edited version, against this plugin's hooks. The 16 Nov 2026 Qodo replay hit it: the copy's
brief script wrote no claim tokens, so no reviewer could claim its review under 5.9.0's hooks, and the review stalled.
This refuses any command that runs a script named like one of this plugin's scripts from anywhere else, and names the
plugin's own path. It knows that path from where this file lives."""
import os, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
OURS = HERE.parent / "skills" / "review" / "scripts"
ASSIGN = re.compile(r"(?:^|[;&|\s])([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s;&|]+)")

def _fold(p): return os.path.normcase(os.path.realpath(str(p))).casefold()

def problem(cmd, cwd):
    """Why the command runs a foreign copy of one of our scripts, or None. Paths it can't work out are left alone."""
    try: names = {f.name for f in OURS.glob("*.py")}
    except OSError: return None
    if not names or ".py" not in cmd: return None
    env = {}
    for m in ASSIGN.finditer(cmd):  # S=plugin/skills/review/scripts; python3 $S/critic_run.py
        env[m.group(1)] = m.group(2).strip("\"'")
    def expand(w):
        w = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", lambda m: env.get(m.group(1) or m.group(2), os.environ.get(m.group(1) or m.group(2), m.group(0))), w)
        return w
    import conduct
    base = str(cwd or os.getcwd())
    for w in conduct._tokens(cmd) or []:
        w = expand(w.lstrip("\x01"))
        if not w.endswith(".py") or "$" in w: continue
        name = os.path.basename(w.replace("\\", "/"))
        if name not in names: continue
        full = w if os.path.isabs(w) else os.path.join(base, w)
        if os.path.exists(full) and _fold(full) != _fold(OURS / name):
            return f"{w} is not this plugin's own copy of {name} (the project holds another copy of Curmudgeon); run {OURS / name} instead"
    return None
