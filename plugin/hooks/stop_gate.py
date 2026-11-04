#!/usr/bin/env python3
"""Curmudgeon stop gate (opt-in, Claude Code only). Turned on per project by /curmudgeon:gate on (creates .critic/gate).

It blocks finishing for one of two causes, each with its own message:
  1. edits since the last review: a watched file is newer than .critic/last-review.md. Watched files are the ones the
     last review stamped (critic_ledger.py stamp) plus any code file created or changed since (so new files count too).
  2. open Critical/High findings after a full run. A review-only run (mode "review") is an audit: its open findings
     never block.
Loop guards: never blocks while Claude Code reports stop_hook_active; at most 3 blocks for the same batch of edits.
After the third it lets stops through for that batch for good (it says so once); a new edit starts a new batch.
Fails open, but never silently: an unexpected error lets the stop through with a message saying the gate is off."""
import hashlib, json, os, pathlib, shlex, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import workspace

SKIP = {".git", "node_modules", "dist", "build", ".critic", "__pycache__", ".next", "coverage", "vendor", ".venv", "venv",
        ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache", ".gradle", ".idea", ".svn", ".hg"}
# Tools' generated or downloaded dot-folders, skipped everywhere (in git too, where a fresh repository may not ignore them).
GENERATED_DOTDIRS = {".env", ".svelte-kit", ".nuxt", ".output", ".angular", ".turbo", ".parcel-cache", ".vercel", ".netlify",
                     ".yarn", ".pnpm-store", ".terraform", ".direnv", ".conda", ".serverless", ".docusaurus", ".expo", ".dart_tool",
                     ".astro", ".wrangler", ".react-router", ".eggs", ".cargo", ".local", ".npm", ".m2"}
# Outside git, only these dot-folders are watched (plus any holding a stamped file): an unknown one is far more often a
# tool's than code someone wrote (collected round review). In git, the project's own ignore rules decide instead.
CODE_DOTDIRS = {".claude", ".github", ".husky", ".devcontainer", ".circleci", ".gitlab", ".storybook", ".githooks", ".config",
                ".vitepress", ".vuepress", ".buildkite", ".gitea", ".forgejo", ".changeset"}
CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".css", ".scss", ".html", ".vue", ".svelte", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".swift", ".kt"}

def nested_checkout(d):
    """A folder that is its own checkout (a .git file or folder): Claude Code's worktrees under .claude/worktrees, a
    submodule, a vendored repository. Its edits are another session's, never this project's (Qodo on #17)."""
    return (d / ".git").exists()

def skipped(name): return name in SKIP or name in GENERATED_DOTDIRS

def candidates(root, stamps=()):
    """The code files the gate watches. In git: tracked and untracked files git doesn't ignore, so a project's own
    .gitignore decides what is generated, minus tools' folders a fresh repository may not ignore yet. When git lists
    nothing for the project (an enclosing repository that ignores it, a dotfiles home repository) or can't answer,
    the walk below decides, so the gate is never silently off (collected round review)."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
    try:
        import safegit
        r = safegit.run(["ls-files", "-z", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            out, seen = [], {}
            for rel in r.stdout.split("\0"):
                if not rel or pathlib.PurePosixPath(rel).suffix not in CODE or rel.startswith(".critic/") or "/.claude/worktrees/" in "/" + rel: continue
                parts = pathlib.PurePosixPath(rel).parts[:-1]
                if any(skipped(x) for x in parts): continue
                for i in range(1, len(parts) + 1):
                    if parts[:i] not in seen: seen[parts[:i]] = nested_checkout(root.joinpath(*parts[:i]))  # once per folder (collected round review)
                if any(seen[parts[:i]] for i in range(1, len(parts) + 1)): continue
                out.append(root / rel)
            if out: return out
    except Exception: pass
    stamped_dirs = {pathlib.PurePosixPath(k).parts[0] for k in stamps if pathlib.PurePosixPath(k).parts}
    out = []
    for dp, dns, fns in os.walk(root):
        top = pathlib.Path(dp) == root
        dns[:] = [d for d in dns if not skipped(d) and not (pathlib.Path(dp).name == ".claude" and d == "worktrees") and not nested_checkout(pathlib.Path(dp) / d)
                  and (not d.startswith(".") or d in CODE_DOTDIRS or (top and d in stamped_dirs))]
        out += [pathlib.Path(dp) / fn for fn in fns if pathlib.Path(fn).suffix in CODE]
    return out

def newest(root, stamps):
    best = (0.0, None)
    for p in [root / k for k in stamps] + candidates(root, stamps):
        try: m = p.stat().st_mtime
        except OSError: continue  # deleted files and broken links are skipped, not fatal
        if m > best[0]: best = (m, p)
    return best

def out(obj): print(json.dumps(obj)); return 0

def main():
    try: data = json.load(sys.stdin)
    except Exception: data = {}
    if data.get("stop_hook_active"): return 0
    root = workspace.project_root(data); c = root / ".critic"
    if (c / "gate").exists() and (c.is_symlink() or any(x.is_symlink() for x in c.glob("*"))):  # gate on, but never write through a planted link
        print(json.dumps({"systemMessage": "Curmudgeon stop gate skipped: .critic/ contains links. Remove them to use the gate."})); return 0
    if not (c / "gate").exists(): return 0
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "review" / "scripts"))
    try:
        from critic_findings import gate_owned
        if not gate_owned(root, "on"): return out({"systemMessage": "Curmudgeon stop gate skipped: .critic/gate is there, but the owner's record doesn't show it turned on here (a repository may have committed it). Run /curmudgeon:gate on to turn it on."})
    except Exception as e: return out({"systemMessage": f"Curmudgeon stop gate skipped: couldn't check the owner's record that the gate is on here ({type(e).__name__}: {e}). A marker in the project alone never turns it on (Qodo on PR #14)."})
    try: L = json.loads((c / "ledger.json").read_text(encoding="utf-8"))
    except FileNotFoundError: L = {}
    except Exception as e: return out({"systemMessage": f"Curmudgeon gate is off for this stop: the ledger can't be read ({e}). Fix .critic/ledger.json or run critic_ledger.py init."})
    if not isinstance(L, dict): L = {}
    review = c / "last-review.md"
    m, p = newest(root, L.get("stamps") or {})
    reason, batch = None, ""
    since = review.stat().st_mtime if review.exists() else None
    from critic_findings import observe_deletions
    seen = observe_deletions(root, L.get("stamps") or {})  # each missing stamped file, with when it went (first seen by the gate; Qodo on #17)
    gone = sorted(k for k, t in seen.items() if since is None or t > since)  # a stamped file deleted after the review, or with no review saved yet: a change too (audit O1; Qodo on #20)
    parts, keys = [], []
    if gone:  # alongside the edit check, never instead of it, so a new edit always starts a new batch (batch 3 review)
        keys.append("deleted:" + hashlib.sha1("|".join(f"{k}@{seen[k]}" for k in gone).encode()).hexdigest()[:12])  # when, too: a re-deletion is a new batch (Qodo on #17)
        parts.append(f"{', '.join(gone[:5])}{' and more' if len(gone) > 5 else ''} {'was' if len(gone) == 1 else 'were'} deleted after the last Curmudgeon review"
                     f" (if the last review did cover it, say so: critic_ledger.py stamp --add {' '.join(shlex.quote(g) for g in gone[:5])}).")  # quoted: a file name is never shell syntax to copy (Qodo on #19)  # the time of a deletion is only a best guess (Qodo on #18)
    if p is not None and not (review.exists() and review.stat().st_mtime >= m):
        keys.append(hashlib.sha1(f"{p}:{m}".encode()).hexdigest()[:12])
        where = p.relative_to(root) if str(p).startswith(str(root)) else p
        parts.append("No Curmudgeon review exists yet for this project's edits." if not review.exists() else f"{where} was edited after the last Curmudgeon review.")
    if parts:
        batch = "|".join(keys)
        reason = " ".join(parts) + " Run /curmudgeon:review review on what changed since the last review (use the curmudgeon-reviewer agent; a deletion can remove a check), and save the teardown to .critic/last-review.md."
    elif L.get("mode") == "full":
        open_ = [i for i, f in (L.get("findings") or {}).items() if isinstance(f, dict) and f.get("status") == "open" and str(f.get("score", "")).title() in ("Critical", "High")]
        if open_:
            batch = "open:" + ",".join(sorted(open_))
            reason = (f"The last full Curmudgeon run left Critical/High findings open: {', '.join(open_[:8])}. Fix each one, or defer it with "
                      "critic_ledger.py defer ID impossible|conflicts|worse \"note\". Then re-check and update .critic/last-review.md.")
    cnt = c / "gate-count"
    if not reason: cnt.unlink(missing_ok=True); return 0
    try: prev = json.loads(cnt.read_text(encoding="utf-8"))
    except Exception: prev = {}
    if prev.get("batch") == batch and prev.get("released"): return 0  # already handed back for this batch
    n = prev.get("n", 0) + 1 if prev.get("batch") == batch else 1
    if n > 3:
        cnt.write_text(json.dumps({"batch": batch, "n": n, "released": True}), encoding="utf-8")
        return out({"systemMessage": f"Curmudgeon gate let this stop through after 3 blocks on the same work, and won't block it again until something changes. Still unresolved: {reason.split('. ')[0]}. Over to you: fix, defer with a reason, or /curmudgeon:gate off."})
    cnt.write_text(json.dumps({"batch": batch, "n": n}), encoding="utf-8")
    return out({"decision": "block", "reason": f"Curmudgeon gate ({n} of 3 for this work): {reason} Turn the gate off with /curmudgeon:gate off."})

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:
        print(json.dumps({"systemMessage": f"Curmudgeon gate is off for this stop: unexpected error ({type(e).__name__}: {e})."})); sys.exit(0)
