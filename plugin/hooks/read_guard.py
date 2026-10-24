#!/usr/bin/env python3
"""PreToolUse: makes blindness a control, not only an instruction (5.0, ruling §5.29).

Each reviewer and verifier works in a private frozen copy of the payload, made in its own scratch folder at the
agent's start (scratch_dir.py and workspace.py). The copy has no .critic/ folder, so a search or a relative path there
can only find code. This guard holds the agent to it:

  Bash         must start with `cd <its workspace> && `. As a backstop, every path-like word (wildcards expanded,
               links followed) is resolved from the copy and judged like a Read, so ../../reviews, node_modules/.. or
               the project's own path are refused when they lead into .critic/ or above it; so are $OLDPWD, `cd -`,
               popd and $CLAUDE_PROJECT_DIR. With no workspace, Bash is refused and the agent reviews by reading.
  Read         checked by the real file (links followed, case ignored): nothing in the project's .critic/ except what
               the role needs (another agent's scratch folder and copy included).
  Grep, Glob   the same for the folder searched; a Grep rooted at or above .critic/ is refused, with the workspace
               named as the place to search (an agent with no workspace may Grep the project root with glob
               "!.critic"); a Glob is judged by every path it really matches.

What a role may read in the project's .critic/:
  reviewer  the rule files, the change map, its own scratch folder
  verifier  the same, plus its verify packets, the scan and the ledger's recorded decisions
  dedup     the rule files, dedup-candidates.json and groups.json

The threat is an honest agent anchoring on what it happens to see. A same-user process set on evasion can always build
a path no check sees; that needs an OS sandbox, and the README says so.

It also refuses a fork (an Agent call with subagent_type "fork") while a review run is active: a fork inherits the
whole conversation, so it can't be blind. A run counts as active from `start` until the teardown is written, for at
most 12 hours. The main conversation and every other agent are never limited. A crash in this hook allows the call
(a broken guard must not stop the user's work); the merge script's own checks still apply."""
import json, os, pathlib, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace

ALLOW = {"reviewer": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore"},
         "verifier": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "verify", "verify-variants", "scan", "ledger.md"},
         "dedup": {"rules", "rules.md", ".gitignore", "dedup-candidates.json", "groups.json"}}

def role_of(agent_type):
    m = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup)", agent_type or "")
    return m.group(1) if m else None

fold = workspace.fold

def judge(target, critic, role, me):
    """None when the path may be read; otherwise a short name of what is forbidden."""
    t, c = fold(target), fold(critic)
    if t == c: return ".critic (the whole folder)"
    if not t.startswith(c + os.sep): return None
    parts = t[len(c) + 1:].split(os.sep)
    top = parts[0]
    if top == "scratch":
        if len(parts) >= 2 and me and parts[1] == me.casefold(): return None
        return ".critic/scratch" + (f"/{parts[1]}" if len(parts) >= 2 else "")
    return None if top in ALLOW[role] else f".critic/{top}"

def above(base, inner):
    """True when a search rooted at base would reach inner (base is inner itself or a folder above it)."""
    return workspace.within(inner, base)

def resolve(v, root):
    p = pathlib.Path(os.path.expanduser(str(v)))
    if not p.is_absolute(): p = root / p
    try: return p.resolve()
    except (OSError, RuntimeError, ValueError): return p

def run_active(root):
    led = root / ".critic" / "ledger.json"
    try: started = json.loads(led.read_text()).get("started_at") if led.is_file() and not led.is_symlink() else None
    except Exception: started = None
    if not started or time.time() - started > 12 * 3600: return False
    last = root / ".critic" / "last-review.md"
    return not last.exists() or last.stat().st_mtime < started

def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0

def bash_problem(cmd, rec, root, critic, role, me):
    """The agent's commands run in its copy, so a recursive search or a relative path there only finds code. This is
    the backstop for the rest: every path-like word (and every word a wildcard expands to) is resolved from the copy,
    links followed, and judged like a Read; a word that leads to the project's .critic/ (beyond what the role may
    read) or to a folder above it is refused, and so are the shell's ways back ($OLDPWD, cd -, popd)."""
    import glob as _glob, shlex
    payload = rec["payload"]
    m = re.match(r"\s*cd\s+((?:'[^']*'|\"[^\"]*\"|\\.|[^\s;&|])+)\s*&&", cmd)  # however it is quoted (shlex.quote included)
    if not m: m = re.match(r"\s*git\s+-C\s+((?:'[^']*'|\"[^\"]*\"|\\.|[^\s;&|])+)(?=\s)", cmd)  # git -C <copy> ...: Claude Code asks before a cd followed by git
    try: target = shlex.split(m.group(1))[0] if m else None
    except (ValueError, IndexError): target = None
    if not target or fold(target.rstrip("/\\") or "/") != fold(payload): return f"a command that doesn't start in your workspace; start it with: cd {shlex.quote(payload)} && (or, for git, git -C {shlex.quote(payload)} ...)"
    rest = cmd[m.end():]
    if not cmd.lstrip().startswith("cd") and re.search(r"[;&|`\n]|\$\(", rest): return "a git -C command followed by another command (that one would run in the project, not your copy); use cd <workspace> && ... for chains"
    if re.search(r"(?i)\$\{?(?:OLDPWD|CLAUDE_PROJECT_DIR)\b|(?:^|[\s;&|(])(?:cd|pushd)\s+-(?:\s|$|[;&|)])|\bpopd\b|\bdirs\b", rest): return "a way back to the project folder ($OLDPWD, cd -, popd, $CLAUDE_PROJECT_DIR)"
    home = os.path.expanduser("~")
    flat = re.sub(r"\\(.)", r"\1", rest).replace("${HOME}", home).replace("$HOME", home)
    try:
        lx = shlex.shlex(flat, posix=True, punctuation_chars=True); lx.whitespace_split = True; words = list(lx)
    except ValueError: words = flat.replace("'", " ").replace('"', " ").split()
    base = pathlib.Path(payload)
    for w in words:
        for piece in re.split(r"[=:,]", w):  # --file=../x, PATH-like lists
            if not piece or piece.startswith("-") and "/" not in piece: continue
            if not ("/" in piece or piece in (".", "..", "~") or piece.startswith("~") or any(ch in piece for ch in "*?[")): continue
            q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else base / q
            hits = _glob.glob(str(q), recursive=True)[:2000] if any(ch in piece for ch in "*?[") else [str(q)]
            for h in hits:
                try: real = pathlib.Path(h).resolve()
                except (OSError, RuntimeError, ValueError): continue
                why = judge(real, critic, role, me)
                if why: return why
                if above(real, critic): return f"{piece}: a folder that holds the project's .critic/ (search your workspace instead)"
    return None

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    tool, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    root = workspace.project_root(data)
    if tool in ("Agent", "Task"):
        if str(ti.get("subagent_type") or "").lower() == "fork" and run_active(root):
            return deny("Curmudgeon: no forks during a review run. A fork inherits the whole conversation, so it can't review blind. Start the named agent (curmudgeon:curmudgeon-reviewer, -verifier, -dedup or -detector) instead.")
        return 0
    role = role_of(data.get("agent_type"))
    if not role: return 0
    me = workspace.clean_id(data.get("agent_id"))
    try: critic = (root / ".critic").resolve()
    except OSError: critic = root / ".critic"
    rec = workspace.info(root, me) if me else None
    where = f" Your workspace is {rec['payload']}." if rec else ""
    why = None
    if tool == "LSP":  # code intelligence: judged by every path or file URI it is given (its parameter names may vary)
        for k, v in ti.items():
            if isinstance(v, str) and re.search(r"(?i)path|file|uri", k):
                p = resolve(re.sub(r"^file://", "", v), root); why = judge(p, critic, role, me)
                if why: break
    elif tool in ("Read", "NotebookRead"):
        v = ti.get("file_path") or ti.get("notebook_path")
        if isinstance(v, str) and v:
            p = resolve(v, root); why = judge(p, critic, role, me)
    elif tool in ("Grep", "Glob"):
        here = pathlib.Path(data.get("cwd") or root)  # the tools search the session's current folder when no path is given
        start = resolve(ti.get("path") or str(here), here)
        why = judge(start, critic, role, me)
        pat = str(ti.get("pattern") or "")
        if not why and tool == "Glob" and (any(ch in pat for ch in "*?[") or "critic" in pat.casefold() or ".." in pat):  # expand it for real and judge what it matches
            import glob as _glob, itertools
            base_, pat_ = (pathlib.Path(pathlib.Path(pat).anchor), pat[len(pathlib.Path(pat).anchor):]) if os.path.isabs(pat) else (pathlib.Path(start), pat)
            try: found = (str(x) for x in base_.glob(pat_))  # pathlib matches dot-folders on every Python, as Glob does
            except (NotImplementedError, ValueError, OSError):
                hidden = {"include_hidden": True} if sys.version_info >= (3, 11) else {}
                found = iter(_glob.glob(os.path.join(str(start), pat), recursive=True, **hidden))
            for h in itertools.islice(found, 5000):
                hp = resolve(h, root); why = judge(hp, critic, role, me)
                if why: break
        if not why and tool == "Grep" and above(start, critic):  # a Glob is judged above by what it really matches
            g = str(ti.get("glob") or "").strip()
            if rec or fold(start) != fold(root) or not re.fullmatch(r"!(\*\*/)?\.critic(/\*{0,2})?", g, re.I):
                why = ".critic (a search from a folder above it); search your workspace" + (f" (path {rec['payload']})" if rec else ", or the project root with glob \"!.critic\", or a narrower folder")
    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str) and cmd:
            if not rec: why = "anything with Bash: no private workspace was made for you, so review by reading (Read, Grep, Glob)"
            else: why = bash_problem(cmd, rec, root, critic, role, me)
    if why: return deny(f"Curmudgeon blindness: a {role} may not read {why}.{where} Review only what your brief gives you.")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
