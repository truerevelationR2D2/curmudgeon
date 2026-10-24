#!/usr/bin/env python3
"""PreToolUse: makes blindness a control, not only an instruction. When a Curmudgeon reviewer, verifier or dedup agent
tries to read something in the project's .critic/ folder that its role must not see, the call is denied:

  reviewer  everything in .critic/ except the rule files, the change map and its own scratch folder
  verifier  the same, except that it may also read its verify packets, the scan and the ledger's recorded decisions
  dedup     the same as a reviewer, except dedup-candidates.json and groups.json, which are its job

Decisions are made on resolved paths (links followed), compared without regard to case (macOS and Windows disks
usually ignore it), and anchored to <project>/.critic only: a fixture's .critic folder elsewhere in the payload is
ordinary code. Read and NotebookRead are checked by their file. Grep and Glob are checked by the folder they search
(and a Glob pattern naming .critic by what it really matches): inside .critic the role's rules apply, and a Grep rooted
above .critic must start at the project root with glob "!.critic", because a search there would read every review.
Grep's search pattern is text, never a path. Bash is judged by the real paths a command can touch (see bash_problem):
quoted scripts, wildcards and links are expanded and resolved, and recursive searches and copies are judged by their
targets. That is best effort: a shell is a language, and an agent set on evasion can build a path no check sees.

It also refuses a fork (an Agent call with subagent_type "fork") while a review run is active: a fork inherits the
whole conversation, so it can't be blind. A run counts as active from `start` until the teardown is written, for at
most 12 hours. The main conversation and every other agent are never limited. A crash in this hook allows the call
(a broken guard must not stop the user's work); the merge script's own checks still apply."""
import json, os, pathlib, re, shlex, sys, time

ALLOW = {"reviewer": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore"},
         "verifier": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "verify", "scan", "ledger.md"},
         "dedup": {"rules", "rules.md", ".gitignore", "dedup-candidates.json", "groups.json"}}
SEARCHERS = {"grep", "egrep", "fgrep", "find", "ack", "rg", "ag", "cp", "rsync", "tar", "zip", "xargs"}
EXCLUDES = re.compile(r"(?i)--exclude-dir[= ]\.critic\b|(?:-g|--glob|--ignore(?:-dir)?)[= ]!?[^\s]*\.critic|-not\s+-path\s+[^\s]*\.critic|"
                      r"-path\s+[^\s]*\.critic\s+-prune|--exclude[= ][^\s]*\.critic")
def role_of(agent_type):
    m = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup)", agent_type or "")
    return m.group(1) if m else None

def fold(p): return os.path.normcase(os.path.normpath(str(p))).casefold()

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

def above(base, critic):
    """True when a search rooted at base would reach critic (base is critic's folder or one above it)."""
    try: return pathlib.Path(fold(critic)).is_relative_to(pathlib.Path(fold(base))) and fold(base) != fold(critic)
    except ValueError: return False

def resolve(v, root):
    p = pathlib.Path(os.path.expanduser(v))
    if not p.is_absolute(): p = root / p
    try: return p.resolve()
    except (OSError, RuntimeError): return p

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

VALUE_OPTS = {"-A", "-B", "-C", "-m", "-e", "-f", "-g", "-t", "-T", "-d", "-D", "-M", "-j", "--include", "--exclude", "--glob", "--iglob", "--type",
              "--type-not", "--max-count", "--context", "--after-context", "--before-context", "--regexp", "--file", "--max-depth", "--threads",
              "--color", "--colors", "--sort", "--sortr", "--max-filesize", "--encoding", "--engine", "--replace"}
def without_patterns(text):
    """The command with every search tool's pattern argument (and git's --grep=) removed: a pattern is text to look for,
    not a path to read, so searching for the words ".critic/reviews" is never mistaken for reading that folder."""
    text = re.sub(r"(?i)--(?:grep|regexp|author|committer)=\S+", " ", text)
    out = []
    for part in re.split(r"(\|\||&&|[;|&\n]|\$\(|`|\(|\))", text):
        words = part.split()
        lead = [w for w in words if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)]
        body = words[len(lead):]
        if body and (os.path.basename(body[0]) in ("grep", "egrep", "fgrep", "rg", "ag", "ack") or body[:2] == ["git", "grep"]):
            k = 2 if body[0] == "git" else 1; drop = set(); explicit = False
            while k < len(body):
                w = body[k]
                if w in ("-e", "--regexp", "-f", "--file"): drop.add(k + 1); explicit = True; k += 2; continue
                if w in VALUE_OPTS: k += 2; continue
                if w.startswith("-"): k += 1; continue
                if not explicit: drop.add(k)
                break
            body = [w for j, w in enumerate(body) if j not in drop]
        out.append(" ".join(lead + body) if words else part)
    return " ".join(out)

def bash_problem(cmd, root, critic, role, me):
    """Judge a shell command by the real paths it can touch, not by its spelling. Quotes and backslashes are removed and
    the whole command (the inside of sh -c and python -c strings included) is split into path-like pieces. Any piece
    that names critic, exists on disk, or holds a wildcard is expanded the way the shell would (glob), followed through
    links and judged like a Read. A recursive search or copy (grep -r, find, xargs, ack, rg or ag with hidden files on,
    cp -r, rsync, tar, zip) is judged by its targets, one simple command at a time: one rooted at or above .critic must
    exclude it in that same command. A shell is a language, so this stays best effort against deliberate evasion."""
    import glob as _glob
    flat = re.sub(r"\\(.)", r"\1", cmd).replace("'", "").replace('"', "")  # .crit""ic is .critic to the shell
    pieces = re.findall(r"[^\s`;&|<>()=,:$]+", without_patterns(EXCLUDES.sub(" ", flat)))  # exclusion flags and search patterns name .critic without reading it
    for piece in pieces:
        names_critic = "critic" in piece.casefold()
        wild = any(ch in piece for ch in "*?[")
        cand = root / os.path.expanduser(piece) if not os.path.isabs(os.path.expanduser(piece)) else pathlib.Path(os.path.expanduser(piece))
        if not (names_critic or wild or os.path.lexists(cand)): continue
        if wild:
            hits = _glob.glob(str(cand), recursive=True)
            if names_critic and not hits and fold(str(cand)).startswith(fold(critic)): return f"a wildcard into .critic ({piece})"
        else: hits = [str(cand)]
        for h in hits[:2000]:
            why = judge(resolve(h, root), critic, role, me)
            if why: return why
    simple = re.split(r"\|\||&&|[;|&\n]|\$\(|`|\(|\)", flat)
    for part in simple:
        words = [w for w in part.split() if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)]
        if not words: continue
        prog = os.path.basename(words[0])
        if prog not in SEARCHERS: continue
        if prog in ("rg", "ag") and not re.search(r"(?:^|\s)(?:--hidden|--no-ignore|-u{1,3}|--unrestricted|-\.)(?:\s|$)", part): continue  # they skip hidden folders by default
        if prog in ("grep", "egrep", "fgrep") and not re.search(r"(?:^|\s)(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive|--dereference-recursive)(?:\s|$)", part): continue
        if prog == "cp" and not re.search(r"(?:^|\s)-[A-Za-z]*[rRa]", part): continue
        if EXCLUDES.search(part): continue
        if prog == "xargs":
            continue  # xargs reads names from its input; the command producing them (find, ls -R) is judged on its own
        targets = [w for w in words[1:] if not w.startswith("-")]
        if prog in ("grep", "egrep", "fgrep", "ack") and targets: targets = targets[1:]  # the first non-option word is the pattern
        if prog == "find": targets = [w for w in words[1:] if not w.startswith(("-", "!", "("))][:1] or ["."]
        if not targets: targets = ["."]
        for t in targets:
            if above(resolve(t, root), critic) or judge(resolve(t, root), critic, role, me):
                return f"a recursive {prog} that would also read .critic/ (exclude it in the same command: grep --exclude-dir=.critic, find -not -path '*/.critic/*', rg -g '!.critic', or name the payload folders)"
    if re.search(r"(?i)(?:^|[\s;&|(])(?:cd|pushd)\s+\S*critic", flat): return "changing into .critic/"
    return None

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    tool, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    root = pathlib.Path(data.get("cwd") or os.getcwd())
    if tool in ("Agent", "Task"):
        if str(ti.get("subagent_type") or "").lower() == "fork" and run_active(root):
            return deny("Curmudgeon: no forks during a review run. A fork inherits the whole conversation, so it can't review blind. Start the named agent (curmudgeon:curmudgeon-reviewer, -verifier, -dedup or -detector) instead.")
        return 0
    role = role_of(data.get("agent_type"))
    if not role: return 0
    me = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("agent_id") or ""))[:64]  # the same cleaning scratch_dir.py uses
    try: critic = (root / ".critic").resolve()
    except OSError: critic = root / ".critic"
    why = None
    if tool in ("Read", "NotebookRead"):
        v = ti.get("file_path") or ti.get("notebook_path")
        if isinstance(v, str) and v: why = judge(resolve(v, root), critic, role, me)
    elif tool in ("Grep", "Glob"):
        base = resolve(ti.get("path") or str(root), root)
        why = judge(base, critic, role, me)
        if not why and tool == "Glob" and "critic" in str(ti.get("pattern") or "").casefold():  # expand it for real and judge what it matches
            import glob as _glob
            for h in _glob.glob(os.path.join(str(base), str(ti["pattern"])), recursive=True)[:2000]:
                why = judge(resolve(h, root), critic, role, me)
                if why: break
        if not why and tool == "Grep" and above(base, critic):
            g = str(ti.get("glob") or "").strip()
            if fold(base) != fold(root) or not re.fullmatch(r"!(\*\*/)?\.critic(/\*{0,2})?", g, re.I):
                why = ".critic (a search from a folder above it); search from the project root with glob \"!.critic\", or a narrower folder"
    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str) and cmd: why = bash_problem(cmd, root, critic, role, me)
    if why: return deny(f"Curmudgeon blindness: a {role} may not read {why}. Review only what your brief gives you and your own scratch folder.")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
