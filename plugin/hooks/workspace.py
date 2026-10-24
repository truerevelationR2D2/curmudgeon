"""Private frozen workspaces for blind agents (5.0, ruling §5.29). Each reviewer and verifier gets its own copy of the
payload, so its cwd, its relative paths and its searches can only reach code: the project's other .critic/ files (the
other reviews, the scan, the tally) are not in the copy. That makes blindness structural instead of a contest between a
shell parser and a shell.

Layout, inside the agent's own scratch folder (Claude Code only lets an agent `cd` inside the session's working
folders, so the copy has to live in the project; the read guard already gives each agent its scratch folder alone):
    <project>/.critic/scratch/<agent_id>/payload          the copy; its Bash commands run from here
    <project>/.critic/scratch/<agent_id>/notes            its notes and probes (kept after it stops)
    <project>/.critic/scratch/<agent_id>/workspace.json   the record

What is copied: in a git project, the files git lists as tracked or untracked-but-not-ignored (so build output and
caches never eat the budget); elsewhere, every file except version-control folders, caches and the build folders the
scanner also skips. Never the top-level .critic, never a file over MAX_FILE. Dependency folders (node_modules, .venv,
venv) are linked, not copied, so tests can run. A link to somewhere in the project points at the same place in the
copy; a link outside the project points at its real target; a link into .critic or to the project itself is dropped.
Past MAX_TOTAL bytes or MAX_FILES files the copy stops and is marked partial; the agent is told, and can still Read the
project's own files (never its .critic). A link the system won't let us make (Windows without symlink rights) is
skipped and listed, never fatal.

Git: the copy is its own repository, a shared clone of the project's (objects shared, nothing copied), reset to the
project's HEAD with no remote. So `git log`, `blame` and `diff` work in the copy and show the working-tree edits, and
`git stash`, `reset` or `checkout` there can never touch the user's real work. When that can't be made, a `.git` file
pointing nowhere stops git from walking up into the project's repository, and git simply reports no repository.

The record is written before the copy starts (marked building), so a copy interrupted by the hook's time limit can
always be found and deleted; an unfinished copy is never used.

The threat this answers is an honest agent that anchors on what it happens to see, not a hostile one: a same-user
process can always build a path to any file the user can read. Hostile isolation needs an OS sandbox."""
import json, os, pathlib, re, shutil, subprocess, time

SKIP_ANYWHERE = {".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".cache"}
SKIP_BUILD = {"dist", "build", ".next", "coverage", "target", ".gradle", "out", ".turbo", ".parcel-cache"}  # non-git projects only
LINK_DIRS = {"node_modules", ".venv", "venv"}
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
MAX_FILES = 100_000
COPY_PART = re.compile(r"[\\/]\.critic[\\/]scratch[\\/][A-Za-z0-9_-]{1,64}[\\/]payload(?:[\\/].*)?$")

def clean_id(v): return re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:64]

def fold(p): return os.path.normcase(os.path.normpath(str(p))).casefold()

def within(p, top):
    p, top = fold(p), fold(top)
    return p == top or p.startswith(top.rstrip(os.sep) + os.sep)

def project_root(data):
    """The project a hook call is about. Claude Code passes the session's current folder as cwd, and after an agent's
    required `cd <copy> && ...` that is the copy itself, so a cwd inside a copy is mapped back to its project."""
    cwd = str(data.get("cwd") or os.getcwd())
    return pathlib.Path(COPY_PART.sub("", cwd) or cwd)

def home_for(root, agent_id):
    """This agent's folder, or None when it can't be made safely (a planted link on the way)."""
    root = pathlib.Path(root); c = root / ".critic"
    agent_id = clean_id(agent_id)
    if not agent_id or c.is_symlink() or (c / "scratch").is_symlink() or (c / "scratch" / agent_id).is_symlink(): return None
    return c / "scratch" / agent_id

def record(root, agent_id):
    """The raw record (ready or still building), or None. For cleanup and start times."""
    h = home_for(root, agent_id)
    if not h: return None
    p = h / "workspace.json"
    try:
        if p.is_symlink() or not p.is_file(): return None
        j = json.loads(p.read_text())
    except (OSError, ValueError): return None
    if not isinstance(j, dict) or fold(j.get("payload", "")) != fold(h.resolve() / "payload"): return None
    return j

def info(root, agent_id):
    """The workspace record for this agent when its copy is finished and present, else None."""
    j = record(root, agent_id)
    if not j or j.get("building") or not pathlib.Path(j["payload"]).is_dir() or pathlib.Path(j["payload"]).is_symlink(): return None
    return j

def _link_target(src, root):
    """Where a copied link should point: None to drop it, else the target to write."""
    try: real = pathlib.Path(src).resolve()
    except (OSError, RuntimeError, ValueError): return None
    rt = pathlib.Path(root).resolve()
    if within(real, rt / ".critic") or within(real, rt / ".git"): return None
    if within(rt, real): return None  # a link to the project itself or above it: a way back to .critic
    if within(real, rt):
        rel_from = os.path.dirname(os.path.relpath(src, rt))
        return os.path.relpath(os.path.relpath(real, rt), rel_from or ".")  # the same place, but in the copy
    return str(real)  # outside the project: its real target (a relative one would dangle from the copy's depth)

def _git(root, *a, timeout=60):
    try: return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError): return None

def _git_files(root):
    """Paths git lists as tracked, or untracked and not ignored; None when this isn't a git work tree."""
    r = _git(root, "rev-parse", "--show-toplevel")
    if not r or r.returncode or fold(r.stdout.strip()) != fold(pathlib.Path(root).resolve()): return None  # only when the project is the repo's top
    r = _git(root, "ls-files", "-z", "-co", "--exclude-standard")
    if not r or r.returncode: return None
    return sorted({x for x in r.stdout.split("\0") if x})

def _own_repo(root, payload):
    """Make the copy its own repository (see the module notes). Returns how: "clone", "none" or "stub"."""
    if not (pathlib.Path(root) / ".git").exists(): kind = "none"
    else:
        tmp = payload.parent / "gitclone"; shutil.rmtree(tmp, ignore_errors=True)
        r = _git(root, "clone", "-q", "--shared", "--no-checkout", str(root), str(tmp), timeout=90)
        head = _git(root, "rev-parse", "-q", "--verify", "HEAD")
        if r and not r.returncode and (tmp / ".git").is_dir():
            os.replace(tmp / ".git", payload / ".git"); shutil.rmtree(tmp, ignore_errors=True)
            _git(payload, "remote", "remove", "origin")
            if head and not head.returncode: _git(payload, "reset", "-q", head.stdout.strip())  # index = project HEAD; files untouched
            return "clone"
        shutil.rmtree(tmp, ignore_errors=True); kind = "stub"
    (payload / ".git").write_text("gitdir: .git-none-curmudgeon-copy\n")  # stops git walking up into the project's repository
    return kind

def make(root, agent_id):
    """Build the workspace and write its record. Returns the record, or None when no workspace could be made."""
    root = pathlib.Path(root).resolve(); h = home_for(root, agent_id)
    if not h: return None
    h.mkdir(parents=True, exist_ok=True); os.chmod(h, 0o700)
    payload = h / "payload"; notes = h / "notes"
    if payload.is_symlink(): payload.unlink()
    elif payload.exists(): shutil.rmtree(payload, ignore_errors=True)
    payload.mkdir(); notes.mkdir(exist_ok=True)
    rec = {"payload": str(payload.resolve()), "notes": str(notes.resolve()), "root": str(root), "made_at": time.time(), "building": True}
    (h / "workspace.json").write_text(json.dumps(rec, indent=1))
    st = {"files": 0, "bytes": 0, "partial": False, "skipped_large": [], "links_skipped": []}

    def link(target, dst, rel):
        try: os.symlink(target, dst, target_is_directory=os.path.isdir(target) if os.path.isabs(str(target)) else os.path.isdir(os.path.join(os.path.dirname(dst), target)))
        except OSError: st["links_skipped"].append(rel)

    def put(rel):
        """Copy one project file (or link) at rel. False once the budget is spent."""
        src = root / rel; dst = payload / rel
        if os.path.islink(src):
            t = _link_target(src, root)
            if t is not None: dst.parent.mkdir(parents=True, exist_ok=True); link(t, dst, rel)
            return True
        try: size = os.path.getsize(src)
        except OSError: return True
        if not os.path.isfile(src): return True
        if size > MAX_FILE: st["skipped_large"].append(rel); return True
        if st["bytes"] + size > MAX_TOTAL or st["files"] >= MAX_FILES: st["partial"] = True; return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        try: shutil.copy2(src, dst)
        except OSError: st["skipped_large"].append(rel); return True
        st["bytes"] += size; st["files"] += 1; return True

    listed = _git_files(root)
    if listed is not None:
        for rel in listed:
            parts = pathlib.PurePosixPath(rel).parts
            if not parts or parts[0] == ".critic" or any(x in SKIP_ANYWHERE or x in LINK_DIRS for x in parts[:-1]): continue
            if not put(rel): break
        for top, dirs, _ in os.walk(root):  # dependency folders git ignores: linked so tests run (four levels deep at most)
            relt = os.path.relpath(top, root)
            depth = 0 if relt == "." else relt.count(os.sep) + 1
            for x in list(dirs):
                if x in LINK_DIRS and not os.path.islink(os.path.join(top, x)):
                    dst = payload / relt / x
                    if not os.path.lexists(dst): dst.parent.mkdir(parents=True, exist_ok=True); link(os.path.join(top, x), dst, os.path.normpath(os.path.join(relt, x)))
            dirs[:] = [x for x in dirs if depth < 3 and x not in LINK_DIRS and x not in SKIP_ANYWHERE and not (relt == "." and x == ".critic") and not os.path.islink(os.path.join(top, x))]
    else:
        stop = False
        for top, dirs, names in os.walk(root):
            relt = os.path.relpath(top, root); keep = []
            for x in sorted(dirs):
                src = os.path.join(top, x); rel = os.path.normpath(os.path.join(relt, x))
                if (relt == "." and x == ".critic") or x in SKIP_ANYWHERE or x in SKIP_BUILD: continue
                if x in LINK_DIRS and not os.path.islink(src): (payload / relt).mkdir(parents=True, exist_ok=True); link(src, payload / rel, rel); continue
                if os.path.islink(src): put(rel); continue
                (payload / rel).mkdir(parents=True, exist_ok=True); keep.append(x)
            dirs[:] = keep
            for n in sorted(names):
                if not put(os.path.normpath(os.path.join(relt, n))): stop = True; break
            if stop: break
    try: rec["git"] = _own_repo(root, payload)
    except OSError: rec["git"] = "stub-failed"
    st["skipped_large"] = st["skipped_large"][:200]; st["links_skipped"] = st["links_skipped"][:200]
    rec.update(st); rec.pop("building", None)
    (h / "workspace.json").write_text(json.dumps(rec, indent=1))
    return rec

def remove(root, agent_id):
    """At the agent's stop: delete the copy (finished or not), keep the notes and the record."""
    rec = record(root, agent_id)
    if not rec: return False
    p = pathlib.Path(rec["payload"])
    if p.is_symlink(): p.unlink()
    else: shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(p.parent / "gitclone", ignore_errors=True)
    return True
