"""Private frozen workspaces for blind agents (5.0, ruling §5.29). Each reviewer and verifier gets its own copy of the
payload, so its cwd, its relative paths and its searches can only reach code: the project's other .critic/ files (the
other reviews, the scan, the tally) are not in the copy. That makes blindness structural instead of a contest between a
shell parser and a shell.

Layout, inside the agent's own scratch folder (Claude Code only lets an agent `cd` inside the session's working
folders, so the copy has to live in the project; the read guard already gives each agent its scratch folder alone):
    <project>/.critic/scratch/<agent_id>/payload          the copy; its Bash commands run from here
    <project>/.critic/scratch/<agent_id>/notes            its notes and probes (kept after it stops)
    <project>/.critic/scratch/<agent_id>/workspace.json   the record

What is copied: every file under the project except the top-level .critic, version-control folders and caches, and files
over MAX_FILE. Dependency folders (node_modules, .venv, venv) are linked, not copied, so tests can run. Links in the
payload are kept only when they can't lead back into the project's .critic or above the project: a link to somewhere in
the project points at the same place in the copy instead. Past MAX_TOTAL bytes or MAX_FILES files the copy stops and is
marked partial; the agent is told, and can still Read the project's own files (never its .critic).

The threat this answers is an honest agent that anchors on what it happens to see, not a hostile one: a same-user
process can always build a path to any file the user can read. Hostile isolation needs an OS sandbox."""
import json, os, pathlib, re, shutil, time

SKIP_ANYWHERE = {".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".cache"}
LINK_DIRS = {"node_modules", ".venv", "venv"}
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
MAX_FILES = 100_000

def clean_id(v): return re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:64]

def fold(p): return os.path.normcase(os.path.normpath(str(p))).casefold()

def within(p, top):
    p, top = fold(p), fold(top)
    return p == top or p.startswith(top.rstrip(os.sep) + os.sep)

def home_for(root, agent_id):
    """This agent's folder, or None when it can't be made safely (a planted link on the way)."""
    root = pathlib.Path(root); c = root / ".critic"
    agent_id = clean_id(agent_id)
    if not agent_id or c.is_symlink() or (c / "scratch").is_symlink() or (c / "scratch" / agent_id).is_symlink(): return None
    return c / "scratch" / agent_id

def info(root, agent_id):
    """The workspace record for this agent, or None. Only trusted when it names this agent's own payload folder."""
    h = home_for(root, agent_id)
    if not h: return None
    p = h / "workspace.json"
    try:
        if p.is_symlink() or not p.is_file(): return None
        j = json.loads(p.read_text())
    except (OSError, ValueError): return None
    if not isinstance(j, dict) or fold(j.get("payload", "")) != fold(h.resolve() / "payload") or not pathlib.Path(j["payload"]).is_dir(): return None
    return j

def _link_target(src, root):
    """Where a copied link should point: None to drop it, else the target to write."""
    try:
        target = os.readlink(src); real = pathlib.Path(src).resolve()
    except (OSError, RuntimeError, ValueError): return None
    rt = pathlib.Path(root).resolve()
    if within(real, rt / ".critic") or within(real, rt / ".git"): return None
    if within(rt, real): return None  # a link to the project itself or above it: a way back to .critic
    if within(real, rt):
        rel_from = os.path.dirname(os.path.relpath(src, rt))
        return os.path.relpath(os.path.relpath(real, rt), rel_from or ".")  # the same place, but in the copy
    return target  # outside the project (a system library, say): harmless to keep

def make(root, agent_id):
    """Build the workspace and write its record. Returns the record, or None when no workspace could be made."""
    root = pathlib.Path(root).resolve(); h = home_for(root, agent_id)
    if not h: return None
    h.mkdir(parents=True, exist_ok=True); os.chmod(h, 0o700)
    payload = h / "payload"; notes = h / "notes"
    if payload.exists() or payload.is_symlink(): shutil.rmtree(payload, ignore_errors=True)
    payload.mkdir(); notes.mkdir(exist_ok=True)
    total = files = 0; partial = False; skipped = []
    for top, dirs, names in os.walk(root):
        rel = os.path.relpath(top, root)
        keep = []
        for x in sorted(dirs):
            src = os.path.join(top, x)
            if (rel == "." and x == ".critic") or x in SKIP_ANYWHERE: continue
            if x in LINK_DIRS and not os.path.islink(src):
                os.symlink(src, payload / rel / x); continue
            if os.path.islink(src):
                t = _link_target(src, root)
                if t is not None: os.symlink(t, payload / rel / x)
                continue
            (payload / rel / x).mkdir(); keep.append(x)
        dirs[:] = keep
        for n in sorted(names):
            src = os.path.join(top, n); dst = payload / rel / n
            if os.path.islink(src):
                t = _link_target(src, root)
                if t is not None: os.symlink(t, dst)
                continue
            try: size = os.path.getsize(src)
            except OSError: continue
            if size > MAX_FILE: skipped.append(os.path.normpath(os.path.join(rel, n))); continue
            if total + size > MAX_TOTAL or files >= MAX_FILES: partial = True; break
            try: shutil.copy2(src, dst)
            except OSError: skipped.append(os.path.normpath(os.path.join(rel, n))); continue
            total += size; files += 1
        if partial: break
    rec = {"payload": str(payload.resolve()), "notes": str(notes.resolve()), "root": str(root), "made_at": time.time(),
           "files": files, "bytes": total, "partial": partial, "skipped_large": skipped[:200]}
    (h / "workspace.json").write_text(json.dumps(rec, indent=1))
    return rec

def remove(root, agent_id):
    """At the agent's stop: delete the copy, keep the notes and the record."""
    rec = info(root, agent_id)
    if not rec: return False
    shutil.rmtree(rec["payload"], ignore_errors=True)
    return True
