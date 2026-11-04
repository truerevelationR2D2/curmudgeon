"""Running git in a project Curmudgeon didn't write (03 §5.57.6, found in batch 1's review of the full audit).

A project that arrives with its own .git (an archive, not a clone: a clone writes a fresh config and no hooks) can make
git run a program it chose, with no git command of the user's own:
- core.fsmonitor, on almost any command that reads the index;
- a filter driver's clean or process command, when git compares the work tree (diff, status);
- a diff driver's command or textconv, or diff.external, when git prints a patch;
- a hook in .git/hooks (post-index-change runs on status and diff) or under core.hooksPath;
- gpg.program, when log.showSignature makes git log check a signed commit;
- the same, one level down, in a submodule's own git folder, when diff or status recurse into it.

Every git command Curmudgeon runs goes through run() here. git's own command-line override (`-c key=value` before
the subcommand, which beats the repository's config on every git version and reaches the git processes it starts in
submodules) switches off core.fsmonitor, hooks, signature checks and submodule recursion, and empties every filter
driver the repository's OWN config defines (local or worktree scope; on git before 2.26, which can't show scopes, the
--local and --worktree lists), marking it not required. A filter whose name contains '=' can't be named with -c (git
splits at the first '='): it goes in GIT_CONFIG_COUNT on git 2.31 and later, and older git is not run at all. diff,
log, show and status also get --ignore-submodules=all, which beats a submodule's own ignore setting in the project's
.gitmodules (review round 3). The owner's global and system filters (git-lfs, git-crypt) are left alone: they are the
owner's, and emptying a required one makes git fail (batch 1 review round 2). A command that can print a patch also
gets --no-ext-diff, --no-textconv and, for log and show, --no-show-signature. The repository's config is only read
(git config --get-regexp), never acted on.
"""
import os, re, subprocess

_ENV = {}
_VER = {}
FIXED = [("core.fsmonitor", "false"), ("core.hooksPath", os.devnull),  # a file, not a folder: no hook is ever found there
         ("log.showSignature", "false"), ("diff.ignoreSubmodules", "all"), ("submodule.recurse", "false"), ("status.submoduleSummary", "false"),
         ("diff.submodule", "short")]  # never print a submodule's own diff (round 3)

def _config_list(cwd, env, extra):
    """`git config --null <extra> --get-regexp` for filter commands: (returncode, [(scope or None, key)])."""
    r = subprocess.run(["git", "-c", "core.fsmonitor=false", "config", "--null", *extra, "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"],
                       cwd=cwd, capture_output=True, text=True, timeout=10, env=env, encoding="utf-8", errors="replace")
    parts = r.stdout.split("\0")
    if "--show-scope" in extra: return r.returncode, [(sc, kv.split("\n", 1)[0]) for sc, kv in zip(parts[0::2], parts[1::2])]
    return r.returncode, [(None, kv.split("\n", 1)[0]) for kv in parts if kv]

def _own_filters(cwd, env):
    """The filter drivers the repository's own config (local or worktree scope, includes too) defines: their names.
    Git before 2.26 has no --show-scope: then --local and --worktree are listed instead (round 3)."""
    keys = []
    try:
        rc, rows = _config_list(cwd, env, ["--show-scope"])
        if rc in (0, 1): keys = [k for sc, k in rows if sc in ("local", "worktree")]
        else:
            for scope in ("--local", "--worktree"):  # --worktree fails when worktreeConfig is off: nothing to add then
                rc, rows = _config_list(cwd, env, [scope, "--includes"])
                if rc in (0, 1): keys += [k for _, k in rows]
    except (OSError, subprocess.SubprocessError): return []
    names = []
    for key in keys:
        if key.count(".") >= 2:
            name = key[len("filter."):key.rindex(".")]
            if name not in names: names.append(name)
    return names

def _git_version(env):
    k = (env or os.environ).get("PATH", "")
    if k not in _VER:
        try: m = re.search(r"(\d+)\.(\d+)", subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10, env=env, encoding="utf-8", errors="replace").stdout)
        except (OSError, subprocess.SubprocessError): m = None
        _VER[k] = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return _VER[k]

def overrides(cwd, env=None):
    """(the `-c key=value` arguments, the GIT_CONFIG_* variables, a refusal or None) for a git command in cwd. A key with
    '=' in it (a filter named "x=y") can't be passed with -c, which splits at the first '=': it goes in GIT_CONFIG_COUNT
    (git 2.31 and later), and on older git the command is refused (round 3). Cached per folder, process and starting
    environment."""
    base = os.environ if env is None else env
    key = (os.path.realpath(str(cwd)), tuple(sorted((k, v) for k, v in base.items() if k.startswith("GIT_") or k == "PATH")))
    if key not in _ENV:
        pairs = list(FIXED)
        for n in _own_filters(cwd, None if env is None else dict(env)):  # an empty command means no filter; not required, so git doesn't fail without it
            pairs += [(f"filter.{n}.clean", ""), (f"filter.{n}.smudge", ""), (f"filter.{n}.process", ""), (f"filter.{n}.required", "false")]
        args = [a for k, v in pairs if "=" not in k for a in ("-c", f"{k}={v}")]
        odd = [(k, v) for k, v in pairs if "=" in k]; add = {}; refuse = None
        if odd:
            if _git_version(None if env is None else dict(env)) < (2, 31):
                refuse = "git refused: this repository defines a filter whose name contains '=', which git before 2.31 can't switch off; Curmudgeon won't run git here"
            else:
                try: start = int(base.get("GIT_CONFIG_COUNT") or 0)
                except ValueError: start = 0
                for i, (k, v) in enumerate(odd, start=start): add[f"GIT_CONFIG_KEY_{i}"] = k; add[f"GIT_CONFIG_VALUE_{i}"] = v
                add["GIT_CONFIG_COUNT"] = str(start + len(odd))
        _ENV[key] = (args, add, refuse)
    a, add, refuse = _ENV[key]
    return list(a), dict(add), refuse

SUB = "--ignore-submodules=all"  # the command-line form beats a submodule's own ignore setting in .gitmodules (round 3)
PATCH_CMDS = {"diff": ["--no-ext-diff", "--no-textconv", SUB], "log": ["--no-ext-diff", "--no-textconv", "--no-show-signature", SUB],
              "show": ["--no-ext-diff", "--no-textconv", "--no-show-signature", SUB], "status": [SUB]}

def run(args, cwd, env=None, **kw):
    """subprocess.run(["git", *args], cwd=cwd, ...) with the overrides above, and the flags above for diff, log, show and
    status: the one way Curmudgeon runs git."""
    args = list(args)
    i = next((k for k, a in enumerate(args) if not a.startswith("-") and args[k - 1:k] != ["-c"]), None)  # the subcommand, after any -c key=value
    if i is not None and args[i] in PATCH_CMDS: args[i + 1:i + 1] = PATCH_CMDS[args[i]]
    c, add, refuse = overrides(cwd, env)
    if refuse:
        text = kw.get("text") or kw.get("universal_newlines") or kw.get("encoding")
        if kw.get("check"): raise subprocess.CalledProcessError(128, ["git", *args], "" if text else b"", refuse if text else refuse.encode())
        return subprocess.CompletedProcess(["git", *args], 128, "" if text else b"", refuse if text else refuse.encode())
    return subprocess.run(["git", *c, *args], cwd=cwd, env=dict(os.environ if env is None else env, **add) if add else env, **kw)
