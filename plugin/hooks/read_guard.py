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
  verifier  the same, plus verify packets (by path, with Read, at most one batch: the lead names its own) and the ledger's recorded decisions; never the scan
  dedup     the rule files, dedup-candidates.json and groups.json

The threat is an honest agent anchoring on what it happens to see. A same-user process set on evasion can always build
a path no check sees; that needs an OS sandbox, and the README says so.

It also refuses a fork (an Agent call with subagent_type "fork") while a review run is active: a fork inherits the
whole conversation, so it can't be blind. A run counts as active from `start` until the teardown is written, for at
most 12 hours. The main conversation and every other agent are never limited. A crash in this hook allows the call
(a broken guard must not stop the user's work); the merge script's own checks still apply."""
import json, os, pathlib, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import workspace

ALLOW = {"reviewer": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "briefs"},  # a brief holds no findings, so reading one by path (a lead that passed the path, not the text) breaks no blindness
         "verifier": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "verify", "verify-variants", "decisions.md"},  # never ledger.md: it holds dismissal notes and memories; never the scan (03 §5.56 item 13)
         "dedup": {"rules", "rules.md", ".gitignore", "dedup-candidates.json", "groups.json"}}

def role_of(agent_type):
    m = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup)", agent_type or "")
    return m.group(1) if m else None

fold = workspace.fold

def judge(target, critic, role, me, via="read"):
    """None when the path may be read; otherwise a short name of what is forbidden. via is "read" for the Read tool;
    a verifier's packets are read only that way, so each one opened is counted (03 §5.56 item 13)."""
    t, c = fold(target), fold(critic)
    if t == c: return ".critic (the whole folder)"
    g = fold(os.path.join(os.path.dirname(str(critic)), ".git"))
    if t == g or t.startswith(g + os.sep): return "the project's own .git (its history and authors; your copy has its own, without them)"
    if not t.startswith(c + os.sep):
        proj = fold(os.path.dirname(str(critic)))
        if t.startswith(proj + os.sep) and ".critic" in t[len(proj) + 1:].split(os.sep): return "a nested .critic/ in the project (an earlier run's records; your copy holds the settings you may read)"  # round 3 review
        return None
    parts = t[len(c) + 1:].split(os.sep)
    top = parts[0]
    if top == "scratch":
        if len(parts) >= 2 and me and parts[1] == me.casefold(): return None
        return ".critic/scratch" + (f"/{parts[1]}" if len(parts) >= 2 else "")
    if role == "verifier" and top in ("verify", "verify-variants"):  # 03 §5.56 item 13: its own packets, by path, and no more than one batch
        if len(parts) != 2 or not parts[1].endswith(".json"): return f".critic/{top} (the folder): read only your packets, by the paths you were given"
        if via != "read": return f".critic/{top}/{parts[1]} except with the Read tool (read your packets by path, with Read)"
        if not me or not packet_ok(critic, me, f"{top}/{parts[1]}"): return f".critic/{top}/{parts[1]}: more packets than one batch ({PACKETS}); judge only the ones you were given"
        return None
    if top == "rules.md" and top in ALLOW[role] and not rules_trusted(critic): return ".critic/rules.md (it may have come with the code and the owner hasn't approved it; 03 §5.56 item 9)"
    return None if top in ALLOW[role] else f".critic/{top}"

def rules_trusted(critic):
    """The same test the scan and the brief use: a rules.md the repository may have shipped is not read until approved."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "review", "scripts"))
        from critic_findings import state_trusted
        return state_trusted(pathlib.Path(critic).parent, "rules.md")
    except Exception: return False  # unknown: not trusted

PACKETS = 5  # critic_run.py's VERIFY_BATCH: a verifier is given at most this many packets

def packet_ok(critic, me, rel):
    """Record the packets this verifier opens, in .critic/verify-opened/ (no agent may write there, and a verifier may
    not read it); the sixth distinct one is refused."""
    f = pathlib.Path(critic) / "verify-opened" / f"{me}.json"
    try: seen = json.loads(f.read_text(encoding="utf-8")) if f.is_file() and not f.is_symlink() else []
    except (OSError, ValueError): seen = []
    if rel in seen: return True
    if len(seen) >= PACKETS: return False
    try:
        if not f.is_symlink(): f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(seen + [rel]), encoding="utf-8")
    except OSError: pass
    return True

def above(base, inner):
    """True when a search rooted at base would reach inner (base is inner itself or a folder above it)."""
    return workspace.within(inner, base)

def resolve(v, root):
    if os.sep == "\\" and re.fullmatch(r"[/\\]{2,}", str(v)): v = pathlib.Path(root).anchor  # // is the root in Git Bash, not an unnamed share (03 §5.57 item 20)
    p = pathlib.Path(os.path.expanduser(str(v)))
    if not p.is_absolute(): p = root / p
    try: return p.resolve()
    except (OSError, RuntimeError, ValueError): return p

def brief_problem(root, ti):
    """A reviewer starts with its brief unchanged (audit P5: a lead once paraphrased them and nothing caught it): during a
    review run with written briefs, a curmudgeon-reviewer's prompt must hold one of them, word for word (whitespace
    aside). Text around it is allowed. None when it does, or when there is nothing to check."""
    if not re.fullmatch(r"(?:curmudgeon:)?curmudgeon-reviewer", str(ti.get("subagent_type") or "")) or not run_active(root): return None
    bd = root / ".critic" / "briefs"
    try: started = json.loads((root / ".critic" / "ledger.json").read_text(encoding="utf-8")).get("started_at") or 0
    except Exception: return None
    briefs = [p for p in (sorted(bd.glob("brief-*.md")) if bd.is_dir() and not bd.is_symlink() else []) if p.is_file() and not p.is_symlink() and p.stat().st_mtime >= started - 2]
    if not briefs: return None
    flat = lambda t: " ".join(str(t).split())
    prompt = flat(ti.get("prompt") or "")
    try: hit = [p for p in briefs if flat(p.read_text(encoding="utf-8", errors="replace")) in prompt]
    except OSError: return "a brief in .critic/briefs/ can't be read, so this reviewer's prompt can't be checked against it; write the briefs again with critic_run.py begin"
    if len(hit) > 1: return "this prompt holds more than one brief; give each reviewer only its own (.critic/briefs/brief-<letter>.md)"  # round 2 review
    if hit:  # each reviewer its own brief: the reading orders differ (batch 5 review: one brief for all three passed)
        used_f, lock = bd / ".used.json", bd / ".used.lock"; fd = None
        for _ in range(100):  # reviewers start in parallel: claim under a lock file made with O_EXCL (round 2 review)
            try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 10: lock.unlink()
                except OSError: pass
                time.sleep(0.02)
            except OSError: break
        try:
            try: used = json.loads(used_f.read_text(encoding="utf-8")) if used_f.is_file() and not used_f.is_symlink() else {}
            except (OSError, ValueError): used = {}
            if used.get("started") != started: used = {"started": started, "briefs": []}
            name = hit[0].name; unused = [p.name for p in briefs if p.name not in used["briefs"]]
            if name in used["briefs"] and unused:  # a reviewer that failed to start gets its brief again once the others have theirs
                return f"{name} was already given to a reviewer; give this one its own brief ({', '.join(unused)}). To start a reviewer again after a failed start, start the others first"
            used["briefs"].append(name)
            try: used_f.write_text(json.dumps(used), encoding="utf-8")
            except OSError: pass
            return None
        finally:
            if fd is not None:
                os.close(fd)
                try: lock.unlink()
                except OSError: pass
    return ("start each reviewer with the text of its brief, unchanged, as its prompt (.critic/briefs/brief-<letter>.md, which critic_run.py begin wrote); "
            "this prompt doesn't hold any of them word for word. Add to it if you need to, but don't rewrite or shorten it.")

def run_active(root):
    led = root / ".critic" / "ledger.json"
    try: L = json.loads(led.read_text(encoding="utf-8")) if led.is_file() and not led.is_symlink() else {}
    except Exception: L = {}
    started = L.get("started_at") if isinstance(L, dict) else None
    if not started or time.time() - started > 12 * 3600: return False
    try:
        if any(isinstance(a, dict) and a.get("run") == L.get("run") for a in L.get("aborted") or []): return False  # the owner stopped it (critic_ledger.py abort): no longer active (5.4.0 self-review)
    except TypeError: pass
    last = root / ".critic" / "last-review.md"
    return not last.exists() or last.stat().st_mtime < started

# A command that only reads files: each part of a pipeline starts with a reader and holds no command substitution,
# variable expansion into a command, or redirect into a file.
READ_ONLY_CMD = re.compile(r"(?:[ \t]*(?:cat|grep|egrep|fgrep|head|tail|wc|nl|uniq|cut)\b[^;&|`$<>\n\r]*)(?:\|[ \t]*(?:cat|grep|egrep|fgrep|head|tail|wc|nl|uniq|cut)\b[^;&|`$<>\n\r]*)*")  # one line of plain readers; sed, sort, rg, less and more can run programs (round 3)

def owner_problem(cmd, detector):
    """A tripwire for the owner's consent and approvals (03 §5.56 items 9 and 12), in any Curmudgeon agent's command:
    their record outside the project, the helper that writes it, and, for the detector (which runs scripts from the
    project), the run's ledger script at all. Quotes and backslashes are removed first, so con""sent reads as consent."""
    flat = re.sub(r"[\\'\"]", "", cmd)
    base = os.path.realpath(os.environ.get("CURMUDGEON_STATE_DIR") or os.path.expanduser("~/.curmudgeon"))
    reading = bool(READ_ONLY_CMD.fullmatch(flat.strip()))  # a plain grep or cat of these names is reading, not writing (batch 2 review round 3)
    if not reading and (re.search(r"(?:write_owner_state|record_baseline|record_ledger|integrity_adopt|integrity_record)\b|(?:~|\$HOME|\$\{HOME\})/\.curmudgeon\b", flat) or base in flat):  # writing it, or naming its folder
        return "the owner's own record of approvals and consent is theirs to write, through the lead"
    if detector and "critic_ledger" in flat: return "the detector runs the scripted checks; the run's ledger (consent and approvals among it) is the lead's"
    if re.search(r"critic_ledger(?:\.py)?\b.*\b(?:consent|approve|adopt)\b", flat): return "only the owner gives consent, approves a file or adopts a set-aside ledger, through the lead"
    if not reading:  # the trusted copy of the pages (audit Q04). A text check is a tripwire, never a wall: it catches the plain and the usual hidden forms
        other = re.sub(r"--integrat\w*|--integrity(?=\s|$)", "", flat)  # pytest --integration, yarn check --integrity: other programs' own flags
        if re.search(r"integrity[-_ ]?(?:adopt|rec)|--inte(?:g|[$`{])|--inte\S*(?:adopt|rec)", other): return "only the owner records or adopts the trusted copy of the pages, through the lead (audit Q04)"
        runs_scan = re.search(r"critic_scan|critic_findings|\S*[*?]\S*\.py\b", flat)
        hidden = re.search(r"[$`]|\b(?:base64|xargs|printf|eval|getattr|exec|compile)\b|python\S*\s+-c\b|\.main\s*\(", re.sub(r"\$\{?CLAUDE_PLUGIN_ROOT\}?", "", flat))
        if runs_scan and hidden: return "the scan's commands run as written: a variable, decoder or python -c around critic_scan could hide an owner-only flag (audit Q04)"
    if re.search(r"security_feed(?:\.py)?\b.*\b(?:set|update|pick-folder)\b", flat) and not READ_ONLY_CMD.fullmatch(flat.strip()):  # the owner's sign-off on the downloads, and the downloads themselves (ultimate audit V13); only plain reading of the file passes (batch 1 review rounds 1 and 2: a narrow match let "-- update", a variable or python -c through)
        return "the security feed's settings, sign-off and downloads are the owner's, through the lead"
    return None

DENIED = []  # set when this call refused the tool, so pre_tool.py runs nothing after it

def deny(reason):
    DENIED.append(reason)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0

OPAQUE = re.compile(r"\$\{!|\$\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?(?:%|#|/|\^|,|:[^-=+?])|\$[@*#!?$-]|\$\{[@*#]|\{[^{}\s,]*\.\.[^{}\s,]*\}|\$\"")  # ${!X}, ${X%..} ${X#..} ${X/..} ${X:1}, $@ $* $$, {a..b}, $"..": a path built this way is refused, not guessed
PROC_ANY = re.compile(r"(?:^|[\s=:'\"])/+proc/+(?:[\d*?\[{$]|thread-self|self/+(?:task|cwd|root|fd))")  # /proc/<pid>, /proc/*, /proc/$PPID ... by text, before any expansion (round 3 review)
PROC_PID = re.compile(r"/proc/(?:\d+|thread-self|self/task/\d+)(?:/|$)")
PATH_ESC = re.compile(r"\\(?:x(?:2[EeFf]|5[Cc])|u00(?:2[EeFf]|5[Cc])|U0000(?:2[EeFf]|5[Cc])|N\{|0?5[67]|134)")  # an escape that makes . / or \\ when the code runs (Qodo on #27, #28)
def procish(path):
    """A path into another process's /proc entry, written either way: Git Bash on Windows serves /proc too, and there
    ../../proc/1 resolves to C:\\proc\\1 (03 §5.57 item 20)."""
    return bool(PROC_PID.match(re.sub(r"^[A-Za-z]:", "", os.path.normpath(str(path)).replace("\\", "/"))))
VAR_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*|\d+)(?:\[[^\]]*\])?(?:[:%#/^,@+-][^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*|\d)")
VAR_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?(?::?[-=+?]|//?[^/}]*/)([^}]*)\}")  # ${Y:-word}, ${X:+word}, ${X/pat/word}: the shell may put the word there

def expand_vars(text, shell_vars, cap=8):
    """text with each $X / ${X} replaced by every value it was given (the last ones first kept), up to cap spellings."""
    out = [text]
    for name in dict.fromkeys(m_.group(1) or m_.group(2) for m_ in VAR_REF.finditer(text)):
        vals = shell_vars.get(name)
        if vals: out = [VAR_REF.sub(lambda m_: v if (m_.group(1) or m_.group(2)) == name else m_.group(0), x) for x in out for v in vals[-cap:]][-cap * 2:]
    return out if out != [text] else []

def braces(pat, limit=64):
    """The patterns a Glob's {a,b} alternatives stand for (nested ones too), at most `limit` of them."""
    m = None; depth = 0
    for k, ch in enumerate(pat):
        if ch == "{":
            if depth == 0: open_ = k
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0: m = (open_, k); break
    if not m: return [pat]
    inner = pat[m[0] + 1:m[1]]; parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0: parts.append(cur); cur = ""; continue
        depth += ch == "{"; depth -= ch == "}"; cur += ch
    parts.append(cur)
    if len(parts) < 2: return [pat]
    out = []
    for p_ in parts:
        out += braces(pat[:m[0]] + p_ + pat[m[1] + 1:], limit)
        if len(out) >= limit: break
    return out[:limit]

HEREDOC = re.compile(r"(?<!<)<<-?(?!<)[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\1[^\n]*\n")  # never a here-string (<<<)
LONE_SLASH = re.compile(r"(?<![\w.~/$-])/{1,2}(?![\w.~*/$-])")
SCRIPT_READERS = re.compile(r"^\s*(?:(?:[A-Za-z_]\w*=\S*|timeout\s+\S+|env|nice|command)\s+)*(?:python[\d.]*|node|deno|ruby|perl|php)\b[^|;&`$()]*$|^\s*cat\b[^|;&`$()]*>[^|;&`$()]*$|^\s*tee\s+[^|;&`$()-][^|;&`$()]*$")  # cat > f <<EOF, cat <<EOF > f, tee f <<EOF
def heredoc_operators(text):
    """A heredoc body fed to a script interpreter (python3 - <<EOF, node, ruby ...) or written to a file (cat > f <<EOF)
    is a program or text, not the shell's words: a lone / or // there is division, a route or a comment (audit V22:
    `ratio = total / count` in a probe was refused as a read of /). Only those lone slashes are blanked, only in a body
    that ends with its own terminator line, and only when the line that opens it is such a reader with no pipe or
    command substitution; a body fed to a shell or to xargs is judged word for word (batch 5 review). Every word in
    the body that looks like a path (../x, /etc/y, a/b) is still judged as one."""
    out, pos = [], 0
    for m in HEREDOC.finditer(text):
        if m.start() < pos: continue
        head = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
        tail = m.group(0)[len(m.group(0).rstrip("\n").split(m.group(2), 1)[0]) + len(m.group(2)):].strip(" \t\n'\"")
        line = re.sub(r"^.*(?:&&|;)\s*", "", head) + " " + tail  # the whole opening line: a pipe after the marker feeds the body to that command (round 2 review)
        tail_ = re.sub(r"\d*>&\d+|&>\S*|\d*>\s*/dev/null", " ", tail)  # 2>&1 and the like aren't a pipe (round 3 review)
        piped_to_shell = re.search(r"\|\s*(?:sudo\s+)?(?:sh|bash|zsh|dash|ksh|xargs|eval|source|\.)\b", tail_) or re.search(r"`|\$\(", tail_)
        if head.count("'") % 2 or head.count('"') % 2 or piped_to_shell or not SCRIPT_READERS.match(re.sub(r"[|&;].*$", "", line)): continue  # inside quotes, fed to a shell, or not a reader
        end = re.search(r"(?m)^[ \t]*" + re.escape(m.group(2)) + r"[ \t]*$", text[m.end():])
        if not end: continue  # no terminator: whatever follows is commands
        stop = m.end() + end.start()
        out.append(text[pos:m.end()]); out.append(LONE_SLASH.sub(" ", text[m.end():stop])); pos = stop
    return "".join(out) + text[pos:]

TRAVERSE = re.compile(r"\b(?:walk|listdir|scandir|iterdir|r?glob|iglob|readdir\w*|opendir\w*|read_dir|find_files|Find\.find|Dir\.(?:glob|entries|children|each_child|\[))\s*[(\[]")  # code that lists or searches folders
def own_paths(own, root):
    """Every spelling of an agent's own scratch folder: as recorded (resolved), through the link the project was opened
    by (macOS's /var is /private/var), and the reverse (03 §5.57 item 20). Inline code that names any of them names
    the agent's own folder, never the project's records."""
    out = {str(own), os.path.realpath(str(own))}
    for base in {str(root), os.path.realpath(str(root))}:
        real_base = os.path.realpath(base)
        for o in list(out):
            if o == real_base or o.startswith(real_base + os.sep): out.add(base + o[len(real_base):])
    if os.sep == "\\": out |= {o.replace("\\", "/") for o in out}  # C:/Users/... as Git Bash writes it (03 §5.57 item 20)
    return out

def _top(g):  # the root as code writes it: '/', '\\', 'C:\\' or os.sep (g: the number of its quote group)
    return r"(?:[rbuRBU]{0,2}(['\"])(?:[/\\]+|[A-Za-z]:[/\\]*)\%d(?!\s*\.)|os\.(?:path\.)?(?:sep|altsep)\b|path\.sep\b|File::SEPARATOR\b)" % g
_LIST = r"\b(?:walk|listdir|scandir|iterdir|r?glob|iglob|readdir\w*|opendir\w*|read_dir|Path|PurePath|abspath|realpath|normpath|resolve|chdir|Find\.find|Dir\.\w+)\s*[(\[]\s*"  # a call whose first argument is where it starts
TOP_START = re.compile(_LIST + r"(?:(?:os\.)?path\.join\s*\(\s*)?" + _top(1)  # the root as that argument, or as the first part of a path.join there
                       + r"|" + _LIST + r"[rbuRBU]{0,2}['\"]/[^'\"\n]*[*?\[]"  # an absolute wildcard as that argument ('/**/x'), never '/*' counted in a file
                       + r"|\.anchor\b|\bparents\s*\[\s*-")  # the root by API: Path.cwd().anchor, .parents[-1]
_COMPUTED = r"\bchr\s*\(|fromCharCode|\\x2f|\\u002f|\\057|\bSOLIDUS\b|\bbytes\s*\(\s*\[|b64decode|unhexlify|codecs\.decode|\batob\s*\(|Buffer\.from\s*\("  # characters made as the code runs
COMPUTED = re.compile(_COMPUTED, re.I)
def computed_root(text):
    """Code that lists folders and builds characters as it runs ('\\x2f', chr(47), base64, bytes([...])): the built
    value can reach the listing through a name, a tuple, a loop, a return value or a keyword (Qodo on #27), so only a
    chr or fromCharCode of literal codes that are neither / nor \\ (chr(65)) is let through (Qodo on #25)."""
    if not TRAVERSE.search(text): return False
    for m in COMPUTED.finditer(text):
        if re.match(r"(?i)chr|fromCharCode", m.group(0)):
            codes = re.match(r"\s*\(?\s*([0-9][0-9\s,]*)\)", text[m.end() - (1 if m.group(0).endswith("(") else 0):])
            if codes and all(int(x) not in (47, 92) for x in re.findall(r"\d+", codes.group(1))): continue
        return True
    return False
TOP_VALUE = re.compile(_top(1))  # the root, as a whole value
HOME_START = re.compile(r"\bgetenv\s*\(\s*['\"](?:HOME|USERPROFILE)|\bPath\.home\s*\(|\bexpanduser\s*\(|\bhomedir\s*\(|\bgethome\w*|environ(?:\.get\s*\(|\[)\s*['\"](?:HOME|USERPROFILE)|process\.env\.(?:HOME|USERPROFILE)|ENV\[['\"]HOME|\bDir\.home\b")
PATTERN_CMDS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "zgrep"}  # the first operand is a pattern, never a file
SEPARATOR_OPTS = {"awk": {"-F"}, "gawk": {"-F"}, "mawk": {"-F"}, "cut": {"-d"}, "paste": {"-d"}, "column": {"-s", "-o"}}  # options that take a separator, per command
VALUE_OPTS = {"grep": {"-m", "--max-count", "-A", "-B", "-C", "--context", "--include", "--exclude", "--exclude-dir", "-d", "-D", "--label"},
              "rg": {"-m", "--max-count", "-A", "-B", "-C", "--context", "-g", "--glob", "-t", "--type", "-T", "--type-not", "-j", "--threads", "-M", "--max-columns", "--max-depth", "--color", "--colour"},
              "ag": {"-A", "-B", "-C", "-m", "--max-count", "-G", "--file-search-regex", "--ignore", "--depth"},
              "ack": {"-A", "-B", "-C", "-m", "--max-count", "--type", "--ignore-dir", "--ignore-file"}}  # options that take a value, per tool (grep -T and ag -t take none: round 2 review)
for _alias in ("egrep", "fgrep", "zgrep"): VALUE_OPTS[_alias] = VALUE_OPTS["grep"]
REDIRECTS = {">", ">>", "&>", "1>", "2>", ">|", "<", "<<", "<<-", "<<<", "<>"}
def data_words(cmd, args, base):
    """Indices (into the words) of a command's arguments that are text, never a path: a search's pattern, tr's sets,
    awk -F, cut -d, paste -d and column -s separators (audit V22: `grep -rn "../" src`, `tr / _` and `awk -F /` were
    refused). Nothing at or after a redirect is ever text (tr a a < FILE reads FILE), and files these commands read
    stay judged: grep -f FILE, rg --files PATH, ag -g PAT PATH (batch 5 review)."""
    stop = next((k for k, a in enumerate(args) if a in REDIRECTS or re.fullmatch(r"\d*(?:[<>]{1,2}|>\||<>|>&|<&)\d*-?", a) or a.startswith(("<(", ">(", "$(", "`"))), len(args)); args = args[:stop]
    out = set()
    if cmd == "tr": return {base + 1 + k for k in range(len(args))}
    if cmd in SEPARATOR_OPTS:
        for k, a in enumerate(args):
            if a in SEPARATOR_OPTS[cmd] and k + 1 < len(args): out.add(base + 2 + k)
        return out
    if cmd in PATTERN_CMDS:
        def scan():  # walks the options as the tool reads them: GNU grep and ripgrep take options after the operands too
            explicit, first, k, opts = False, None, 0, True
            while k < len(args):
                a = args[k]
                if opts and a == "--": opts = False; k += 1; continue  # after --, every word is an operand
                if opts and a.startswith("-") and a != "-":
                    if cmd == "rg" and a in ("--files", "--type-list"): explicit = True; k += 1; continue  # rg --files takes paths only
                    if a in ("-e", "--regexp") or (cmd in ("ag", "ack") and a == "-g"):
                        if k + 1 < len(args): out.add(base + 2 + k)
                        explicit = True; k += 2; continue
                    if cmd == "ag" and a == "-f": k += 1; continue  # ag -f is --follow: no value
                    if cmd == "ack" and a == "-f": explicit = True; k += 1; continue  # ack -f lists files: no pattern, every operand is a path (Qodo on #23)
                    if cmd == "ack" and a == "--match":
                        if k + 1 < len(args): out.add(base + 2 + k)
                        explicit = True; k += 2; continue
                    if a in ("-f", "--file") or a.startswith(("--file=", "--regexp=", "--match=")): explicit = True; k += 1 if "=" in a else 2; continue  # the pattern comes from the option; every operand is a path
                    if re.fullmatch(r"-[A-Za-z]*[ef]", a) and len(a) > 2:  # -rne PATTERN, -rf FILE
                        if a[-1] == "e" and k + 1 < len(args): out.add(base + 2 + k)
                        explicit = True; k += 2; continue
                    if re.fullmatch(r"-[A-Za-z]*[ef].+", a): explicit = True; k += 1; continue  # -e. or -ePATTERN, -fFILE: attached
                    k += 2 if a in VALUE_OPTS.get(cmd, VALUE_OPTS["grep"]) else 1; continue
                if first is None: first = k
                k += 1
            return explicit, first
        explicit, first = scan()  # one pass over the whole command: grep FILE -e x makes FILE a path (Qodo on #22)
        if not explicit and first is not None: out.add(base + 1 + first)
    return out

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
    if not cmd.lstrip().startswith("cd"): rest = "git " + rest  # git -C <copy> fetch: the tripwire sees the git command and its subcommand
    if not cmd.lstrip().startswith("cd") and re.search(r"[;&|`\n]|\$\(", rest): return "a git -C command followed by another command (that one would run in the project, not your copy); use cd <workspace> && ... for chains"
    home = os.path.expanduser("~")
    unquoted = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " ", rest)  # what the shell itself would expand
    if re.search(r"(?i)\$\{?(?:OLDPWD|CLAUDE_PROJECT_DIR)\b|(?:^|[\s;&|(])(?:cd|pushd)\s+-(?:\s|$|[;&|)])", unquoted): return "a way back to the project folder ($OLDPWD, cd -, $CLAUDE_PROJECT_DIR)"
    if re.search(r"\$\{?IFS\b|(?:^|[\s=:])~-|\{[^}\s]*\b(?:cd|pushd|chdir)\b[^}\s]*,", unquoted): return "a command spelled through $IFS, ~- or brace expansion"
    rest = re.sub(r"\$\{?PWD\}?", lambda m_: payload, rest)  # $PWD is the copy the command starts in
    flat_orig = re.sub(r"\\(.)", r"\1", rest).replace("${HOME}", home).replace("$HOME", home).replace("\n", " ; ")
    rest = heredoc_operators(rest)
    rest = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)(?=[\"'])", r"${\1}", rest)  # "$X"tic: the shell ends the name at the quote; shlex would glue it to tic (round 3 review)
    rest = re.sub(r'\$"', '"', rest)  # $"..": locale quoting, the text inside it (round 3 review)
    rest = re.sub(r"\$'((?:[^'\\]|\\.)*)'", lambda m_: "'" + m_.group(1).encode().decode("unicode_escape", "replace").replace("'", "") + "'", rest)  # $'..' is the text inside it, escapes decoded (round 2 review)
    flat = re.sub(r"\\(.)", r"\1", rest).replace("${HOME}", home).replace("$HOME", home).replace("\n", " ; ")
    def split(text):
        try:
            lx = shlex.shlex(text, posix=True, punctuation_chars=True); lx.whitespace_split = True; lx.commenters = ""; return list(lx)  # no comments: a # would hide the rest of the joined command (round 3 review)
        except ValueError: return text.replace("'", " ").replace('"', " ").split()
    SEP = {";", "&&", "||", "|", "&", "(", ")", "{", "}", ";;", "|&", "&>", "<(", ">("}  # a process substitution starts a command (round 3 review)
    LEAD = {"builtin", "command", "time", "eval", "exec", "nohup", "env", "if", "while", "until", "!", "then", "do", "else", "elif", "sudo"}  # a command still follows these
    pay = pathlib.Path(payload); ws_ = fold(payload); own = fold(pay.parent)
    inside = lambda q: fold(q) == ws_ or fold(q).startswith(ws_ + os.sep)
    try: real_ws = fold(pay.resolve())
    except (OSError, RuntimeError): real_ws = ws_
    PROCS = {"ps", "pgrep", "pstree", "top", "htop", "lsof", "pidof", "fuser"}
    NET = {"curl", "wget", "nc", "ncat", "netcat", "ssh", "scp", "sftp", "rsync", "telnet", "ftp", "socat", "npx", "pnpx", "bunx"}
    WRITERS = {"rm", "rmdir", "mv", "cp", "touch", "tee", "truncate", "ln", "chmod", "chown", "dd", "install", "mkdir"}
    WRAPPERS = {"timeout": {"-s", "--signal", "-k", "--kill-after"}, "nice": {"-n", "--adjustment"}, "ionice": {"-c", "-n", "-p"}, "stdbuf": set(),
                "xargs": {"-n", "-I", "-P", "-L", "-d", "-s", "-E", "-a", "--max-args", "--replace", "--max-procs", "--delimiter", "--arg-file"},
                "nohup": set(), "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}, "sudo": {"-u", "-g"}, "doas": {"-u"}, "chronic": set(), "unbuffer": set()}
    GIT_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env", "--super-prefix"}
    GIT_NET = {"fetch", "pull", "push", "clone", "ls-remote", "remote", "submodule", "send-email", "request-pull", "archive", "lfs"}
    PKG_NET = {"install", "i", "in", "ci", "add", "update", "up", "upgrade", "uninstall", "remove", "rm", "un", "link", "ln", "publish", "exec", "x", "dlx", "audit", "outdated", "view", "info", "show", "search", "create", "init", "fetch", "unlink", "dedupe", "prune", "rebuild"}
    INLINE = {"-c", "-e", "-E", "-p", "-r", "--eval", "--print", "eval"}  # the flags that take a program as text
    NET_CODE = re.compile(r"\b(?:socket|urllib|http\.client|requests|httpx|aiohttp|fetch\(|net\.|https?\.(?:get|request)|XMLHttpRequest|LWP|Net::HTTP|open-uri|curl_)"
                          r"|\brequire\(\s*['\"](?:node:)?(?:https?|http2|net|tls|dgram|dns|undici)['\"]\s*\)|\bfrom\s+['\"](?:node:)?(?:https?|http2|net|tls|dgram|undici)['\"]"
                          r"|\bimport\(\s*['\"](?:node:)?(?:https?|net|tls|undici)['\"]|\bWebSocket\b|\bwget\b|\bcurl\b")  # audit V14: require("https").get(...) and its relatives
    def positional(args, value_opts=()):
        out, k = [], 0
        while k < len(args):
            a = args[k]
            if a in value_opts: k += 2; continue
            if not a.startswith("-") or a == "-": out.append(a)
            k += 1
        return out
    def tripwire(name, args):
        """03 §5.56 items 11 and 16, a tripwire (not a sandbox: PRIVACY.md says the boundary is the user's permission
        mode): reviewers and verifiers send nothing over the network and install nothing, from their copy."""
        n = name.rsplit("/", 1)[-1]
        for k, a in enumerate(args[:-1]):
            if a.endswith("critic_ledger.py") and args[k + 1] in ("consent", "approve", "adopt"): return f"critic_ledger.py {args[k + 1]}: only the owner gives consent, approves a file or adopts a set-aside ledger, through the lead"
        if (n == "poetry" and args[:1] == ["run"]) or (n in ("pnpm", "yarn") and args[:1] == ["exec"]):  # poetry run pip install ...: judge what they launch
            return tripwire(args[1], args[2:]) if len(args) > 1 else None
        if n in WRAPPERS:  # timeout 10 curl ..., nice -n 5 pip install ..., xargs -n1 curl: judge the command they run
            k = 0
            while k < len(args) and (args[k].startswith("-") or re.fullmatch(r"\d+(?:\.\d+)?[smhd]?|[A-Za-z_][A-Za-z0-9_]*=.*", args[k])):
                k += 2 if args[k] in WRAPPERS[n] else 1
            return tripwire(args[k], args[k + 1:]) if k < len(args) else None
        if n in ("npx", "pnpx", "bunx"):  # a binary the copy already has runs from node_modules/.bin, offline
            tool_ = next(iter(positional(args)), "")
            if tool_ and "@" not in tool_[1:] and any((pathlib.Path(c) / "node_modules" / ".bin" / tool_).exists() for c in [pay]): return None
        if n in NET: return f"a network command ({n}): reviewers and verifiers work offline in their copy"
        if n in PROCS or any(a.startswith("/") and re.match(r"/proc/(?:\d+|thread-self)(?:/|$)", os.path.normpath("/" + a.lstrip("/")).replace("\\", "/")) for a in args): return f"{n} {' '.join(args[:1])}: other agents' processes and command lines are not yours to read (audit P3); work on the code in your copy"
        if n == "git":
            sub = next(iter(positional(args, GIT_VALUE)), None)
            if sub in GIT_NET: return f"git {sub} (it reaches the network): review the copy as it is"
        pos = positional(args)
        if n in ("npm", "pnpm", "yarn", "bun") and (any(a in PKG_NET - ({"exec"} if n in ("pnpm", "yarn") else set()) for a in pos[:2]) or (n == "yarn" and not pos)): return f"{n} {' '.join(pos[:1]) or '(install)'}: it would change the dependencies (linked to the real project) or reach the network"  # pnpm and yarn exec run what is installed
        if (re.fullmatch(r"pip[\d.]*|uv|pipx|conda|mamba", n) and any(a in ("install", "uninstall", "add", "sync", "remove", "download", "update", "upgrade", "lock", "run", "tool") for a in pos[:3])) \
           or (n == "poetry" and any(a in ("install", "add", "remove", "update", "lock", "sync", "self") for a in pos[:2])): return f"{n} install: it would change the environment (linked to the real project) or reach the network"  # poetry run uses what is installed; uv run may sync first
        if (n in ("bundle", "bundler", "gem", "cargo", "go", "composer", "mix", "dotnet", "brew", "apt", "apt-get", "dnf", "yum", "apk") and any(a in ("install", "add", "get", "fetch", "update", "upgrade", "download", "restore", "require", "deps.get") for a in pos[:2])) \
           or (n == "go" and pos[:2] == ["mod", "download"]): return f"{n} {' '.join(pos[:2])}: it would change the dependencies or reach the network"
        if n.startswith("python") and "-m" in args and any(a in ("pip", "ensurepip", "venv", "http.server") for a in args[args.index("-m") + 1:args.index("-m") + 2]): return "python -m pip: it would change the environment or reach the network"
        if n.startswith("python") or n in ("node", "deno", "bun", "ruby", "perl", "php", "osascript", "pwsh", "powershell"):
            code = [args[k + 1] for k in range(len(args) - 1) if args[k] in INLINE] + [x for k, x in enumerate(args) if k and args[k - 1] in ("<<<",)]
            if "<<" in args or "<<-" in args: code.append(flat_orig)  # the body as written, before its lone slashes were blanked (round 3 review)  # the body is on the lines after, in the same command text
            if any(NET_CODE.search(c) for c in code): return f"{n} with network code: reviewers and verifiers work offline"
            own_spellings = sorted(own_paths(pay.parent, root), key=len, reverse=True)
            def starts_from(c, raw=False):
                """A listing whose starting argument is built from character codes or escapes (os.walk(chr(47)): 03
                §5.57 item 18), or is a name that holds the root or such a value at that point: root = '/' then
                os.walk(root) (Qodo on #23), start = root (#24), but not after start = 'src', and never an unrelated
                chr(65) elsewhere in the code (#25). Read statement by statement, in order; raw: the command as typed,
                whose escapes ('\\x2f') the split words lose."""
                if computed_root(c): return True
                if raw: return False  # root literals in names are followed in the split words
                held = set()
                for st in re.split(r"[;\n]", c):
                    if any(re.search(_LIST + re.escape(n_) + r"\b", st) for n_ in held): return True
                    m_ = re.match(r"\s*([A-Za-z_]\w*)\s*=(?!=)\s*(.*?)\s*$", st)
                    if m_:
                        v = m_.group(2)
                        tv = TOP_VALUE.match(v)
                        if tv and re.fullmatch(r"\s*(?:#.*)?", v[tv.end():]): v = tv.group(0)  # root = '/'  # a comment (Qodo on #27)
                        if TOP_VALUE.fullmatch(v) or v in held: held.add(m_.group(1))
                        else: held.discard(m_.group(1))
                return False
            def from_top(c):
                """Code that searches the disk from its root, the home folder or a folder at or above the project can
                find .critic/ under a name it builds as it runs ('.cri' + 'tic'), so the name never shows (Qodo on
                #22). A lone / in a heredoc is blanked for the shell's words, never here: this reads the body as
                written. Splitting or joining on '/' and walking the copy's own folders are not starts at the top."""
                roots_ = {fold(str(root)), fold(os.path.realpath(str(root)))}
                for lit in re.findall(r"['\"]((?:/|[A-Za-z]:[\\/]|\\\\)[^'\"\n]*)['\"]", c):  # a folder at or above the project, written out: /home/x, C:\Users\x, C:/Users/x (03 §5.57 item 20)
                    for q in {fold(lit), fold(os.path.realpath(lit))}:  # Windows writes one folder two ways (RUNNER~1, runneradmin): realpath gives the long one
                        top_ = q.rstrip("\\/")
                        if top_ and not re.fullmatch(r"[a-z]:", top_) and any(r_ == q or r_.startswith(top_ + os.sep) for r_ in roots_): return True
                if not TRAVERSE.search(c): return False
                return bool(TOP_START.search(c) or HOME_START.search(c) or starts_from(c))  # from the root or home, or an absolute wildcard ('/**/x')
            def reaches(c):  # names .critic or ~/.curmudgeon and can leave the copy: the project's own path or a "..", never a .critic folder a probe makes inside the copy (batch 5 review)
                for lit in set(re.findall(r"['\"]((?:/|[A-Za-z]:[\\/])[^'\"\n]*)['\"]", c) + re.findall(r"(?<![\w'\"])((?:[A-Za-z]:[\\/]|/)[^\s'\";|&<>()]+)", c)):  # the agent's folder written another way, quoted or not (a heredoc's redirect target) (Windows: RUNNER~1 for runneradmin): its long form, so it is known as the agent's own (03 §5.57 item 20); never with .., which resolving would hide
                    if ".." in lit or PATH_ESC.search(lit): continue  # escapes are judged as written below; resolving would reshape them on Windows
                    rp = os.path.realpath(lit)
                    if rp != lit and any(fold(rp) == fold(o_) or fold(rp).startswith(fold(o_) + os.sep) for o_ in own_spellings): c = c.replace(lit, rp)
                owns = [re.compile(re.escape(o_) + r"(?=[/\\'\"\s,)]|$)") for o_ in own_spellings]  # the folder itself, never scratch/r10 when it is r1 (guard review)
                for lit in re.findall(r"(['\"])([^'\"\n]*)\1", c):  # a path written out from the agent's folder that stays inside it (notes/../notes/x) is its own (Qodo on #27)
                    for o_ in own_spellings:
                        if (lit[1].startswith(o_ + "/") or lit[1].startswith(o_ + os.sep)) and PATH_ESC.search(lit[1][len(o_):]): return True  # escapes that make . / or \\ (\x2e, \056) change the path when the code runs (Qodo on #27); a Windows separator or notes\\2024 doesn't (Qodo on #28)
                        if lit[1].startswith(o_ + "/") or lit[1].startswith(o_ + os.sep):
                            q_ = fold(lit[1]); fo = fold(o_)
                            if q_ == fo or q_.startswith(fo + os.sep): c = c.replace(lit[0] + lit[1] + lit[0], "''"); break
                if any(o_.search(c) for o_ in owns) and ".." in c: return True  # a climb out of the agent's own folder, joined in pieces or not (guard review)
                for o_ in owns: c = o_.sub("", c)
                if re.search(r"(?i)\.curmudgeon\b", c): return True
                if re.search(r"\.\.[/\\]+\.\.|\bdirname\s*\(\s*(?:os\.path\.)?dirname|\.parent\.parent|parents\[\s*[1-9]|os\.walk\s*\(\s*['\"]/['\"]", c): return True  # two levels up from the copy is the scratch folder, three is .critic/ (round 3 review)
                if from_top(c): return True
                if not re.search(r"(?i)\.critic\b", c): return False
                if str(root) in c or os.path.realpath(str(root)) in c or ".." in c or "~" in c: return True
                if re.search(r"(?i)\.parents?\b|\bpardir\b|\bchdir\b|\bexpanduser\b|\bglob\b|\bos\.sep\b", c): return True  # a climb by API (round 2 review)
                return any(not os.path.normpath(os.path.join(str(pay), lit)).startswith(str(pay) + os.sep) for lit in re.findall(r"['\"]([^'\"\n]*\.critic[^'\"\n]*)['\"]", c))  # a .critic path written out that leads outside the copy (round 3 review: 'tests/.critic' is fine)
            if code and starts_from(cmd, raw=True): return f"{n} with code that lists folders from a path it builds out of character codes or escapes (chr(47), '\\x2f'): reviewers and verifiers work on code in their copy (03 §5.57 item 18)"  # the raw text: the words lose their backslashes before they are split
            if any(reaches(c) for c in code): return f"{n} with code that names the project's .critic/ or Curmudgeon's own records: reviewers and verifiers work on code in their copy (audit Q01)"
        return None
    real_root = fold(pathlib.Path(root).resolve()); real_notes = fold((pay.parent / "notes").resolve())
    def write_targets(cmd_, args, base):
        """Indices (into the words) of the operands this command writes: for cp, mv, ln and install only the destination."""
        RED = (">", ">>", "&>", "1>", "2>", ">|", "<", "<<", "<<-", "<<<")
        pos = [base + 1 + k for k, a in enumerate(args) if not a.startswith("-") and a not in RED and not (k and args[k - 1] in RED)]
        if cmd_ in ("cp", "mv", "ln", "install"):
            for k, a in enumerate(args):
                if a in ("-t", "--target-directory") and k + 1 < len(args): return {base + 2 + k}
                if a.startswith("--target-directory="): return {base + 1 + k}
            return set(pos[-1:])
        if cmd_ in ("chmod", "chown"): return set(pos[1:])  # the mode or owner comes first
        if cmd_ == "dd": return {base + 1 + k for k, a in enumerate(args) if a.startswith("of=")}
        if cmd_ == "sed": return {base + 1 + k for k, a in enumerate(args) if base + 1 + k in pos}.difference(pos[:1]) if any(re.fullmatch(r"-[A-Za-z]*i.*|--in-place.*", a) for a in args) else set()
        return set(pos) if cmd_ in WRITERS else set()
    def into_project(piece, c):
        """A write whose real path is in the real project but outside this agent's copy and notes (an absolute path,
        or ../ through a link): the review would change the owner's files (03 §5.56 batch 2 review)."""
        q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else c / q
        try: r = fold(q.resolve())
        except (OSError, RuntimeError): return False
        ok = lambda base: r == base or r.startswith(base + os.sep)
        return ok(real_root) and not ok(real_ws) and not ok(real_notes)
    def through_link(piece, c):
        """A path inside the copy by its words that leads outside it through a link (node_modules, .venv): a write
        there changes the real project (03 §5.56 item 11)."""
        q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else c / q
        if not inside(pathlib.Path(os.path.normpath(str(q)))): return False
        try: r = fold(q.resolve())
        except (OSError, RuntimeError): return False
        return r != real_ws and not r.startswith(real_ws + os.sep)
    shell_vars = {}
    def walk(words, cands):
        """Judge the words (§5.56 rounds 1-2). A shell's folder can't be known for sure from the text (a cd in a
        subshell, a cd that fails, a cd spelled some way not listed here), so every path is judged from every folder
        the shell might be in: the copy, and every cd destination named so far. A cd may move within the copy, never
        out of it; a path that leads above the copy (to the agent's own scratch folder or higher) is refused."""
        cmd_pos = True; cmd = None; targets = set(); text_words = set()  # shell_vars is shared: bash -c '...' sees the outer command's variables (round 3 review)
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
                targets = write_targets(bare.rsplit("/", 1)[-1], rest_args, i)
                text_words = data_words(bare.rsplit("/", 1)[-1], rest_args, i)
            if (i in targets or (i >= 1 and words[i - 1] in (">", ">>", "&>", "1>", "2>", ">|"))) and i != skip:
                pieces = [w[3:]] if w.startswith("of=") else [p_ for p_ in re.split(r"[=:,]", w) if p_ and not p_.startswith("-")]
                if any(through_link(p_, c) for p_ in pieces for c in cands):
                    return f"{w}: a write through a link (node_modules, .venv) changes the real project; write in your notes folder instead", cands
                if any(into_project(p_, c) for p_ in pieces for c in cands):
                    return f"{w}: a write into the real project, outside your copy; write in your copy or your notes folder", cands
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
            am = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", w)
            back = next((j for j in range(i - 1, -1, -1) if words[j] in SEP), -1)
            decl = i and any(words[j] in ("export", "local", "declare", "readonly", "typeset") for j in range(back + 1, i))  # declare -x X=.., export A=1 X=..
            if am and (cmd_pos or decl): shell_vars.setdefault(am.group(1), []).extend(expand_vars(am.group(2), shell_vars) or [am.group(2)])  # Y=$X takes X's values  # X=/project/.cri, then ${X}tic: judged with every value X was given (audit Q16; a prefix X=zz cmd ${X} still expands the old one)
            pm = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\+=(.*)", w)
            if pm: shell_vars[pm.group(1)] = [v + pm.group(2) for v in shell_vars.get(pm.group(1), [""])]
            if w == "for" and cmd_pos and i + 2 < len(words) and words[i + 2] == "in":
                for x in words[i + 3:]:
                    if x in SEP or x == "do": break
                    shell_vars.setdefault(words[i + 1], []).append(x)
            if am and am.group(2) == "" and i + 1 < len(words) and words[i + 1] == "(":  # X=(a b): an array (shlex splits off the parenthesis)
                arr = []
                for x in words[i + 2:]:
                    if x == ")": break
                    arr.append(x)
                shell_vars.setdefault(am.group(1), [""])[-1:] = arr or [""]
            if cmd_pos and w == "set" and i + 1 < len(words) and words[i + 1] == "--":
                for n_, x in enumerate(words[i + 2:], 1):
                    if x in SEP: break
                    shell_vars.setdefault(str(n_), []).append(x)
            if cmd_pos and w == "printf" and i + 2 < len(words) and words[i + 1] == "-v":
                pa = []
                for x in words[i + 3:]:
                    if x in SEP: break
                    pa.append(x)
                try: shell_vars.setdefault(words[i + 2], []).append(pa[0].replace("%s", "{}").format(*pa[1:]) if pa and pa[0].count("%s") == len(pa) - 1 else "".join(pa[1:]) or "")
                except (IndexError, ValueError): shell_vars.setdefault(words[i + 2], []).append("".join(pa[1:]))
            if cmd_pos and w == "read":
                k_ = next((k for k in range(i + 1, len(words)) if words[k] == "<<<"), len(words))
                names = [x for x in words[i + 1:k_] if not x.startswith("-") and x not in SEP and re.fullmatch(r"[A-Za-z_]\w*", x)]
                fields = words[k_ + 1].split() if k_ + 1 < len(words) else []
                for n_, name_ in enumerate(names):
                    shell_vars.setdefault(name_, []).append(" ".join(fields[n_:]) if n_ == len(names) - 1 else (fields[n_] if n_ < len(fields) else ""))
            if cmd_pos and w in ("mapfile", "readarray"):
                k_ = next((k for k in range(i + 1, len(words)) if words[k] == "<<<"), None)
                names = [x for x in words[i + 1:k_ or len(words)] if re.fullmatch(r"[A-Za-z_]\w*", x)]
                if names and k_ is not None and k_ + 1 < len(words): shell_vars.setdefault(names[-1], []).append(words[k_ + 1])
            variants = [w] + [VAR_DEFAULT.sub(lambda m_: m_.group(1), w)] if VAR_DEFAULT.search(w) else [w]
            if "$" in w:  # ${X}, $X, ${X%%zz} and the like: each value the command gave X (at most 8 spellings)
                for name in dict.fromkeys(m_.group(1) or m_.group(2) for x_ in variants for m_ in VAR_REF.finditer(x_)):
                    vals = shell_vars.get(name)
                    if vals:
                        if len(variants) * len(vals) > 16 or len(vals) > 8: return f"{w}: a path built from more variable values than the guard follows; write the path out", cands  # fail closed (round 3 review)
                        variants = [VAR_REF.sub(lambda m_: v if (m_.group(1) or m_.group(2)) == name else m_.group(0), x) for x in variants for v in vals]
            if "$" in w: variants = variants + [VAR_REF.sub("", x) for x in variants if VAR_REF.search(x)]  # a name the command never set expands to nothing (round 3 review)
            if "{" in w and "," in w: variants = [b_ for x in variants for b_ in braces(x)]  # cat /p/.{critic,x}/...: as the shell expands it (round 2 review)
            if i != skip and i not in text_words and "/" in w and OPAQUE.search(w):  # round 3 review: refuse what can't be evaluated exactly, instead of chasing each spelling
                return f"{w}: a path spelled through parameter expansion ({OPAQUE.search(w).group(0)}); write the path out", cands
            if i != skip and i not in text_words and PROC_ANY.search(w): return f"{w}: other agents' processes and command lines are not yours to read (audit P3)", cands
            pieces = []
            for w_ in ([] if i == skip or i in text_words else variants):
                unurl = re.sub(r"(?i)file://", "", re.sub(r"(?i)\b(?!file:)[a-z][\w+.-]*://(?![^\s,;]*(?:\.\.|\.critic))[^\s,;]*", "", w_))  # a URL is no path (audit V22: http:// was read as /), unless it holds .. or .critic (a folder named "x:" makes x://../.. a path); file:// leaves its path
                pieces += [p_ for p_ in re.split(r"[=:,]", unurl) if p_.strip()]
                if unurl == w_ and re.search(r"[=:,]", w_): pieces.append(w_)  # the whole word too: a folder named "x:" makes x://../.. a real path
            for piece in pieces:  # --file=../x, PATH-like lists
                if os.sep == "\\" and re.fullmatch(r"[/\\]{2,}", piece or ""): piece = "/"  # // is the root in Git Bash (03 §5.57 item 20)
                if not piece or piece.startswith("-") and "/" not in piece: continue
                if not ("/" in piece or piece in (".", "..", "~") or piece.startswith("~") or any(ch in piece for ch in "*?[")): continue
                if re.match(r"/proc/(?:\d+|thread-self)(?:/|$)", os.path.normpath("/" + piece.lstrip("/")).replace("\\", "/") if piece.startswith("/") else ""): return f"{piece}: other agents' processes and command lines are not yours to read (audit P3)", cands
                for c in cands:
                    q = pathlib.Path(os.path.expanduser(piece)); q = q if q.is_absolute() else c / q
                    if fold(os.path.normpath(str(q))) == own: return f"{piece}: the folder above your workspace (stay inside {payload})", cands
                    hits = _glob.glob(str(q), recursive=True)[:2000] if any(ch in piece for ch in "*?[") else [str(q)]
                    if procish(q): return f"{piece}: other agents' processes and command lines are not yours to read (audit P3)", cands
                    for h in hits:
                        if procish(h): return f"{piece}: other agents' processes and command lines are not yours to read (audit P3)", cands  # /proc/*/cmdline, ../../proc/1 (round 2 review)
                        try: real = pathlib.Path(h).resolve()
                        except (OSError, RuntimeError, ValueError): continue
                        why = judge(real, critic, role, me, "bash")
                        if why: return why, cands
                        if above(real, critic): return f"{piece}: a folder that holds the project's .critic/ (search your workspace instead)", cands
            cmd_pos = w in SEP or bare in LEAD or (cmd_pos and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w) is not None)
        return None, cands
    why, _ = walk(split(flat), [pay])
    if why: return why
    return None

def main(data=None):
    if data is None:
        try: data = json.load(sys.stdin)
        except Exception: return 0
    tool, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    root = workspace.project_root(data)
    if tool in ("Agent", "Task"):
        if str(ti.get("subagent_type") or "").lower() == "fork" and run_active(root):
            return deny("Curmudgeon: no forks during a review run. A fork inherits the whole conversation, so it can't review blind. Start the named agent (curmudgeon:curmudgeon-reviewer, -verifier, -dedup or -detector) instead.")
        why = brief_problem(root, ti)
        if why: return deny(f"Curmudgeon: {why}")
        return 0
    role = role_of(data.get("agent_type"))
    if tool == "Bash" and re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")):
        why = owner_problem(str(ti.get("command") or ""), not role)
        if why: return deny(f"Curmudgeon: {why} (03 §5.56 item 12).")
    if tool in ("PowerShell", "Monitor") and re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")):  # every Curmudgeon agent, the detector too: the guard and the owner tripwire read bash only, and Windows turns the PowerShell tool on by itself when Git Bash isn't there (03 §5.57 item 20; Qodo on #27)
        return deny(f"Curmudgeon: Curmudgeon's agents run shell commands through the Bash tool only, where they are checked; {tool} commands aren't. Use Bash.")
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
                p = resolve(re.sub(r"^file://", "", v), root); why = judge(p, critic, role, me, "lsp")
                if why: break
    elif tool in ("Read", "NotebookRead"):
        v = ti.get("file_path") or ti.get("notebook_path")
        if isinstance(v, str) and v:
            p = resolve(v, root); why = judge(p, critic, role, me)
    elif tool in ("Grep", "Glob"):
        here = pathlib.Path(data.get("cwd") or root)  # the tools search the session's current folder when no path is given
        start = resolve(ti.get("path") or str(here), here)
        why = judge(start, critic, role, me, "search")
        pat = str(ti.get("pattern") or "")
        if not why and tool == "Glob" and (any(ch in pat for ch in "*?[{") or "critic" in pat.casefold() or ".." in pat):  # expand it for real and judge what it matches
            import glob as _glob, itertools
            def found_for(one):
                if os.path.isabs(one):  # the fixed part resolved, so a Windows short name (RUNNER~1) matches the folder listing (03 §5.57 item 20)
                    parts_ = re.split(r"[\\/]", one); k_ = next((i for i, x in enumerate(parts_) if any(ch in x for ch in "*?[")), len(parts_))
                    fixed = os.sep.join(parts_[:k_]) or os.sep
                    if re.fullmatch(r"[A-Za-z]:", fixed): fixed += os.sep
                    base_, pat_ = pathlib.Path(os.path.realpath(fixed)), "/".join(parts_[k_:]) or "."
                else: base_, pat_ = pathlib.Path(start), one
                try: yield from (str(x) for x in base_.glob(pat_))  # pathlib matches dot-folders on every Python, as Glob does
                except (NotImplementedError, ValueError, OSError):
                    hidden = {"include_hidden": True} if sys.version_info >= (3, 11) else {}
                    yield from _glob.glob(os.path.join(str(start), one), recursive=True, **hidden)
            n = 0; alts = braces(pat)
            leaves = bool(re.search(r"(?:^|[{,])(?:/|\\|[A-Za-z]:[\\/]|~)", pat)) or ".." in pat or bool(re.search(r"\.\{|\{\.|,\.", pat)) or above(start, critic) or fold(start) == fold(critic)  # the pattern, or any {a,b} alternative, can reach .critic/ (round 2 review)
            if len(alts) >= 64 and leaves: why = "a Glob with 64 or more {a,b} alternatives that can reach .critic/ (split it, or search your workspace)"  # never judged on a cut-down list (batch 5 review)
            for h in ([] if why else itertools.chain.from_iterable(found_for(x) for x in alts)):  # {a,b} alternatives, as the Glob tool expands them (audit V27)
                n += 1
                if n > 5000:  # audit Q17: never a silent cut-off when the pattern can reach .critic/
                    if leaves: why = "a Glob with more than 5,000 matches that can reach .critic/ (narrow the pattern, or search your workspace)"
                    break
                hp = resolve(h, root); why = judge(hp, critic, role, me, "search")
                if why: break
        if not why and tool == "Grep" and above(start, critic):  # a Glob is judged above by what it really matches
            g = str(ti.get("glob") or "").strip()
            try: root_real = root.resolve()
            except OSError: root_real = root
            if rec or fold(start) != fold(root_real) or not re.fullmatch(r"!(\*\*/)?\.critic(/\*{0,2})?", g, re.I):
                why = ".critic (a search from a folder above it); search your workspace" + (f" (path {rec['payload']})" if rec else ", or the project root with glob \"!.critic\", or a narrower folder")
    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str) and cmd:
            if not rec: why = "anything with Bash: no private workspace was made for you, so review by reading (Read, Grep, Glob)"
            else:
                try: why = bash_problem(cmd, rec, root, critic, role, me)
                except Exception as e: why = f"a command the guard couldn't read ({type(e).__name__}); write it more plainly"  # fail closed for a review agent, never allow on a crash (round 3 review)
    if why: return deny(f"Curmudgeon blindness: a {role} may not read {why}.{where} Review only what your brief gives you.")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
