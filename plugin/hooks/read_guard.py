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
  verifier  the same, plus its own verify packets (by path, at most one batch) and the ledger's recorded decisions; never the scan
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

ALLOW = {"reviewer": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "briefs"},  # a brief holds no findings, so reading one by path (a lead that passed the path, not the text) breaks no blindness
         "verifier": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "verify", "verify-variants", "decisions.md"},  # never ledger.md: it holds dismissal notes and memories; never the scan (03 §5.56 item 13)
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
    if role == "verifier" and top in ("verify", "verify-variants"):  # 03 §5.56 item 13: its own packets, by path, and no more than one batch
        if len(parts) != 2 or not parts[1].endswith(".json"): return f".critic/{top} (the folder): read only your packets, by the paths you were given"
        if me and not packet_ok(critic, me, f"{top}/{parts[1]}"): return f".critic/{top}/{parts[1]}: more packets than one batch ({PACKETS}); judge only the ones you were given"
        return None
    return None if top in ALLOW[role] else f".critic/{top}"

PACKETS = 5  # critic_run.py's VERIFY_BATCH: a verifier is given at most this many packets

def packet_ok(critic, me, rel):
    """Record the packets this verifier opens, in its own scratch folder; the sixth distinct one is refused."""
    f = pathlib.Path(critic) / "scratch" / me / "packets-opened.json"
    try: seen = json.loads(f.read_text()) if f.is_file() and not f.is_symlink() else []
    except (OSError, ValueError): seen = []
    if rel in seen: return True
    if len(seen) >= PACKETS: return False
    try:
        if not f.is_symlink(): f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(seen + [rel]))
    except OSError: pass
    return True

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
    home = os.path.expanduser("~")
    unquoted = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " ", rest)  # what the shell itself would expand
    if re.search(r"(?i)\$\{?(?:OLDPWD|CLAUDE_PROJECT_DIR)\b|(?:^|[\s;&|(])(?:cd|pushd)\s+-(?:\s|$|[;&|)])", unquoted): return "a way back to the project folder ($OLDPWD, cd -, $CLAUDE_PROJECT_DIR)"
    if re.search(r"\$\{?IFS\b|(?:^|[\s=:])~-|\{[^}\s]*\b(?:cd|pushd|chdir)\b[^}\s]*,", unquoted): return "a command spelled through $IFS, ~- or brace expansion"
    flat = re.sub(r"\\(.)", r"\1", rest).replace("${HOME}", home).replace("$HOME", home).replace("\n", " ; ")
    def split(text):
        try:
            lx = shlex.shlex(text, posix=True, punctuation_chars=True); lx.whitespace_split = True; return list(lx)
        except ValueError: return text.replace("'", " ").replace('"', " ").split()
    SEP = {";", "&&", "||", "|", "&", "(", ")", "{", "}", ";;", "|&", "&>"}
    LEAD = {"builtin", "command", "time", "eval", "exec", "nohup", "env", "if", "while", "until", "!", "then", "do", "else", "elif", "sudo"}  # a command still follows these
    pay = pathlib.Path(payload); ws_ = fold(payload); own = fold(pay.parent)
    inside = lambda q: fold(q) == ws_ or fold(q).startswith(ws_ + os.sep)
    try: real_ws = fold(pay.resolve())
    except (OSError, RuntimeError): real_ws = ws_
    NET = {"curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "sftp", "rsync", "telnet", "ftp", "socat"}
    WRITERS = {"rm", "rmdir", "mv", "cp", "touch", "tee", "truncate", "ln", "chmod", "chown", "dd", "install", "mkdir"}
    def tripwire(name, args):
        """03 §5.56 items 11 and 16, a tripwire (not a sandbox: PRIVACY.md says the boundary is the user's permission
        mode): reviewers and verifiers send nothing over the network and install nothing, from their copy."""
        n = name.rsplit("/", 1)[-1]
        for k, a in enumerate(args[:-1]):
            if a.endswith("critic_ledger.py") and args[k + 1] in ("consent", "approve"): return f"critic_ledger.py {args[k + 1]}: only the owner gives consent or approves a file, through the lead"
        if n in NET: return f"a network command ({n}): reviewers and verifiers work offline in their copy"
        if n == "git" and args[:1] and args[0] in ("fetch", "pull", "push", "clone", "ls-remote", "remote", "submodule"): return f"git {args[0]} (it reaches the network): review the copy as it is"
        if n in ("npm", "pnpm", "yarn", "bun") and args[:1] and args[0] in ("install", "i", "ci", "add", "update", "upgrade", "uninstall", "remove", "rm", "link", "publish"): return f"{n} {args[0]}: it would change the dependencies (linked to the real project) or reach the network"
        if n in ("pip", "pip3", "uv", "poetry", "pipx") and any(a in ("install", "uninstall", "add", "sync", "remove") for a in args[:2]): return f"{n} install: it would change the environment (linked to the real project) or reach the network"
        if n.startswith("python") and "-m" in args and any(a in ("pip", "ensurepip", "venv") for a in args[args.index("-m") + 1:args.index("-m") + 2]): return "python -m pip: it would change the environment or reach the network"
        if (n.startswith("python") or n in ("node", "deno", "ruby", "perl", "php")) and any(re.search(r"\b(?:socket|urllib|http\.client|requests|httpx|aiohttp|fetch\(|net\.|https?\.(?:get|request)|XMLHttpRequest|LWP|Net::HTTP)", a) for a in args): return f"{n} with network code: reviewers and verifiers work offline"
        return None
    def through_link(piece, c):
        """A path inside the copy by its words that leads outside it through a link (node_modules, .venv): a write
        there changes the real project (03 §5.56 item 11)."""
        q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else c / q
        if not inside(pathlib.Path(os.path.normpath(str(q)))): return False
        try: r = fold(q.resolve())
        except (OSError, RuntimeError): return False
        return r != real_ws and not r.startswith(real_ws + os.sep)
    def walk(words, cands):
        """Judge the words (§5.56 rounds 1-2). A shell's folder can't be known for sure from the text (a cd in a
        subshell, a cd that fails, a cd spelled some way not listed here), so every path is judged from every folder
        the shell might be in: the copy, and every cd destination named so far. A cd may move within the copy, never
        out of it; a path that leads above the copy (to the agent's own scratch folder or higher) is refused."""
        cmd_pos = True; cmd = None
        sure = not any(x in ("(", ")", "|", "|&", "||", "&") or "$(" in x or "`" in x for x in words)  # no subshell or pipe: a cd joined by && really happened if the command goes on
        skip = None
        for i, w in enumerate(words):
            bare = re.sub(r"^(?:\$\(|`|\()+", "", w)
            if i >= 1 and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", words[i - 1]) and any(x.rsplit("/", 1)[-1] in ("bash", "sh", "zsh", "dash", "ksh") for x in words[max(0, i - 4):i - 1]) \
               or i >= 1 and words[i - 1] == "eval":
                why, cands = walk(split(w), cands)  # bash -c / -lc / -ec "...", eval "...": the inner commands, the same way
                if why: return why, cands
            if (cmd_pos or w != bare) and bare in ("popd", "dirs"): return "a way back to the project folder (popd, dirs)", cands
            if cmd_pos and bare not in LEAD and w not in SEP and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w):
                cmd = bare; rest_args = []
                for x in words[i + 1:]:
                    if x in SEP: break
                    rest_args.append(x)
                why = tripwire(bare, rest_args)
                if why: return why, cands
            if (cmd in WRITERS or (i >= 1 and words[i - 1] in (">", ">>", "&>", "1>", "2>")) or (cmd == "sed" and "-i" in words[max(0, i - 6):i])) and i != skip \
               and any(through_link(p_, c) for p_ in re.split(r"[=:,]", w) if p_ and not p_.startswith("-") for c in cands):
                return f"{w}: a write through a link (node_modules, .venv) changes the real project; write in your notes folder instead", cands
            if (cmd_pos or w != bare) and bare in ("cd", "pushd", "chdir"):
                args = []
                for x in words[i + 1:i + 4]:
                    if x in SEP: break  # a bare cd goes home; the next command is never its folder
                    args.append(x)
                arg = next((x for x in args if not x.startswith("-")), "~")
                skip = next((i + 1 + k for k, x in enumerate(args) if x == arg), None)  # the destination was judged here, from the folders before the cd
                new = []
                for c in cands:
                    dest = pathlib.Path(os.path.normpath(os.path.join(str(c), os.path.expanduser(arg))))  # by the path's words, not its links: node_modules is a link to the project's own
                    if not inside(dest): return f"a cd out of your workspace ({arg}): work inside {payload}", cands
                    new.append(dest)
                follows = next((x for x in words[i + 1:] if x in SEP), None)
                if sure and follows == "&&" and all(x.is_dir() for x in new): cands = list(dict.fromkeys(new))  # cd X && ...: X exists, so the rest runs in X (a failed cd stops the chain)
                else: cands = cands + [x for x in new if x not in cands]
            for piece in ([] if i == skip else re.split(r"[=:,]", w)):  # --file=../x, PATH-like lists
                if not piece or piece.startswith("-") and "/" not in piece: continue
                if not ("/" in piece or piece in (".", "..", "~") or piece.startswith("~") or any(ch in piece for ch in "*?[")): continue
                for c in cands:
                    q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else c / q
                    if fold(os.path.normpath(str(q))) == own: return f"{piece}: the folder above your workspace (stay inside {payload})", cands
                    hits = _glob.glob(str(q), recursive=True)[:2000] if any(ch in piece for ch in "*?[") else [str(q)]
                    for h in hits:
                        try: real = pathlib.Path(h).resolve()
                        except (OSError, RuntimeError, ValueError): continue
                        why = judge(real, critic, role, me)
                        if why: return why, cands
                        if above(real, critic): return f"{piece}: a folder that holds the project's .critic/ (search your workspace instead)", cands
            cmd_pos = w in SEP or bare in LEAD or (cmd_pos and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w) is not None)
        return None, cands
    why, _ = walk(split(flat), [pay])
    if why: return why
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
