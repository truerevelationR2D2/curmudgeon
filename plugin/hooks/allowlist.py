"""The reviewers' command list (03 §5.57 items 52 and 53): which shell commands a reviewer or verifier may run. The
commands Curmudgeon knows, with their classes, are data in commands.json; the classes reviewers may use are its
"accepted" list. A known command of another class is blocked with its class; an unknown command is blocked as unknown
and listed for the owner, who adds it to commands.json (critic_commands.py proposes entries), so the list grows by
data, never by new code. Nothing here ever cuts a review: a cut stays with conduct.py's backstop and the outcome
check (outcome.py), which judges what code a reviewer runs really changes on disk.

Measured 18 Nov 2026: honest reviewers and verifiers used 51 command names in 4,311 commands (311 eval runs on Linux
and two review sessions on a Windows PC)."""
import json
import os
import re

import conduct

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands.json")
KEYWORDS = {"if", "then", "else", "elif", "fi", "for", "in", "do", "done", "while", "until", "case", "esac", "!", "{", "}"}
NO_FORM = [  # (pattern on the command with quoted text and here-document bodies taken out, what it is, what to use instead)
    (r"<\(|>\(", "process substitution", "write to a file in your notes folder and read it back"),
    (r"(?:^|[;&|(]\s*)function\s+\w|\w\s*\(\)\s*\{", "a shell function", "write a script in your notes folder and run it"),  # at a command's start only: grep function x is a search (5.10.0 round 2, F-702ecf38)
]
GIT_READ = {"log", "show", "diff", "status", "blame", "ls-files", "grep", "rev-parse", "cat-file", "ls-tree",
            "shortlog", "describe", "--version", "help", "show-ref", "for-each-ref", "whatchanged", "name-rev"}
GIT_LIST = {"branch": {"-a", "-r", "-v", "-vv", "--list", "-l", "--all", "--remotes", "--show-current", "--contains", "--merged", "--no-merged", "--sort", "--format", "--column", "--no-column", "--points-at"},
            "tag": {"-l", "--list", "-n", "--contains", "--points-at", "--sort", "--format", "--merged", "--no-merged"},
            "remote": {"-v", "--verbose", "show", "get-url"},
            "config": {"--get", "--get-all", "--list", "-l", "--get-regexp", "--show-origin", "--show-scope", "--null", "-z", "--name-only"},
            "reflog": {"show"}}
GIT_GLOBAL = {"-C": 1, "-c": 1, "--git-dir": 1, "--work-tree": 1, "--no-pager": 0, "-P": 0, "--no-optional-locks": 0, "--bare": 0}
GIT_WRITE_OPTS = ("--output", "-o", "--ext-diff", "--textconv", "-O", "--open-files-in-pager")
_data = None


def data():
    global _data
    if _data is None:
        with open(DATA, encoding="utf-8") as f: _data = json.load(f)
    return _data


def _real(p):
    return os.path.normcase(os.path.realpath(str(p)))


def _inside(path, roots):
    """Inside one of the roots, by its real path, so a link in the copy that points out is outside (round 2)."""
    p = _real(path)
    return any(p == r or p.startswith(r + os.sep) for r in roots)


def problem(cmd, payload, notes, own_review=None, _depth=0):
    """None when every part of `cmd` is on the reviewers' command list, else one line saying what isn't and what to
    use instead. `payload` is the agent's copy, `notes` its notes folder; writes may go only there, to its claimed
    review, or to /dev/null."""
    D = data(); flat = conduct._strip_heredocs(cmd)
    bare = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", flat)
    for rx, what, instead in NO_FORM:
        if re.search(rx, bare): return f"{what} is outside the reviewers' command list; {instead}"
    for q in re.findall(r'"(?:\\.|[^"\\])*"', re.sub(r"'[^']*'", "''", flat)):  # $( ) inside double quotes: the command inside is judged the same way (round 2)
        for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", q):
            inner = inner[0] or inner[1]
            if _depth < 3 and inner.strip():
                why = problem(f"cd {payload} && {inner}", payload, notes, own_review, _depth + 1)
                if why: return why
        if re.search(r"\$\([^()]*\(", q): return "command substitution nested inside double quotes is outside the reviewers' command list; run the inner command on its own"
    toks = conduct._tokens(cmd)
    if toks is None: return "a command the guard can't read; write it more plainly"
    roots = [_real(payload), _real(notes)] + ([_real(own_review)] if own_review else [])
    for t, how in conduct.write_targets(cmd, payload, kinds=True):
        if t and not _inside(t, roots) and os.path.normpath(t) not in (os.devnull, "/dev/null"):
            return f"{how} writes {t}, outside your copy and notes; write in your copy or ../notes/ instead"
    cwd, assigned = str(payload), {}
    for seg in conduct.segments(toks):
        if seg[0] in ("for", "select", "case"): continue  # a loop's header: a name and the words it takes, no command
        words = [w for w in seg if w not in KEYWORDS]
        while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
            k_, v_ = words[0].split("=", 1); assigned[k_] = v_.lstrip("\x01"); words = words[1:]
        if not words: continue
        if words[0] in ("<", "<<", "<<<", ">", ">>", "2>", "&>", ">&"): continue  # a redirect's own segment piece
        head = words[0].lstrip("\x01")
        var = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", head)
        if var and var.group(1) in assigned: words = [assigned[var.group(1)]] + words[1:]  # P=python.exe; $P app.py: the program it names (Windows run, 18 Nov)
        if conduct.name_of(words[0]) in ("cd", "pushd"):
            dest = words[1].lstrip("\x01") if len(words) > 1 else ""
            nxt = os.path.join(cwd, os.path.expanduser(dest)) if dest else cwd
            if _inside(nxt, roots): cwd = os.path.normpath(nxt)
            continue
        inner = conduct.run_words(words)  # timeout 5 X, xargs X, nice X, env X: X is what runs
        if inner and len(inner) < len(words): words = inner
        why = _judge(D, words, roots, cwd)
        if why: return why
    return None


def _judge(D, words, roots, cwd):
    raw = words[0].lstrip("\x01"); n = conduct.name_of(raw); args = [w.lstrip("\x01") for w in words[1:]]
    e = D["commands"].get(n) or D["commands"].get(n.lower())
    if e is None:
        if re.fullmatch(r"[\w.-]+\.(?:py|js|mjs|cjs|ts|sh|rb|php|pl)", n) or raw.startswith(("./", "../")): e = {"c": "code"}  # a script in its copy or notes, run by path
        else: return f"{n} is not on Curmudgeon's list of known commands, so it is blocked and listed for the owner; use the reading tools (cat, grep, ls, find), run code with python3 or node, or say why in your review"
    c = e["c"]
    if n == "git": return _git_rules(args, roots, cwd)
    if "sub" in e:
        sub = next((a for a in args if not a.startswith("-")), args[0] if args else "")
        c = e["sub"].get(sub, e["sub"].get(args[0], c) if args else c)
        if c not in D["accepted"]: return f"{n} {sub} {D['classes'].get(c, c)}, which is outside the reviewers' command list; run the project's own tests (npm test, go test, cargo test) instead"
        return None
    if "first" in e:
        if args and args[0] in e["first"] and "-p" not in args and "--package" not in args: c = e.get("first_cls", c)
        else: return e.get("why") or f"{n} {D['classes'].get(c, c)}"
    if c not in D["accepted"]: return f"{n} {D['classes'].get(c, c)}, which is outside the reviewers' command list; {e.get('why') or 'use the reading tools (cat, grep, ls, find), or run code from your copy with python3 or node'}"
    if "only" in e and not any(a in e["only"] for a in args): return e.get("why") or f"{n} only as {' or '.join(e['only'])}"
    if "only_re" in e and not any(re.search(e["only_re"], a) for a in args): return e.get("why") or f"{n} only in its listing form"
    for o in e.get("w", []):
        if any(a == o or a.startswith(o + "=") or len(o) == 2 and o[0] == "-" and o[1] != "-" and a.startswith(o) and len(a) > 2 and not a.startswith("--") for a in args):
            return f"{n} {o} writes a file or runs a program, which is outside the reviewers' command list; print the result and redirect it into ../notes/ instead"
    if "out" in e:
        pos = [a for a in args if not a.startswith("-")]
        if len(pos) >= e["out"]:
            t = pos[e["out"] - 1]; t = t if os.path.isabs(t) else os.path.join(cwd, t)
            if not _inside(t, roots): return f"{n} writes {pos[e['out'] - 1]}, outside your copy and notes; write in ../notes/ instead"
    if e.get("c_deny") and any(re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a) for a in args): return f"{n} -c runs a command given as text, which is outside the reviewers' command list; run the commands themselves"
    if e.get("m_deny"):
        mod = args[1] if len(args) >= 2 and args[0] == "-m" else args[0][2:] if args and args[0].startswith("-m") and len(args[0]) > 2 else None
        if mod in e["m_deny"]: return f"{n} -m {mod} installs or changes packages, which is outside the reviewers' command list; use what the project already has instead"
    return None


def _git_rules(args, roots, cwd):
    """git with read-only subcommands only, after its global options (-C DIR, -c k=v, --no-pager...). -C must name a
    folder inside its copy or notes, from the folder the command is in (round 2, F-35db7c2e). A listing subcommand
    (branch, tag, remote, config, reflog) passes only when every option it carries is a listing one (round 2,
    F-c06b937b); options that write a file or run a program are refused on any subcommand."""
    k = 0
    while k < len(args) and (args[k] in GIT_GLOBAL or re.fullmatch(r"-c\S+|--git-dir=\S+|--work-tree=\S+", args[k])):
        if args[k] in ("-C", "--git-dir", "--work-tree") and k + 1 < len(args) and not _inside(os.path.join(cwd, os.path.expanduser(args[k + 1])), roots):
            return f"git {args[k]} {args[k + 1]} points outside your copy and notes; run git from your copy instead"
        k += 1 + (GIT_GLOBAL.get(args[k], 0) if args[k] in GIT_GLOBAL else 0)
    sub = args[k] if k < len(args) else ""
    rest = args[k + 1:]
    if any(a == o or a.startswith(o + "=") for a in rest for o in GIT_WRITE_OPTS): return f"git {sub} with an option that writes a file or runs a program is outside the reviewers' command list; print the result and redirect it into ../notes/ instead"
    if not sub or sub in GIT_READ: return None
    if sub in GIT_LIST:
        opts = [a for a in rest if a.startswith("-") or sub in ("remote", "reflog") and a in GIT_LIST[sub]]
        named = [a for a in rest if not a.startswith("-")]
        listing = all(a.split("=")[0] in GIT_LIST[sub] for a in opts)
        if listing and (opts or not named or sub == "remote" and named[0] in GIT_LIST[sub]) and (opts or sub not in ("config", "reflog") or sub == "reflog" and not rest): return None
    return f"git {sub} can change the repository; reviewers use read-only git (log, show, diff, status, blame, grep, branch --list) instead"
