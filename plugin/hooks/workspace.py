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
venv) are linked, not copied, so tests can run, unless a link inside one leads outside the project (then it is left out
and the agent is told; a virtual environment's own interpreter link is allowed). A link to somewhere in the project
points at the same place in the copy; a link outside the project becomes a short note saying so, never a copy or a
link (a project can point at ~/.ssh); a link into .critic or to the project itself is dropped. A submodule or nested repository is copied as files, without its history.
Past MAX_TOTAL bytes or MAX_FILES files the copy stops and is marked partial; the agent is told, and can still Read the
project's own files (never its .critic). A link the system won't let us make (Windows without symlink rights) is
skipped and listed, never fatal.

Git: the copy is its own repository with one anonymous commit holding the project's HEAD tree (no history, no
authors, no messages: 03 §5.56 item 10; only that tree's objects are copied in, with no link to the project's object store). So `git diff`
and `git status` work in the copy and show the working-tree edits, and
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
ESCAPE_SCAN_MAX = 300000  # entries walked in one dependency folder before it counts as too large to check

def escaping_link(folder, root):
    """The first link inside a dependency folder that leads outside the project (None when there is none). The folder is
    linked whole into the copy, so such a link would let the reviewer read through it (a node_modules entry pointing at
    ~/.aws, say). A virtual environment's own interpreter link (bin/python3 -> /usr/bin/python3.12) is allowed."""
    rt = pathlib.Path(root).resolve(); stack = [folder]; seen = 0
    while stack:
        try: it = list(os.scandir(stack.pop()))
        except OSError: continue
        for e in it:
            seen += 1
            if seen > ESCAPE_SCAN_MAX: return f"{os.path.relpath(folder, root)} (too large to check)"
            if e.is_symlink():
                try: real = pathlib.Path(e.path).resolve()
                except (OSError, RuntimeError): continue
                if within(real, rt): continue
                if os.path.basename(os.path.dirname(e.path)) in ("bin", "Scripts") and re.match(r"^(python|pypy)[\d.]*(\.exe)?$", real.name, re.I): continue
                return os.path.relpath(e.path, root)
            elif e.is_dir(follow_symlinks=False): stack.append(e.path)
    return None
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
MAX_FILES = 100_000
COPY_PART = re.compile(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$")  # anywhere in the scratch area (a copy, its notes, the agent folder) belongs to the project above it

def clean_id(v): return re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:64]

def fold(p): return os.path.normcase(os.path.normpath(str(p))).casefold()

def within(p, top):
    p, top = fold(p), fold(top)
    return p == top or p.startswith(top.rstrip(os.sep) + os.sep)

def project_root(data):
    """The project a hook call is about. Claude Code passes the session's current folder as cwd, and after an agent's
    required `cd <copy> && ...` that is the copy itself (or its notes folder), so any cwd in .critic/scratch is mapped
    back to the project that holds it."""
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

OUTSIDE_STUB = ("Curmudgeon: in the project this is a link to something outside the project. Its content was not copied into "
                "this workspace, because a project can link to private files such as keys. Review it as an outside dependency.\n")

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
    """Paths git tracks, then untracked-but-not-ignored ones outside build folders; None when this isn't a git work
    tree. Tracked files come first, so build output that nobody ignored can never crowd the source out of the budget."""
    r = _git(root, "rev-parse", "--show-toplevel")
    if not r or r.returncode or fold(r.stdout.strip()) != fold(pathlib.Path(root).resolve()): return None  # only when the project is the repo's top
    t = _git(root, "ls-files", "-z", "-c")
    u = _git(root, "ls-files", "-z", "-o", "--exclude-standard")
    if not t or t.returncode or not u or u.returncode: return None
    tracked = sorted({x.rstrip("/") for x in t.stdout.split("\0") if x})
    seen = set(tracked)
    extra = sorted({x.rstrip("/") for x in u.stdout.split("\0") if x and x.rstrip("/") not in seen and not any(part in SKIP_BUILD for part in pathlib.PurePosixPath(x).parts[:-1])})
    return tracked + extra

def _own_repo(root, payload):
    """Make the copy its own repository with no history (03 §5.56 item 10): one commit holding the project's HEAD tree
    without .critic/, by an anonymous author with a plain message, so `git diff` shows the working-tree edits but
    `git log`, `blame` and even `git fsck` show no author, email, commit message, co-author line or older version. Only
    the objects of that one tree are copied in (no link to the project's object store, which holds its whole history).
    Returns how: "base", "empty" (a repository with no commits yet), "none" (not a git project) or "stub"."""
    if not (pathlib.Path(root) / ".git").exists(): kind = "none"
    else:
        kind = "stub"
        head = _git(root, "rev-parse", "-q", "--verify", "HEAD^{commit}")
        r = _git(payload, "init", "-q")
        if r and not r.returncode and (payload / ".git").is_dir():
            wt = _git(root, "rev-parse", "--show-toplevel")
            own = bool(wt and not wt.returncode and fold(wt.stdout.strip()) == fold(pathlib.Path(root).resolve()))  # a broken .git makes git walk up to a parent repository: never copy that one's tree
            if head is not None and head.returncode and own: return "empty"  # a real repository with no commit yet
            if not own or head is None or head.returncode: head = None  # no commit to copy: git status shows every file as new, which is what it is
            try:
                if head is None: raise ValueError("no repository")
                ls = subprocess.run(["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], cwd=root, capture_output=True, timeout=120)
                entries = []
                for rec in ls.stdout.split(b"\0") if ls.returncode == 0 else []:
                    if not rec: continue
                    meta, path = rec.split(b"\t", 1)
                    if path == b".critic" or path.startswith(b".critic/"): continue  # Curmudgeon's own records never reach a reviewer
                    mode, typ, sha = meta.split(b" ")
                    entries.append((mode, typ, sha, path))
                if ls.returncode == 0:
                    blobs = b"\n".join(sha for _, typ, sha, _ in entries if typ == b"blob") + b"\n"
                    pk = subprocess.run(["git", "pack-objects", "--stdout", "-q"], cwd=root, input=blobs, capture_output=True, timeout=600)
                    ip = subprocess.run(["git", "index-pack", "--stdin"], cwd=payload, input=pk.stdout, capture_output=True, timeout=600) if pk.returncode == 0 else None
                    info = b"".join(mode + b" " + sha + b"\t" + path + b"\0" for mode, typ, sha, path in entries)
                    ui = subprocess.run(["git", "update-index", "-z", "--index-info"], cwd=payload, input=info, capture_output=True, timeout=300) if ip is not None and ip.returncode == 0 else None
                    wt = _git(payload, "write-tree", "--missing-ok") if ui is not None and ui.returncode == 0 else None
                    if wt and not wt.returncode and wt.stdout.strip():
                        env = dict(os.environ, GIT_AUTHOR_NAME="reviewed code", GIT_AUTHOR_EMAIL="reviewer@example.invalid", GIT_COMMITTER_NAME="reviewed code",
                                   GIT_COMMITTER_EMAIL="reviewer@example.invalid", GIT_AUTHOR_DATE="2000-01-01T00:00:00Z", GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")
                        c = subprocess.run(["git", "commit-tree", wt.stdout.strip(), "-m", "base"], cwd=payload, capture_output=True, text=True, timeout=60, env=env)
                        if not c.returncode and c.stdout.strip():
                            for cmd in (["update-ref", "refs/heads/base", c.stdout.strip()], ["symbolic-ref", "HEAD", "refs/heads/base"], ["reset", "-q"]):  # reset: index = the base commit; the files on disk are the project's working tree
                                subprocess.run(["git", "-c", "core.logAllRefUpdates=false", *cmd], cwd=payload, capture_output=True, timeout=120, env=env)
                            shutil.rmtree(payload / ".git" / "logs", ignore_errors=True)  # a reflog would carry this machine's git identity (03 §5.56 batch 2 round 3)
                            return "base"
            except (OSError, subprocess.SubprocessError, ValueError): pass
            shutil.rmtree(payload / ".git", ignore_errors=True)
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
    (h / ".git").write_text("gitdir: .git-none-curmudgeon-agent\n")  # git run from notes/ (or here) stops here, never reaching the project's repository
    rec = {"payload": str(payload.resolve()), "notes": str(notes.resolve()), "root": str(root), "made_at": time.time(), "building": True}
    (h / "workspace.json").write_text(json.dumps(rec, indent=1))
    st = {"files": 0, "bytes": 0, "partial": False, "skipped_large": [], "links_skipped": [], "outside_links": [], "nested": [], "deps_not_linked": []}

    def link_deps(src, dst, rel):
        """A dependency folder is linked whole only when nothing inside it leads outside the project (round 3, F-bae6a123)."""
        bad = escaping_link(src, root)
        if bad: st["deps_not_linked"].append(f"{rel} (a link inside leads outside the project: {bad})"); return
        link(src, dst, rel)

    def link(target, dst, rel):
        try: os.symlink(target, dst, target_is_directory=os.path.isdir(target) if os.path.isabs(str(target)) else os.path.isdir(os.path.join(os.path.dirname(dst), target)))
        except OSError: st["links_skipped"].append(rel)

    def put(rel):
        """Copy one project file (or link) at rel. False once the budget is spent."""
        src = root / rel; dst = payload / rel
        if os.path.islink(src):
            t = _link_target(src, root)
            if t is None: return True
            dst.parent.mkdir(parents=True, exist_ok=True)
            if os.path.isabs(t):  # outside the project: neither copied nor linked, so a project can't point a reviewer at ~/.ssh or ~/.aws
                try: dst.write_text(OUTSIDE_STUB, encoding="utf-8"); st["outside_links"].append(rel)
                except OSError: st["links_skipped"].append(rel)
                return True
            link(t, dst, rel)
            return True
        if os.path.isdir(src):  # a submodule or nested repository git lists as one entry: its files, without its history
            st["nested"].append(rel)
            for top, dirs, names in os.walk(src):
                dirs[:] = sorted(x for x in dirs if x not in SKIP_ANYWHERE and x not in LINK_DIRS)
                for n in sorted(names):
                    if not put(os.path.relpath(os.path.join(top, n), root).replace(os.sep, "/")): return False
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
                    if not os.path.lexists(dst): dst.parent.mkdir(parents=True, exist_ok=True); link_deps(os.path.join(top, x), dst, os.path.normpath(os.path.join(relt, x)))
            dirs[:] = [x for x in dirs if depth < 3 and x not in LINK_DIRS and x not in SKIP_ANYWHERE and not (relt == "." and x == ".critic") and not os.path.islink(os.path.join(top, x))]
    else:
        stop = False
        for top, dirs, names in os.walk(root):
            relt = os.path.relpath(top, root); keep = []
            for x in sorted(dirs):
                src = os.path.join(top, x); rel = os.path.normpath(os.path.join(relt, x))
                if (relt == "." and x == ".critic") or x in SKIP_ANYWHERE or x in SKIP_BUILD: continue
                if x in LINK_DIRS and not os.path.islink(src): (payload / relt).mkdir(parents=True, exist_ok=True); link_deps(src, payload / rel, rel); continue
                if os.path.islink(src): put(rel); continue
                (payload / rel).mkdir(parents=True, exist_ok=True); keep.append(x)
            dirs[:] = keep
            for n in sorted(names):
                if not put(os.path.normpath(os.path.join(relt, n))): stop = True; break
            if stop: break
    try: rec["git"] = _own_repo(root, payload)
    except OSError: rec["git"] = "stub-failed"
    for k in ("skipped_large", "links_skipped", "outside_links", "nested", "deps_not_linked"): st[k] = st[k][:200]
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
