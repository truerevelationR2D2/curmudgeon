#!/usr/bin/env python3
"""PreToolUse: makes blindness a control, not only an instruction. When a Curmudgeon reviewer, verifier or dedup agent
tries to read something in the project's .critic/ folder that its role must not see, the call is denied:

  reviewer  everything in .critic/ except the rule files, the change map and its own scratch folder
  verifier  the same, except that it may also read its verify packets, the scan and the ledger's recorded decisions
  dedup     the same as a reviewer, except dedup-candidates.json and groups.json, which are its job

Decisions are made on resolved paths (links followed), compared without regard to case (macOS and Windows disks
usually ignore it), and anchored to <project>/.critic only: a fixture's .critic folder elsewhere in the payload is
ordinary code. Read and NotebookRead are checked by their file. Grep and Glob are checked by the folder they search:
inside .critic the role's rules apply, and a Grep rooted at or above .critic is denied unless it excludes it (glob
"!.critic/**"), because a search there would read every review. Grep's search pattern is text, never a path. Bash is
checked token by token: any path naming .critic is resolved and judged like a Read, wildcards and `..` inside .critic
are refused, and recursive content searches (grep -r, ack, find -exec, or rg/ag with hidden files on) must exclude
.critic. That is best effort: a shell is a language, and an agent set on evasion can build a path no pattern sees.

It also refuses a fork (an Agent call with subagent_type "fork") while a review run is active: a fork inherits the
whole conversation, so it can't be blind. A run counts as active from `start` until the teardown is written, for at
most 12 hours. The main conversation and every other agent are never limited. A crash in this hook allows the call
(a broken guard must not stop the user's work); the merge script's own checks still apply."""
import json, os, pathlib, re, shlex, sys, time

ALLOW = {"reviewer": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore"},
         "verifier": {"rules", "rules.md", "change-map.md", "change-map.json", "risk-map.md", ".gitignore", "verify", "scan", "ledger.md"},
         "dedup": {"rules", "rules.md", ".gitignore", "dedup-candidates.json", "groups.json"}}
SEARCH_CMDS = re.compile(r"(?i)(?:^|[\s;&|(`])(?:grep|egrep|fgrep)\b[^;&|]*\s-(?:[a-z]*[rR][a-z]*)\b|(?:^|[\s;&|(`])grep\b[^;&|]*--recursive|"
                         r"(?:^|[\s;&|(`])ack\b|(?:^|[\s;&|(`])find\b[^;&|]*-(?:exec|execdir|ok|okdir)\b|"
                         r"(?:^|[\s;&|(`])(?:rg|ag)\b[^;&|]*(?:--hidden|--no-ignore|-u{1,3}\b|--unrestricted)")
EXCLUDES = re.compile(r"(?i)--exclude-dir[= ]['\"]?\.critic['\"]?|(?:-g|--glob|--ignore(?:-dir)?)[= ]['\"]?!?[^\s'\"]*\.critic[^\s'\"]*['\"]?|"
                      r"-not\s+-path\s+['\"]?[^\s'\"]*\.critic[^\s'\"]*['\"]?|-path\s+['\"]?[^\s'\"]*\.critic['\"]?\s+-prune")

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

def bash_problem(cmd, root, critic, role, me):
    stripped = EXCLUDES.sub(" ", cmd)
    if SEARCH_CMDS.search(stripped) and not EXCLUDES.search(cmd):
        return ("a recursive search that would also read .critic/; exclude it (grep --exclude-dir=.critic, find -not -path '*/.critic/*', "
                "rg -g '!.critic/**') or search the payload folders by name")
    if ".critic" not in stripped.casefold(): return None
    try:
        lx = shlex.shlex(stripped, posix=True, punctuation_chars=True); lx.whitespace_split = True; raw = list(lx)
    except ValueError: return "a command naming .critic that can't be parsed"
    tokens, seg, i = [], [], 0
    for tok in raw + [";"]:  # per simple command: a search tool's pattern argument is text, not a path
        if tok and all(ch in ";&|()<>" for ch in tok):
            if seg:
                words = [w for w in seg if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)]  # leading VAR=value
                if words and os.path.basename(words[0]) in ("grep", "egrep", "fgrep", "rg", "ag", "ack") or words[:2] == ["git", "grep"]:
                    rest = words[2:] if words[0] == "git" else words[1:]; skip = None; j = 0
                    while j < len(rest):
                        w = rest[j]
                        if w in ("-e", "--regexp") and j + 1 < len(rest): skip = j + 1; break
                        if not w.startswith("-"): skip = j; break
                        j += 1
                    seg = [w for k, w in enumerate(words) if not (skip is not None and w is rest[skip] and k == len(words) - len(rest) + skip)]
                tokens += seg
            seg = []
        else: seg.append(tok)
    for tok in tokens:
        for piece in re.split(r"[;&|<>()`=]+", tok):
            if ".critic" not in piece.casefold(): continue
            if re.search(r"[*?\[\]{}$]", piece) or ".." in pathlib.PurePath(piece).parts: return f"a wildcard, variable or .. in a .critic path ({piece})"
            p = resolve(piece, root)
            hit = judge(p, critic, role, me)
            if hit: return hit
    if re.search(r"(?i)(?:^|[\s;&|(])(?:cd|pushd)\s+['\"]?[^\s'\"]*\.critic", stripped): return "changing into .critic/"
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
        if not why and tool == "Glob" and ".critic" in str(ti.get("pattern") or "").casefold():
            why = judge(resolve(os.path.join(str(base), str(ti["pattern"]).split("*")[0] or "."), root), critic, role, me) or \
                  (".critic (a pattern into it)" if any(ch in str(ti["pattern"]) for ch in "*?[") else None)
        b, c = fold(base), fold(critic)
        if not why and tool == "Grep" and c.startswith(b + os.sep) and not re.fullmatch(r"!\*{0,2}/?\.critic(/\*{0,2})?", str(ti.get("glob") or "").strip(), re.I):
            why = ".critic (a search from a folder above it); add glob \"!.critic/**\" or search a narrower folder"
    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str) and cmd: why = bash_problem(cmd, root, critic, role, me)
    if why: return deny(f"Curmudgeon blindness: a {role} may not read {why}. Review only what your brief gives you and your own scratch folder.")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
