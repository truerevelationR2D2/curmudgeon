"""Running git in a project Curmudgeon didn't write (a draft of the fix proposed after batch 1's review, 03 §5.57).

A project that arrives with its own .git (an archive, not a clone: a clone writes a fresh config) can put commands in
.git/config that git runs on its own: core.fsmonitor on almost any command that reads the index, a filter driver's
clean or process command when git compares the work tree, and a diff driver's command or textconv, or diff.external,
when git prints a patch. Every git command Curmudgeon runs goes through run() here: core.fsmonitor and the filters are
switched off with git's own command-line override (GIT_CONFIG_COUNT), which beats the repository's config, and a
command that can print a patch gets --no-ext-diff --no-textconv. The repository's config is only read (git config
--get-regexp), never acted on. Git older than 2.31 ignores the override.
"""
import os, subprocess

_ENV = {}

def _driver_keys(cwd, env):
    """Every filter driver command the repository's config (and its includes) defines, by full key."""
    try:
        r = subprocess.run(["git", "config", "--null", "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"],
                           cwd=cwd, capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError): return []
    return [rec.split("\n", 1)[0] for rec in r.stdout.split("\0") if rec.strip()]

def git_env(cwd, base=None):
    """The environment for a git command in cwd: base (or os.environ) plus overrides that switch off core.fsmonitor and
    every filter driver command the repository defines. Cached per folder and process. (diff.external and diff drivers
    can't be emptied this way, git would try to run "": run() turns them off with --no-ext-diff --no-textconv.)"""
    base = dict(os.environ if base is None else base)
    key = (os.path.realpath(str(cwd)), tuple(sorted((k, v) for k, v in base.items() if k.startswith("GIT_"))))
    if key not in _ENV:
        first = dict(base, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.fsmonitor", GIT_CONFIG_VALUE_0="false")
        pairs = [("core.fsmonitor", "false")] + [(k, "") for k in _driver_keys(cwd, first)]  # an empty filter command means no filter
        try: n = int(base.get("GIT_CONFIG_COUNT") or 0)
        except ValueError: n = 0
        add = {}
        for i, (k, v) in enumerate(pairs, start=n): add[f"GIT_CONFIG_KEY_{i}"] = k; add[f"GIT_CONFIG_VALUE_{i}"] = v
        add["GIT_CONFIG_COUNT"] = str(n + len(pairs))
        _ENV[key] = add
    return dict(base, **_ENV[key])

PATCH_CMDS = ("diff", "log", "show")  # the commands that can print a patch, and so run diff.external or a diff driver

def run(args, cwd, env=None, **kw):
    """subprocess.run(["git", *args], cwd=cwd, ...) with git_env, and, for a command that can print a patch, the flags
    that turn off external diff programs and textconv: the one way Curmudgeon runs git."""
    args = list(args)
    i = next((k for k, a in enumerate(args) if not a.startswith("-") and args[k - 1:k] != ["-c"]), None)  # the subcommand, after any -c key=value
    if i is not None and args[i] in PATCH_CMDS: args[i + 1:i + 1] = ["--no-ext-diff", "--no-textconv"]
    return subprocess.run(["git", *args], cwd=cwd, env=git_env(cwd, env), **kw)
