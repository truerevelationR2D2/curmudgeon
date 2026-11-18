"""The reviewers' standard (03 §5.57 item 44): each reviewer claims its review at the start with the token its own
brief holds, and the hooks record which agent owns which review. A reviewer that writes outside its own space (its
private copy, its notes and the review it claimed), or that tries to change or interfere with the proctor,
Curmudgeon's records, settings or the test, is cut: its review is voided as in ruling 35. Other blocked actions (an
accidental read the guard stops) stay blocked and are listed for the owner, never cut.

Records, under .critic/proctor/ (written only by the scripts and hooks; agents can't write or read there):
  claim-tokens.json      {letter: token}, written with the briefs
  claims/<agent>.json    {"review": "review-A.json", "at": time}
  cut/<agent>.jsonl      one line per broken rule: {"at", "why"}
  blocked/<agent>.jsonl  one line per blocked action that doesn't cut: {"at", "why"}"""
import json, os, pathlib, re, secrets, time

LIST_MAX = 200  # lines kept per agent in blocked/; cut/ lines are few by nature, and kept all
CLAIM_RX = re.compile(r"critic_proctor\.py['\"]?\s+claim\s+([A-Za-z])\s+([0-9a-f]{12})\b")
SETTINGS_RX = re.compile(r"(?i)(?:^|[\\/])(?:\.claude(?:[\\/]|$)|CLAUDE(?:\.local)?\.md$)")  # read by Claude Code itself: settings, hooks, agents, instructions
OWN_SETTINGS_RX = re.compile(r"(?i)(?:^|[\\/])CLAUDE(?:\.local)?\.md$")  # in its own folder only an instructions file counts: Claude Code loads CLAUDE.md from any folder it reads, but no .claude/ there; a fake home with .claude/ in the notes is a probe (5.9.0 measurement)

def _dir(root): return pathlib.Path(root) / ".critic" / "proctor"

def _clean(v): return re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:64]

def started(root):
    try: return float(json.loads((pathlib.Path(root) / ".critic" / "ledger.json").read_text(encoding="utf-8")).get("started_at") or 0)
    except (OSError, ValueError, TypeError, AttributeError): return 0.0

def _write(path, text, append=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink(): return  # never through a link a repository planted
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(text)

def new_tokens(root, letters):
    """One fresh claim token per letter, written beside the briefs. Each brief names only its own."""
    t = {x: secrets.token_hex(6) for x in letters}
    _write(_dir(root) / "claim-tokens.json", json.dumps(t))
    return t

def tokens(root):
    try: j = json.loads((_dir(root) / "claim-tokens.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    return {str(k).upper(): str(v) for k, v in j.items()} if isinstance(j, dict) else {}

def claims(root):
    """{agent: review name} for this run's claims."""
    out, since = {}, started(root)
    for f in (_dir(root) / "claims").glob("*.json"):
        try: j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError): continue
        if isinstance(j, dict) and isinstance(j.get("review"), str) and float(j.get("at") or 0) >= since - 2: out[f.stem] = j["review"]
    return out

def claimed_by(root, agent): return claims(root).get(_clean(agent))

def claim(root, agent, letter, token):
    """Record the claim; returns None when it holds, else why it was refused (the claim is then not recorded)."""
    me, letter = _clean(agent), letter.upper()
    if not me: return "a claim from an agent with no id"
    want = tokens(root).get(letter)
    if not want or not secrets.compare_digest(want, token): return f"review {letter}'s claim token doesn't match: claim the letter and token your own brief gives"
    have = claims(root)
    name = f"review-{letter}.json"
    if have.get(me) and have[me] != name: return f"you already claimed {have[me]}; a reviewer claims one review"
    stopped = lambda a: (pathlib.Path(root) / ".critic" / "stops" / f"{a}.json").is_file()  # a reviewer that has stopped holds its letter no longer, so a replacement started with the same brief can claim it (5.9.0 blind round C6)
    other = next((a for a, r in have.items() if r == name and a != me and not stopped(a)), None)
    if other: return f"{name} is already claimed by another reviewer"
    _write(_dir(root) / "claims" / f"{me}.json", json.dumps({"review": name, "at": time.time()}))
    return None

def note(root, agent, why, kind):
    """kind: "cut" or "blocked"."""
    me = _clean(agent)
    if not me: return
    f = _dir(root) / kind / f"{me}.jsonl"
    try:
        if kind == "blocked" and f.is_file() and sum(1 for _ in f.open(encoding="utf-8")) >= LIST_MAX: return
        _write(f, json.dumps({"at": time.time(), "why": str(why)[:300]}) + "\n", append=True)
    except OSError: pass

def listed(root, agent, kind):
    """This run's lines for one agent: a list of reasons."""
    since, out = started(root), []
    try:
        for line in (_dir(root) / kind / f"{_clean(agent)}.jsonl").open(encoding="utf-8"):
            try: j = json.loads(line)
            except ValueError: continue
            if isinstance(j, dict) and float(j.get("at") or 0) >= since - 2: out.append(str(j.get("why") or ""))
    except OSError: pass
    return out

def all_listed(root, kind):
    return {f.stem: listed(root, f.stem, kind) for f in (_dir(root) / kind).glob("*.jsonl")}

def is_reviewer(agent_type): return bool(re.fullmatch(r"(?:curmudgeon:)?curmudgeon-reviewer", str(agent_type or "")))

WRITERS_ALL = {"tee", "rm", "touch", "truncate", "mkdir", "rmdir", "shred", "unlink"}
WRITERS_LAST = {"cp", "mv", "install", "ln", "rsync"}

HEREDOC_RX = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n.*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|\Z)", re.S)

def _tokens(cmd):
    """The command's words, with every here-document's body left out (a probe script written with cat <<EOF is data,
    so a 'kill' or a '>' inside it is never a command: 5.9.0 blind round, where three honest reviewers were cut for
    probes that named kill). Quoted text stays one word, so a quoted '>' is an argument, not a redirect; a newline
    outside quotes ends a command like ';' (5.9.0 blind round C2, C8)."""
    import shlex
    flat = HEREDOC_RX.sub(lambda m: "<< " + m.group(2) + m.group(3) + "\n", cmd)  # the rest of the opening line stays: `cat <<EOF > file` writes file (5.9.2 blind round 2)
    if os.name == "nt": flat = re.sub(r"\\(?=[^\s\"'$`\\])", "/", flat)  # Windows paths (C:\Users\...) keep their separators; a backslash before a quote or a space still escapes it
    held, buf, i, q = [], [], 0, None
    while i < len(flat):
        ch = flat[i]
        if q is None and ch in "'\"":
            j = i + 1
            while j < len(flat) and flat[j] != ch:
                j += 2 if ch == '"' and flat[j] == "\\" else 1
            held.append(flat[i + 1:j].replace('\\"', '"') if ch == '"' else flat[i + 1:j]); buf.append(f"\x00{len(held) - 1}\x00"); i = j + 1; continue
        if ch == "\\" and i + 1 < len(flat): buf.append(flat[i:i + 2]); i += 2; continue
        buf.append(" ; " if ch == "\n" else ch); i += 1
    text = re.sub(r"(^|[\s;&|()])\d+(?=[<>])", r"\1", "".join(buf))  # 2>/dev/null, 2>&1: a stream number written against its redirect is no word ("touch 2 > f" keeps its 2; 5.9.2 blind round 2)
    try:
        lx = shlex.shlex(text, posix=True, punctuation_chars=True); lx.whitespace_split = True; lx.commenters = ""; words = list(lx)
    except ValueError:  # a command the shell itself may refuse (a trailing backslash, say) is still judged, by its plain words (5.9.2 blind round 2)
        words = re.findall(r"[;&|()<>]+|[^\s;&|()<>]+", text.replace("\\", " "))
    put = lambda w: re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], w)
    words = [o for w in words for o in _ops(w)]
    return [w if "\x00" not in w else ("\x01" + put(w) if w.strip("\x00").isdigit() else put(w)) for w in words]  # \x01: a word that was wholly quoted, never an operator

WRAPPERS = {"time", "sudo", "doas", "exec", "nohup", "env", "xargs", "timeout", "command", "builtin", "nice", "ionice", "stdbuf", "setsid", "chrt", "taskset", "unbuffer", "watch", "flock"}
TAKES_VALUE = {"sudo": {"-u", "-g", "-h", "-p", "-C", "-U", "-D", "-r", "-t"}, "doas": {"-u", "-C"}, "env": {"-u", "-C", "-S"}, "xargs": {"-n", "-I", "-P", "-L", "-s", "-d", "-a", "-E"},
               "timeout": {"-s", "-k"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "stdbuf": {"-i", "-o", "-e"}, "watch": {"-n", "-d"}, "flock": {"-w", "-E"}}  # a wrapper's options that take their own value (sudo -u x, xargs -n 1, timeout -s KILL)

OPS = sorted([";;", "&&", "||", "|&", "&>>", "&>", ">&", "<&", ">>", ">|", "<<<", "<<", ";", "&", "|", "(", ")", "<", ">"], key=len, reverse=True)

def _ops(w):
    """shlex keeps runs of punctuation together: `)>`, `;>` and `&&>` come out as one word. Split such a run into the
    shell's own operators, longest first, so `(echo x)>f` and `true;>f` show their redirect (5.9.2 code review)."""
    if not w or w[0] == "\x01" or any(ch not in ";&|()<>" for ch in w) or w in OPS: return [w]
    out, i = [], 0
    while i < len(w):
        op = next((o for o in OPS if w.startswith(o, i)), w[i]); out.append(op); i += len(op)
    return out

def name_of(word):
    """A command's name as the shell runs it: its file name, without a Windows .exe (rm.exe is rm; 5.9.2 code review)."""
    n = os.path.basename(word.lstrip("\x01").replace("\\", "/"))
    return n[:-4] if n.lower().endswith(".exe") else n

def makes_nothing(cmd, word, cands):
    """True when `word` is the argument of a mkdir and already names a folder from every place the shell may be:
    mkdir then changes nothing and reads nothing (03 §5.57 item 48). The word is judged whole and as the OS resolves
    it, never split or tidied first: `mkdir -p src/new/..` makes src/new, and `mkdir src,.` makes a folder called
    'src,.' (5.9.2 code review)."""
    if name_of(cmd or "") != "mkdir" or not word or word.startswith("-"): return False
    w = os.path.expanduser(word.lstrip("\x01"))
    parts = re.split(r"[\\/]", w)
    if any(p_ == ".." and any(q not in ("..", ".", "") for q in parts[:k]) for k, p_ in enumerate(parts)): return False  # src/new/.. makes src/new first; Windows would call the path an existing folder by its words alone (CI on #55). A leading .. (../../reviews) is a plain way up
    return all(os.path.isdir(w if os.path.isabs(w) else os.path.join(str(c), w)) for c in cands)

def _commands(toks):
    """The first word of each simple command, looking through wrappers and their options (sudo -n kill, env -i kill,
    timeout 5 kill, xargs -n1 kill: 5.9.2 blind round 2)."""
    out, start, wrapped, skip = [], True, None, False
    for t in toks:
        if t in (";", "&&", "||", "|", "&", "(", ")", "|&", "\n", "{", "}", "!", "then", "do", "else"): start, wrapped, skip = True, None, False; continue
        if not start: continue
        w = name_of(t)
        if skip: skip = False; continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t): continue
        if wrapped and t.startswith("-") and t != "-":
            skip = t in TAKES_VALUE.get(wrapped, ()); continue
        if wrapped and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?|0x[0-9a-fA-F]+", t): continue  # timeout 5, chrt 10, taskset 0x3
        if w in WRAPPERS: wrapped = w; continue
        out.append(w); start = False; wrapped = None
    return out

def write_targets(cmd, start, kinds=False):
    """The files a shell command would write, as plain paths resolved from where it runs: redirect targets, and the
    file arguments of commands that write (tee, cp, mv, rm, touch, sed -i, dd of=...). A lead, not a parser: the
    write guard proper is the OS boundary; this only finds the plain cases, to cut on them (03 §5.57 item 44).
    A mkdir of a folder that already exists changes nothing, so it is no write (03 §5.57 item 48: the Qodo replay's
    #26, an honest reviewer cut for `mkdir -p` of the reviews folder). With kinds=True, each target comes back as
    (path, command name), so the caller can tell a folder being made from a file being written."""
    toks = _tokens(cmd)
    if toks is None: return []
    out, cwd, seg, assigned = [], str(start), [], {}
    NULLS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "con", os.devnull.lower()}  # checked before resolving: on Windows /dev/null resolves to C:\dev\null (CI on #52)
    def resolve(x):
        x = x.lstrip("\x01")
        x = re.sub(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", lambda m: cwd if m.group(1) == "PWD" else assigned.get(m.group(1), os.environ.get(m.group(1), m.group(0))), x)  # $HOME/.claude is Claude Code's folder, not one in the copy (5.9.2 blind round 2)
        x = os.path.expanduser(x)
        if x.lower() in NULLS: return None
        return os.path.normpath(x if os.path.isabs(x) else os.path.join(cwd, x))
    def flush(seg):
        nonlocal cwd
        if not seg: return
        name, args = name_of(seg[0]), [a.lstrip("\x01") for a in seg[1:]]
        if name == "cd" and args: cwd = resolve(args[0]); return
        if name in ("export", "declare", "local", "readonly"):
            for a in args:
                m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", a)
                if m: assigned[m.group(1)] = m.group(2)
            return
        tdir = next((args[k + 1] for k, a in enumerate(args) if a in ("-t", "--target-directory") and k + 1 < len(args)), None) or next((a.split("=", 1)[1] for a in args if a.startswith("--target-directory=")), None)
        if name in WRITERS_LAST and tdir: out.append((resolve(tdir), name)); return  # cp -t DIR src: DIR is where it writes (5.9.2 blind round 2)
        files = [a for k, a in enumerate(args) if not a.startswith("-") and not (k and args[k - 1] in ("-m", "--mode") and name in ("mkdir", "install"))]  # a mode is no file
        if name == "mkdir": out.extend((resolve(a), name) for a in files if not makes_nothing(name, a, [cwd]))
        elif name in WRITERS_ALL: out.extend((resolve(a), name) for a in files)
        elif name in WRITERS_LAST and len(files) >= 2: out.append((resolve(files[-1]), name))
        elif name in ("chmod", "chown") and len(files) >= 2: out.extend((resolve(a), name) for a in files[1:])
        elif name == "sed" and any(re.fullmatch(r"-[A-Za-z]*i.*|--in-place(?:=.*)?", a) for a in args) and len(files) >= 2: out.extend((resolve(a), name) for a in files[1:])
        elif name == "dd": out.extend((resolve(a[3:]), name) for a in args if a.startswith("of="))
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in (">&", "<&") and i + 1 < len(toks):
            if not re.fullmatch(r"\d+|-", toks[i + 1]): out.append((resolve(toks[i + 1]), t))  # >&file writes the file; >&1 only joins two streams
            i += 2; continue
        if t in (">", ">>", ">|", "&>", "&>>") and i + 1 < len(toks):
            if not re.fullmatch(r"&\d*|&-", toks[i + 1]): out.append((resolve(toks[i + 1]), t))  # > &2 duplicates a stream and writes no file; > 2 writes a file named 2
            i += 2; continue
        if t in (";", "&&", "||", "|", "&", "(", ")", "|&", "\n"): flush(seg); seg = []; i += 1; continue
        if seg == [] and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):  # VAR=x before a command is no argument; on its own it sets a variable later paths may use
            k_, v_ = t.split("=", 1); assigned[k_] = v_.lstrip("\x01")
        else: seg.append(t)
        i += 1
    flush(seg)
    out = [(p, k) for p, k in out if p]
    return out if kinds else [p for p, _ in out]

def bash_cut(cmd, root, me, payload):
    """Why a reviewer's shell command breaks the standard, or None: it stops or signals processes, or writes anywhere
    but its own folder (copy and notes) and the review it claimed, or writes an instructions file in its own folder.
    The same line as the Write tool's (5.9.0 blind round C5): a write to a temporary folder outside is cut too."""
    toks = _tokens(cmd) or []
    if any(c in ("kill", "pkill", "killall", "skill") for c in _commands(toks)): return "ran a command that stops or signals processes, which interferes with the run"
    fold = lambda x: os.path.normcase(os.path.realpath(str(x))).casefold()  # realpath: macOS's /var is /private/var, and a temp folder is often reached through it
    exact = lambda x: os.path.normcase(os.path.realpath(str(x)))  # case kept: on Linux .CRITIC is another folder
    mine_p = pathlib.Path(root) / ".critic" / "scratch" / me
    mine = fold(mine_p)
    homes = [fold(pathlib.Path.home() / ".claude"), fold(os.environ.get("CURMUDGEON_STATE_DIR") or pathlib.Path.home() / ".curmudgeon")]
    have = claimed_by(root, me)
    own_review = fold(pathlib.Path(root) / ".critic" / "reviews" / have) if have else None
    for t, how in write_targets(cmd, payload, kinds=True):
        f = fold(t)
        if f == mine or f.startswith(mine + os.sep):
            if OWN_SETTINGS_RX.search(os.path.relpath(os.path.realpath(t), os.path.realpath(str(mine_p)))): return f"wrote {t}, an instructions file Claude Code reads"  # relative: a project inside a .claude folder is not settings (blind round C3)
            continue
        if own_review and f == own_review: continue  # its own claimed review, by the shell too (blind round C4)
        if have and how == "mkdir" and exact(pathlib.Path(root) / ".critic" / "reviews" / have).startswith(exact(t) + os.sep): continue  # a folder on the way to its own review (03 §5.57 item 48)
        if any(f == h or f.startswith(h + os.sep) for h in homes): return f"wrote {t}, in Claude Code's or Curmudgeon's own folder"
        return f"wrote {t}, outside its copy, its notes and the review it claimed"
    return None
