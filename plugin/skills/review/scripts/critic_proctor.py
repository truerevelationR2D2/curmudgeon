#!/usr/bin/env python3
"""The proctor's request command (03 §5.57 item 35): a reviewer that needs something outside its private copy asks
here, from its copy, instead of reaching for it. The proctor hands it over without exposing anyone's work.

usage (from the reviewer's copy: cd <workspace> && python3 <this file> ask ...):
  critic_proctor.py ask read PATH          print a file (at most 200 KB)
  critic_proctor.py ask list FOLDER        list a folder
  critic_proctor.py ask git log|diff|ls-files [OPTIONS] [REV...] [-- PATH...]
  critic_proctor.py ask git show [OPTIONS] [REV...] [-- PATH...]   or   ask git show REV:PATH
  critic_proctor.py ask git blame [OPTIONS] [REV] -- PATH
                                           read-only history of the real project (a copy may have none), with
                                           no author, email or date (the copy and the brief hide who wrote it);
                                           the project's .critic/ is always left out

Refused, whatever the spelling or link: any .critic folder, Curmudgeon's own records (~/.curmudgeon), Claude's own
folder (~/.claude: agents' transcripts), other processes (/proc), and git options that write files or run programs.
An answer holding any of Curmudgeon's run marks (a brief, the scan, a tally) is withheld. Every request is listed in
.critic/proctor/requests.jsonl, which the lead and the owner can read and reviewers can't. Nothing is changed."""
import json, os, pathlib, re, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import safegit

ROOT = pathlib.Path(__import__("projroot").project_of(os.getcwd())).resolve(); D = ROOT / ".critic"  # never CRITIC_ROOT: the reviewer it polices could set that (5.5.0 blind round)
MAX = 200 * 1024
GIT_OK = {"log", "show", "blame", "diff", "ls-files"}
GIT_BAD = re.compile(r"^(?:--output|-o$|--ext-diff|--textconv|--exec|--upload-pack|--receive-pack|-c$|-C$|--git-dir|--work-tree|--config|--open-files-in-pager|-O|--no-index|--author|--committer|--mailmap|--use-mailmap)", re.I)  # --author and --committer would let a search find who wrote the code (5.6.0 re-review C1)
NO_WHO = "--format=%h %s"  # history without authors or dates, which the private copy and the brief keep from reviewers (5.6.0 re-review C1); git uses the last --format given, so this one wins
VALUE_OPTS = {"--grep", "-S", "-G", "--since", "--until", "--after", "--before", "-n", "--max-count", "--skip", "-L", "--format", "--pretty", "--diff-filter", "--stat", "-U", "--unified", "--find-renames", "-M", "--relative"}  # options whose value is the next argument (5.6.0 re-review C9)

def log(kind, what, answer):
    try:
        d = D / "proctor"
        if D.is_symlink() or d.is_symlink() or not D.is_dir(): return
        d.mkdir(exist_ok=True); f = d / "requests.jsonl"
        if f.is_symlink(): return
        with open(f, "a", encoding="utf-8") as fh: fh.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "what": what[:300], "answer": answer}) + "\n")
    except OSError: pass

def bases():
    """[(folder, why)] never handed over: the owner's records and Claude's own folder, both where the environment says
    and where they are by default under the account's real home (from the password database, not HOME), so a reviewer
    that sets HOME, CLAUDE_CONFIG_DIR or CURMUDGEON_STATE_DIR on its own command line moves nothing (5.6.0 re-review C10)."""
    homes = {pathlib.Path.home()}
    try:
        import pwd; homes.add(pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir))
    except (ImportError, KeyError, AttributeError, OSError): pass
    if os.environ.get("USERPROFILE"): homes.add(pathlib.Path(os.environ["USERPROFILE"]))  # Windows has no password database
    out = []
    for h in homes:
        out += [(h / ".curmudgeon", "Curmudgeon's own records"), (h / ".claude", "Claude's own folder (agents' transcripts)")]
    for v, why in (("CURMUDGEON_STATE_DIR", "Curmudgeon's own records"), ("CLAUDE_CONFIG_DIR", "Claude's own folder (agents' transcripts)")):
        if os.environ.get(v): out.append((pathlib.Path(os.environ[v]), why))
    res = []
    for b, why in out:
        try: res.append((pathlib.Path(os.path.realpath(b)), why))
        except (OSError, ValueError): pass
    return res

def refused_path(raw):
    """Why this path is never handed over, or None."""
    try: real = pathlib.Path(os.path.realpath(os.path.expanduser(raw)))
    except (OSError, ValueError): return "an unreadable path"
    parts = [x.lower() for x in real.parts]
    if ".critic" in parts or ".critic" in [x.lower() for x in pathlib.Path(raw).parts]: return "a .critic folder (the run's own records)"
    for base, why in bases():
        if real == base or base in real.parents: return why
    if parts[:2] == [real.anchor.lower(), "proc"] or str(real).replace("\\", "/").startswith("/proc/"): return "another process's details (/proc)"
    return None

def marked(text):
    """True when text holds any of Curmudgeon's run marks; None when the marks can't be read (Claude Code's sandbox
    hides .critic/ from a reviewer's command, or no run has written any), so the check fails closed (5.6.0 blind round)."""
    f = D / "proctor" / "marks.json"
    try: m = json.loads(f.read_text(encoding="utf-8")).get("marks") if f.is_file() and not f.is_symlink() else None
    except (OSError, ValueError, AttributeError): m = None
    return None if not isinstance(m, dict) else any(k in text for k in m)

def answer(kind, what, text):
    seen = marked(text)
    if seen is None and kind != "git":  # git leaves .critic/ out by itself; a file or a listing can't be checked
        log(kind, what, "refused: the run marks can't be read here"); print("proctor: refused: the run marks can't be read from here (Claude Code's sandbox hides .critic/, or no run is active), so a file can't be checked; read it with the Read tool, whose reads the guard checks", file=sys.stderr); return 2
    if seen:
        log(kind, what, "withheld: it holds a run mark"); print("proctor: withheld: the answer holds another part of this review's work", file=sys.stderr); return 3
    log(kind, what, f"given ({len(text)} characters)")
    sys.stdout.write(text if len(text) <= MAX else text[:MAX] + f"\n[proctor: cut at {MAX // 1024} KB]\n"); return 0

def main(a):
    if len(a) < 3 or a[0] != "ask" or a[1] not in ("read", "list", "git"): print(__doc__); return 2
    kind, rest = a[1], a[2:]
    if kind in ("read", "list"):
        why = refused_path(rest[0])
        if why: log(kind, rest[0], f"refused: {why}"); print(f"proctor: refused: {why}", file=sys.stderr); return 2
        p = pathlib.Path(os.path.expanduser(rest[0]))
        try:
            if kind == "list":
                if not p.is_dir(): print("proctor: not a folder", file=sys.stderr); return 2
                return answer(kind, rest[0], "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())) + "\n")
            if not p.is_file(): print("proctor: not a file", file=sys.stderr); return 2
            with open(p, "rb") as fh: data = fh.read(MAX + 1)
            return answer(kind, rest[0], data.decode("utf-8", errors="replace"))
        except OSError as e: print(f"proctor: can't read it ({e.strerror})", file=sys.stderr); return 2
    sub, args = rest[0], rest[1:]
    opts, paths = (args[:args.index("--")], args[args.index("--") + 1:]) if "--" in args else (args, [])
    refuse = lambda why: (log("git", " ".join(rest), f"refused: {why}"), print(f"proctor: refused: {why}", file=sys.stderr), 2)[2]
    if sub not in GIT_OK: return refuse(f"git {sub} isn't a read-only history command")
    bad = [x for x in args if ".critic" in x.lower() or GIT_BAD.match(x)] + [x for x in paths if x.startswith((":", "-")) or refused_path(str(ROOT / x))]
    if bad: return refuse(f"{bad[0]} (it names .critic, writes a file, runs a program, sets its own paths, or uses pathspec magic)")
    blobs = [x for i, x in enumerate(opts) if re.match(r"^[^-][^:]*:", x) and not (i and opts[i - 1] in VALUE_OPTS)]  # REV:PATH names one file; an option's value (--grep "fix: x") is not one (5.6.0 re-review C9)
    if blobs and (sub != "show" or len(opts) != 1 or paths or not blobs[0].split(":", 1)[1]):
        return refuse("REV:PATH works only alone, as git show REV:PATH (5.5.0 blind round: beside other revisions it lifted the .critic exclusion)")
    if sub == "blame":
        if len(paths) != 1: return refuse("git blame needs exactly one file after --")
        odd = [x for x in opts if x.startswith("-") and not re.fullmatch(r"-L\d*,?[+-]?\d*|-[wsnlfMC]+|--show-name|--show-number", x)]
        if odd: return refuse(f"{odd[0]} (git blame takes only -L, -w, -s, -n, -l, -f, -M and -C here: --contents would print any file, and the porcelain, email and time forms name who wrote it)")  # 5.5.0 blind round 2; 5.6.0 re-review C1
        cmd = ["blame", "-s", *opts, "--", paths[0]]  # -s: no author and no date
    elif blobs: cmd = ["show", blobs[0]]
    elif sub in ("log", "show"): cmd = [sub, *opts, NO_WHO, "--", *(paths or ["."]), ":(exclude,icase).critic", ":(exclude,icase).critic/**"]
    else: cmd = [sub, *opts, "--", *(paths or ["."]), ":(exclude,icase).critic", ":(exclude,icase).critic/**"]
    r = safegit.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if r.returncode != 0: log("git", " ".join(rest), f"git failed ({r.returncode})"); print(r.stderr[-2000:], file=sys.stderr); return r.returncode
    return answer("git", " ".join(rest), r.stdout)

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
