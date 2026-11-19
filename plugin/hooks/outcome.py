"""The outcome check (03 §5.57 item 52): what a reviewer's or verifier's shell command really changed on disk, judged
by the result, not by how the command was spelled. Five reviews of 5.9.2 kept finding new spellings that slipped past
conduct.py's reading of shell text; a change to a protected file is seen here whatever the spelling, including one
made by code the agent ran.

How it works:
  - The protected set: the project's own files outside .critic/ (with node_modules and .git's hooks and config), the
    other reviews in .critic/reviews/, the claim tokens, and the instruction files Claude Code reads from the user's
    home folder. Nothing in it is written while reviewers and verifiers run; their own copy and notes are not in it.
  - Each Bash call of a reviewer or verifier is logged with its start and end time (call_start, call_end).
  - After each call, the protected set is compared with the last snapshot. Each changed file has a change time: its
    ctime on macOS and Linux, which no program can set back, and its mtime on Windows. A change is charged to an agent
    only when that agent's call was running at that time and no other agent's was; then the agent is cut (ruling 44:
    a write outside its space). Its own claimed review is never a change against it. A change no single agent's call
    covers is listed for the owner as unattributed, and no one is cut for it.
  - At an agent's stop the same comparison runs once more, so a background job's later write is not missed.
State lives in Curmudgeon's own folder outside the project (~/.curmudgeon, or CURMUDGEON_STATE_DIR), which agents can't
write. Above LIMIT files the check watches folders only (new and removed files, not edits) and says so. Every part
fails open: a broken check never blocks or cuts anyone."""
import hashlib
import json
import os
import pathlib
import stat
import time

LIMIT = 20000          # watched files before the check falls back to folders only
PENDING_S = 30         # seconds a change to another reviewer's claimed review waits for that reviewer's own save to be recorded
LONGEST = 600          # seconds: a call whose end was never logged is taken to have ended this long after it started (Bash's own longest timeout)
SLACK = 0.05           # seconds either side of a call: file times come from the same clock as the hook's, a few ms coarser
SKIP_DIRS = {".critic", ".git"}  # at the project's top: .critic is judged file by file below, .git by its config and hooks
CACHES = {"__pycache__", ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".turbo"}  # written by honest test runs and tools, anywhere


def _state(root):
    base = pathlib.Path(os.environ.get("CURMUDGEON_STATE_DIR") or pathlib.Path.home() / ".curmudgeon")
    key = hashlib.sha256(os.path.normcase(os.path.realpath(str(root))).encode("utf-8")).hexdigest()[:16]
    d = base / "outcome" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _when(st):
    """When the file last changed. On macOS and Linux its ctime, which a program can neither set back nor forward
    (setting the mtime changes the ctime to now); on Windows only the mtime is there (round 1, F-d1b2776c)."""
    return st.st_ctime if os.name != "nt" else st.st_mtime


def _same(a, b):
    """Two snapshot entries match: size, mtime and (on POSIX) ctime, so a same-size rewrite with its mtime put back
    still shows (round 1, F-d00d0b9b)."""
    return a[0] == b[0] and a[1] == b[1] and (os.name == "nt" or a[2] == b[2])


def watched(root):
    """Every protected path with (size, mtime_ns, change time), and whether the list is partial (folders only)."""
    root = pathlib.Path(root)
    out, partial, n = {}, False, 0
    def add(p):
        try: st = os.stat(p, follow_symlinks=False)
        except OSError: return
        if stat.S_ISDIR(st.st_mode) and not partial: return  # folders only in folder mode: their time changes whenever an honest writer adds to them
        out[str(p)] = (st.st_size, st.st_mtime_ns, _when(st))
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in CACHES and not (pathlib.Path(d) == root and x in SKIP_DIRS) and not (os.path.basename(d) == "node_modules" and x.startswith("."))]  # node_modules/.vite, .cache...: tools' caches, written by honest test runs through the copy's link (round 2, F-9dec388c)
        n += len(fs)
        if n > LIMIT:  # too many files: from here on each folder alone (its time changes when a file is made or removed in it)
            partial = True; add(d); continue
        for f in fs: add(os.path.join(d, f))
    git = root / ".git"
    for p in [git / "config", git / "HEAD"] + (sorted((git / "hooks").glob("*")) if (git / "hooks").is_dir() else []): add(p)
    c = root / ".critic"
    for p in (sorted((c / "reviews").glob("*")) if (c / "reviews").is_dir() else []) + [c / "proctor" / "claim-tokens.json", c / "ledger.json"]: add(p)  # files only: a folder's time changes whenever an honest writer adds to it (round 1, F-a0168e24)
    home = pathlib.Path.home() / ".claude"
    for p in (home / "settings.json", home / "settings.local.json", home / "CLAUDE.md"): add(p)
    return out, partial


def known(root, path):
    """A legitimate writer's own change (a reviewer saving its claimed review with Write, the stop hook's stamp): its
    content is recorded, and a change that leaves exactly that content is no one's to answer for (round 1, F-b4ea77d7,
    F-1011538f)."""
    try:
        h = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        f = _state(root) / "known.jsonl"
        with f.open("a", encoding="utf-8") as fh: fh.write(json.dumps({"path": str(path), "sha": h}) + "\n")
    except OSError: pass


def _known(root):
    out = {}
    try:
        for line in (_state(root) / "known.jsonl").open(encoding="utf-8"):
            try: j = json.loads(line); out.setdefault(j["path"], set()).add(j["sha"])
            except (ValueError, KeyError): pass
    except OSError: pass
    return out


def _calls(root):
    f = _state(root) / "calls.jsonl"
    out = []
    try:
        for line in f.open(encoding="utf-8"):
            try: out.append(json.loads(line))
            except ValueError: pass
    except OSError: pass
    return out


def _log_call(root, rec):
    with (_state(root) / "calls.jsonl").open("a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")


def _baseline(root):
    """The last snapshot, or None when there is none or it is older than this run (a run's first call takes a new
    one, so edits made between runs are never charged to anyone)."""
    try:
        j = json.loads((_state(root) / "baseline.json").read_text(encoding="utf-8"))
        import conduct
        if float(j.get("at") or 0) < conduct.started(root): return None, False  # taken before this run began
        return {k: tuple(v) for k, v in j["files"].items()}, j.get("partial", False)
    except (OSError, ValueError, KeyError, TypeError): return None, False


def _save(root, snap, partial):
    d = _state(root); tmp = d / f"baseline.{os.getpid()}.tmp"
    tmp.write_text(json.dumps({"files": snap, "partial": partial, "at": time.time()}), encoding="utf-8")
    os.replace(tmp, d / "baseline.json")


def call_start(root, agent, call_id):
    """Before a reviewer's or verifier's Bash call: log its start, and take the first snapshot if there is none."""
    if _baseline(root)[0] is None:
        forget(root)  # a new run: last run's calls are no one's now
        snap, partial = watched(root); _save(root, snap, partial)
    _log_call(root, {"agent": agent, "id": call_id, "start": time.time()})


def call_end(root, agent, call_id, own=()):
    """After the call: log its end, compare the protected set with the last snapshot, and charge what changed.
    Returns [(agent or None, path, what)] for the caller to record: an agent's name means cut, None means unattributed."""
    now = time.time()
    mine = any(r.get("agent") == agent and r.get("id") == call_id and "start" in r for r in _calls(root))
    gone = not (_state(root) / "baseline.json").is_file()
    _log_call(root, {"agent": agent, "id": call_id, "end": now})
    if not mine or gone:  # its start was logged and a snapshot taken before it ran: if either is gone, something removed them during this call (round 1, F-2de49bd3)
        rest = [] if gone else sweep(root, own_of={agent: own})
        if gone: snap, partial = watched(root); _save(root, snap, partial)
        return [(agent, str(_state(root)), "removed the outcome check's own record of")] + rest
    return sweep(root, own_of={agent: own})


def _windows(root):
    """Each call's (agent, start, end); a call with no end yet is still running, until the same agent starts another
    call or LONGEST seconds pass (round 1, F-4a7db951: a call whose end was never logged took the blame for the rest of
    the run)."""
    by, order = {}, []
    for r in _calls(root):
        k = (r.get("agent"), r.get("id"))
        if k not in by: by[k] = [None, None]; order.append(k)
        if "start" in r: by[k][0] = r["start"]
        if "end" in r: by[k][1] = r["end"]
    out = []
    for k in order:
        s, e = by[k]
        if s is None: continue
        if e is None:
            later = [by[j][0] for j in order if j[0] == k[0] and j != k and by[j][0] and by[j][0] > s]
            e = min(later) if later else (s + LONGEST if time.time() > s + LONGEST else None)
        out.append((k[0], s, e))
    return out


def _claimed(root):
    """{review file name: the agent that claimed it}."""
    try:
        import conduct
        return {r: a for a, r in conduct.claims(root).items()}
    except Exception: return {}


def _stopped(root, agent):
    return (pathlib.Path(root) / ".critic" / "stops" / f"{agent}.json").is_file()


def _pending(root, okay, now, out):
    """Changes to a review another reviewer claimed wait here until that reviewer's own save is recorded as a known
    write (it lands just after the save, so a command ending in that gap must not be charged: round 2, F-cec6dc20 and
    F-b75d95cf). One is dropped when its content is the owner's known write, and charged as found once the owner has
    stopped or PENDING_S seconds have passed."""
    f = _state(root) / "pending.jsonl"; keep = []
    try: rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError): rows = []
    for r in rows:
        try: sha = hashlib.sha256(pathlib.Path(r["path"]).read_bytes()).hexdigest()
        except OSError: sha = None
        if sha and sha in okay.get(r["path"], set()): continue
        if _stopped(root, r.get("owner")) or now - r["t"] > PENDING_S: out.append((r.get("agent"), r["path"], r["what"]))
        else: keep.append(r)
    tmp = f.with_suffix(f".{os.getpid()}.tmp"); tmp.write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8"); os.replace(tmp, f)


def sweep(root, own_of=None):
    """Compare the protected set with the last snapshot, charge each change, and save the new snapshot."""
    old, _ = _baseline(root)
    began = time.time()  # before the walk: a removed file is timed from here, however long the walk takes (round 2, F-311e3be9)
    snap, partial = watched(root)
    _save(root, snap, partial)
    if old is None: return []
    now = time.time(); wins = _windows(root); out = []; okay = _known(root); claimed = _claimed(root); wait = []
    _pending(root, okay, now, out)
    own_of = {a: {os.path.normcase(os.path.realpath(str(p))) for p in ps} for a, ps in (own_of or {}).items()}
    if partial and not (_state(root) / "partial.flag").exists():
        (_state(root) / "partial.flag").write_text("1", encoding="utf-8")
        out.append((None, None, f"the outcome check watched only the project's folders (it has more than {LIMIT} files), so an edit to an existing file was not seen"))  # round 1, F-91c5a0d8
    for path in sorted(set(old) | set(snap)):
        a, b = old.get(path), snap.get(path)
        if a is not None and b is not None and _same(a, b): continue
        if b is not None and path in okay:
            try:
                if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() in okay[path]: continue
            except OSError: pass
        what = "made" if a is None else "removed" if b is None else "changed"
        t = b[2] if b is not None else began  # a removed file has no time of its own: only a call running when the walk began can be charged
        who = {ag for ag, s, e in wins if s - SLACK <= t <= (e if e is not None else now) + SLACK}
        ag = next(iter(who)) if len(who) == 1 else None
        if ag and os.path.normcase(os.path.realpath(path)) in own_of.get(ag, set()): continue  # its own claimed review
        owner = claimed.get(os.path.basename(path)) if os.path.basename(os.path.dirname(path)) == "reviews" else None
        if owner and owner != ag and b is not None:  # another reviewer's claimed review: wait for that reviewer's own save
            wait.append({"path": path, "agent": ag, "what": what, "t": now, "owner": owner}); continue
        out.append((ag, path, what))
    if wait:
        with (_state(root) / "pending.jsonl").open("a", encoding="utf-8") as fh:
            for r in wait: fh.write(json.dumps(r) + "\n")
    return out


def record(root, found):
    """Write what sweep found where the merge step reads it: a cut for an agent (conduct.note, as ruling 44's cuts),
    and an unattributed change for the owner."""
    import conduct
    for ag, path, what in found:
        if path is None: conduct.note(root, "unattributed", what, "unattributed"); continue
        rel = os.path.relpath(path, str(root)) if os.path.realpath(path).startswith(os.path.realpath(str(root))) else path
        if ag: conduct.note(root, ag, f"{what} {rel} while its command ran (seen on disk, whatever the command's spelling)", "cut")
        else: conduct.note(root, "unattributed", f"{what} {rel} while reviewers or verifiers ran, not tied to one agent", "unattributed")


def forget(root):
    """End of a run: drop the snapshot and the call log."""
    d = _state(root)
    for f in ("baseline.json", "calls.jsonl", "known.jsonl", "partial.flag", "pending.jsonl"):
        try: (d / f).unlink()
        except OSError: pass
