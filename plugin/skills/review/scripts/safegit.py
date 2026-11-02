"""Running git in a project Curmudgeon didn't write (03 §5.57.6, found in batch 1's review of the full audit).

A project that arrives with its own .git (an archive, not a clone: a clone writes a fresh config and no hooks) can make
git run a program it chose, with no git command of the user's own:
- core.fsmonitor, on almost any command that reads the index;
- a filter driver's clean or process command, when git compares the work tree (diff, status);
- a diff driver's command or textconv, or diff.external, when git prints a patch;
- a hook in .git/hooks (post-index-change runs on status and diff) or under core.hooksPath;
- gpg.program, when log.showSignature makes git log check a signed commit;
- the same, one level down, in a submodule's own git folder, when diff or status recurse into it.

Every git command Curmudgeon runs goes through run() here. git's own command-line override (GIT_CONFIG_COUNT, which
beats the repository's config) switches off core.fsmonitor, hooks, signature checks and submodule recursion, and
empties every filter driver the repository's OWN config defines (local or worktree scope), marking it not required.
The owner's global and system filters (git-lfs, git-crypt) are left alone: they are the owner's, and emptying a
required one makes git fail (batch 1 review round 2). A command that can print a patch also gets --no-ext-diff,
--no-textconv and, for log and show, --no-show-signature. The repository's config is only read (git config
--get-regexp), never acted on. Git older than 2.31 ignores GIT_CONFIG_COUNT; the command-line flags still apply.
"""
import os, subprocess

_ENV = {}
FIXED = [("core.fsmonitor", "false"), ("core.hooksPath", os.devnull),  # a file, not a folder: no hook is ever found there
         ("log.showSignature", "false"), ("diff.ignoreSubmodules", "all"), ("submodule.recurse", "false"), ("status.submoduleSummary", "false")]

def _own_filters(cwd, env):
    """The filter drivers the repository's own config (local or worktree scope, includes too) defines: their names."""
    try:
        r = subprocess.run(["git", "config", "--null", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"],
                           cwd=cwd, capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError): return []
    parts = r.stdout.split("\0"); names = []
    for scope, kv in zip(parts[0::2], parts[1::2]):
        key = kv.split("\n", 1)[0]
        if scope in ("local", "worktree") and key.count(".") >= 2:
            name = key[len("filter."):key.rindex(".")]
            if name not in names: names.append(name)
    return names

def git_env(cwd, base=None):
    """The environment for a git command in cwd: base (or os.environ) plus the overrides above. Cached per folder,
    process and starting environment."""
    base = dict(os.environ if base is None else base)
    key = (os.path.realpath(str(cwd)), tuple(sorted((k, v) for k, v in base.items() if k.startswith("GIT_"))))
    if key not in _ENV:
        probe = dict(base, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.fsmonitor", GIT_CONFIG_VALUE_0="false")
        pairs = list(FIXED)
        for n in _own_filters(cwd, probe):  # an empty command means no filter; not required, so git doesn't fail without it
            pairs += [(f"filter.{n}.clean", ""), (f"filter.{n}.smudge", ""), (f"filter.{n}.process", ""), (f"filter.{n}.required", "false")]
        try: start = int(base.get("GIT_CONFIG_COUNT") or 0)
        except ValueError: start = 0
        add = {}
        for i, (k, v) in enumerate(pairs, start=start): add[f"GIT_CONFIG_KEY_{i}"] = k; add[f"GIT_CONFIG_VALUE_{i}"] = v
        add["GIT_CONFIG_COUNT"] = str(start + len(pairs))
        _ENV[key] = add
    return dict(base, **_ENV[key])

PATCH_CMDS = {"diff": ["--no-ext-diff", "--no-textconv"], "log": ["--no-ext-diff", "--no-textconv", "--no-show-signature"],
              "show": ["--no-ext-diff", "--no-textconv", "--no-show-signature"]}

def run(args, cwd, env=None, **kw):
    """subprocess.run(["git", *args], cwd=cwd, ...) with git_env, and the flags above for diff, log and show: the one
    way Curmudgeon runs git."""
    args = list(args)
    i = next((k for k, a in enumerate(args) if not a.startswith("-") and args[k - 1:k] != ["-c"]), None)  # the subcommand, after any -c key=value
    if i is not None and args[i] in PATCH_CMDS: args[i + 1:i + 1] = PATCH_CMDS[args[i]]
    return subprocess.run(["git", *args], cwd=cwd, env=git_env(cwd, env), **kw)
