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
GIT_C_SAFE = r"color(?:\.[\w.-]+)?=\S*|core\.quotepath=\S*|core\.pager=(?:cat|less|more|)|pager\.[\w-]+=(?:false|cat|)|log\.(?:date|decorate|abbrevcommit)=\S*|diff\.(?:noprefix|renames|context)=\S*|i18n\.[\w.]+=\S*"  # git -c with a setting that only changes how output looks; core.fsmonitor, core.pager=PROGRAM, diff.external and the like run a program (round 3, F-6e504768)
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd"}
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


def _double_quoted(s):
    """The text inside each double-quoted part of s, read the way the shell reads quotes: an apostrophe inside double
    quotes is a plain character, so it never hides a later $( ) (round 3, F-9707272d)."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\": i += 2; continue
        if c == "'":
            j = s.find("'", i + 1); i = n if j < 0 else j + 1; continue
        if c == '"':
            j, buf = i + 1, []
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n: buf.append(s[j:j + 2]); j += 2; continue
                buf.append(s[j]); j += 1
            out.append("".join(buf)); i = j + 1; continue
        i += 1
    return out


def problem(cmd, payload, notes, own_review=None, _depth=0):
    """None when every part of `cmd` is on the reviewers' command list, else one line saying what isn't and what to
    use instead. `payload` is the agent's copy, `notes` its notes folder; writes may go only there, to its claimed
    review, or to /dev/null."""
    D = data(); flat = conduct._strip_heredocs(cmd)
    bare = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", flat)
    for rx, what, instead in NO_FORM:
        if re.search(rx, bare): return f"{what} is outside the reviewers' command list; {instead}"
    for q in _double_quoted(flat):  # $( ) inside double quotes: the command inside is judged the same way (round 2)
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
        if t and ("$(" in t or "`" in t): return f"{how} writes to a place named by a command's output, which the guard can't judge before it runs; write to a plain path in ../notes/ instead"  # round 3, F-65cdbe66
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
        lead = {conduct.name_of(w.lstrip("\x01")) for w in words[:len(words) - len(inner)]} if inner else set()
        for w_ in sorted(lead & set(conduct.WRAPPERS)):  # sudo, doas, exec: the wrapper is judged too, before what it runs (round 3, F-f9ad4b76)
            e_ = D["commands"].get(w_)
            if e_ is not None and e_["c"] not in D["accepted"]: return f"{w_} {D['classes'].get(e_['c'], e_['c'])}, which is outside the reviewers' command list; run the command itself"
        if "xargs" in lead and inner and _writes(D, inner): return f"xargs adds words the guard can't see to {conduct.name_of(inner[0])}, which writes files; name the files yourself, inside your copy or ../notes/"  # round 3, F-65cdbe66
        if inner and len(inner) < len(words): words = inner
        why = _judge(D, words, roots, cwd)
        if why: return why
    return None


def _writes(D, words):
    n = conduct.name_of(words[0].lstrip("\x01")); e = D["commands"].get(n) or {}
    return e.get("c") == "write-own" or n in conduct.WRITERS_ALL | conduct.WRITERS_LAST or "out" in e or any(re.fullmatch(r"-[A-Za-z]*i.*|--in-place(?:=.*)?", w.lstrip("\x01")) for w in words[1:])


def _long(a, o):
    """a names the long option o, whole or cut short as GNU tools allow (--out for --output: round 3, F-b5a681a6)."""
    k = a.split("=", 1)[0]
    return a == o or a.startswith(o + "=") or len(k) >= 4 and o.startswith(k)


def _short(a, o):
    """a holds the short option o, alone, with its value joined, or bundled after other flags (-uo FILE: round 3)."""
    return a.startswith("-") and not a.startswith("--") and len(a) > 1 and o[1] in a[1:]


def _judge(D, words, roots, cwd):
    raw = words[0].lstrip("\x01"); n = conduct.name_of(raw); args = [w.lstrip("\x01") for w in words[1:]]
    e = D["commands"].get(n) or D["commands"].get(n.lower())
    if e is None:
        if re.fullmatch(r"[\w.-]+\.(?:py|js|mjs|cjs|ts|sh|rb|php|pl)", n) or raw.startswith(("./", "../")): e = {"c": "code"}  # a script in its copy or notes, run by path
        else: return f"{n} is not on Curmudgeon's list of known commands, so it is blocked and listed for the owner; use the reading tools (cat, grep, ls, find), run code with python3 or node, or say why in your review"
    c = e["c"]
    if n == "git": return _git_rules(args, roots, cwd)
    if "sub" in e:
        sub = next((a for a in args if a in e["sub"]), None) or next((a for a in args if not a.startswith("-")), args[0] if args else "")  # the first known subcommand, so an option's value is never taken for one (round 3, F-9fada6f5)
        c = e["sub"].get(sub, e["sub"].get(args[0], c) if args else c)
        if sub not in e["sub"]: sub = " ".join(args)[:60]  # no known subcommand: show what it was given
        if c not in D["accepted"]: return f"{n} {sub} {D['classes'].get(c, c)}, which is outside the reviewers' command list; run the project's own tests (npm test, go test, cargo test) instead"
        return None
    if "first" in e:
        if args and args[0] in e["first"] and "-p" not in args and "--package" not in args: c = e.get("first_cls", c)
        else: return e.get("why") or f"{n} {D['classes'].get(c, c)}"
    if c not in D["accepted"]: return f"{n} {D['classes'].get(c, c)}, which is outside the reviewers' command list; {e.get('why') or 'use the reading tools (cat, grep, ls, find), or run code from your copy with python3 or node'}"
    if "only" in e and not any(a in e["only"] for a in args): return e.get("why") or f"{n} only as {' or '.join(e['only'])}"
    if "only_re" in e and not any(re.search(e["only_re"], a) for a in args if a.startswith("-") or a is args[0]): return e.get("why") or f"{n} only in its listing form"
    for o in e.get("w", []):
        if any(_long(a, o) if o.startswith("--") else _short(a, o) if len(o) == 2 and o[0] == "-" else a == o or a.startswith(o + "=") for a in args):
            return f"{n} {o} writes a file or runs a program, which is outside the reviewers' command list; print the result and redirect it into ../notes/ instead"
    if "out" in e:
        pos = [a for a in args if not a.startswith("-")]
        if len(pos) >= e["out"]:
            t = pos[e["out"] - 1]; t = t if os.path.isabs(t) else os.path.join(cwd, t)
            if not _inside(t, roots): return f"{n} writes {pos[e['out'] - 1]}, outside your copy and notes; write in ../notes/ instead"
    plain = [a for k, a in enumerate(args) if a not in ("<", "<<", "<<<", "<<-") and not (k and args[k - 1] in ("<", "<<", "<<<", "<<-"))]
    if n in SHELLS and (not [a for a in plain if not a.startswith("-")] or "-s" in plain): return f"{n} reading commands from its input (a pipe, a here-document or <) runs text the guard can't judge; write a script in ../notes/ and run it"  # round 3, F-78964562
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
        c_ = args[k + 1] if args[k] == "-c" and k + 1 < len(args) else args[k][2:] if re.fullmatch(r"-c\S+", args[k]) else None
        if c_ is not None and not re.fullmatch(GIT_C_SAFE, c_, re.I): return f"git -c {c_} sets something that can run a program; use git's own defaults, or -c color.ui=never and -c core.pager=cat"
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
