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
import time

LIMIT = 20000          # watched files before the check falls back to folders only
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
    return max(st.st_mtime, st.st_ctime) if os.name != "nt" else st.st_mtime  # ctime can't be set back by a program on POSIX


def watched(root):
    """Every protected path with (size, mtime_ns, change time), and whether the list is partial (folders only)."""
    root = pathlib.Path(root)
    out, partial, n = {}, False, 0
    def add(p):
        try: st = os.stat(p, follow_symlinks=False)
        except OSError: return
        out[str(p)] = (st.st_size, st.st_mtime_ns, _when(st))
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in CACHES and not (pathlib.Path(d) == root and x in SKIP_DIRS)]
        n += len(fs)
        if n > LIMIT:  # too many files: from here on each folder alone (its time changes when a file is made or removed in it)
            partial = True; add(d); continue
        for f in fs: add(os.path.join(d, f))
    git = root / ".git"
    for p in [git / "config", git / "HEAD"] + (sorted((git / "hooks").glob("*")) if (git / "hooks").is_dir() else []): add(p)
    c = root / ".critic"
    for p in (sorted((c / "reviews").glob("*")) if (c / "reviews").is_dir() else []) + [c / "proctor" / "claim-tokens.json", c / "reviews"]: add(p)
    home = pathlib.Path.home() / ".claude"
    for p in (home / "settings.json", home / "settings.local.json", home / "CLAUDE.md"): add(p)
    return out, partial


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
        if float(j.get("at") or 0) < conduct.started(root) - 1: return None, False
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
    _log_call(root, {"agent": agent, "id": call_id, "end": now})
    return sweep(root, own_of={agent: own})


def _windows(root):
    """Each call's (agent, start, end); a call with no end yet is still running."""
    by = {}
    for r in _calls(root):
        k = (r.get("agent"), r.get("id"))
        w = by.setdefault(k, [None, None])
        if "start" in r: w[0] = r["start"]
        if "end" in r: w[1] = r["end"]
    return [(a, s, e) for (a, _), (s, e) in by.items() if s is not None]


def sweep(root, own_of=None):
    """Compare the protected set with the last snapshot, charge each change, and save the new snapshot."""
    old, _ = _baseline(root)
    snap, partial = watched(root)
    _save(root, snap, partial)
    if old is None: return []
    now = time.time(); wins = _windows(root); out = []
    own_of = {a: {os.path.normcase(os.path.realpath(str(p))) for p in ps} for a, ps in (own_of or {}).items()}
    for path in sorted(set(old) | set(snap)):
        a, b = old.get(path), snap.get(path)
        if a is not None and b is not None and a[:2] == b[:2]: continue
        what = "made" if a is None else "removed" if b is None else "changed"
        t = b[2] if b is not None else now  # a removed file has no time of its own: only the call running now can be charged
        who = {ag for ag, s, e in wins if s - SLACK <= t <= (e if e is not None else now) + SLACK}
        if len(who) == 1:
            ag = next(iter(who))
            if os.path.normcase(os.path.realpath(path)) in own_of.get(ag, set()): continue  # its own claimed review
            out.append((ag, path, what))
        else: out.append((None, path, what))
    return out


def record(root, found):
    """Write what sweep found where the merge step reads it: a cut for an agent (conduct.note, as ruling 44's cuts),
    and an unattributed change for the owner."""
    import conduct
    for ag, path, what in found:
        rel = os.path.relpath(path, str(root)) if os.path.realpath(path).startswith(os.path.realpath(str(root))) else path
        if ag: conduct.note(root, ag, f"{what} {rel} while its command ran (seen on disk, whatever the command's spelling)", "cut")
        else: conduct.note(root, "unattributed", f"{what} {rel} while reviewers or verifiers ran, not tied to one agent", "unattributed")


def forget(root):
    """End of a run: drop the snapshot and the call log."""
    d = _state(root)
    for f in ("baseline.json", "calls.jsonl"):
        try: (d / f).unlink()
        except OSError: pass
