#!/usr/bin/env python3
"""SubagentStart: gives each Curmudgeon agent its own private scratch folder, .critic/scratch/<agent_id>/, and gives
each reviewer and verifier a private frozen copy of the payload inside that folder (workspace.py), where its Bash
commands must run. The project's .critic/ folder is not in the copy, so the agent's cwd, relative paths and searches
can't reach the other reviews or the scan. The read guard (read_guard.py) enforces the rest. Never fails the agent's
start: when no copy can be made, the agent is told that Bash is off for it and it reviews by reading."""
import json, os, pathlib, re, shlex, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    kind = str(data.get("agent_type") or "")
    m = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-(reviewer|verifier|dedup|detector)", kind)
    if not m: return 0
    agent_id = workspace.clean_id(data.get("agent_id"))
    if not agent_id: return 0
    root = workspace.project_root(data); c = root / ".critic"
    if c.is_symlink() or (c / "scratch").is_symlink(): return 0  # never create through a link a cloned repo planted
    d = c / "scratch" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    try: os.chmod(d, 0o700)
    except OSError: pass
    msg = f"Your private scratch folder is {d}. Put any notes there and nowhere else; other agents can't read it, and you can't read theirs."
    if m.group(1) in ("reviewer", "verifier"):
        try: rec = workspace.make(root, agent_id)
        except Exception: rec = None
        if rec:
            q = shlex.quote(rec["payload"])
            msg = (f"Your workspace is {rec['payload']}: a private frozen copy of the project made for you (the project's .critic/ is left out). "
                   + ("It is its own git repository: one commit holding the project's last commit, with no history or authors (you review the code, not who wrote it); git diff shows the uncommitted edits, and git commands there never touch the real project. " if rec.get("git") == "base" else "")
                   + f"Read and search files there. Start every Bash command with `cd {q} && `; commands that don't are refused. For git, use `git -C {q} <command>` on its own (Claude Code asks the user before a cd followed by git). "
                   f"Cite files by their path relative to the workspace, which is the same as in the project (src/app.js:12, never the full path). "
                   f"Put notes, probes and test scripts in {rec['notes']}; they are kept after you finish, and the copy is deleted. "
                   f"Write your result where your brief says, under {c}.")
            if rec.get("partial"): msg += " The copy is partial (the project is very large): a file missing from it can be read from the project itself."
            if rec.get("outside_links"): msg += f" These are links to files or folders outside the project; their content was not copied (each is a short note in the copy): {', '.join(rec['outside_links'][:10])}."
            if rec.get("deps_not_linked"): msg += f" Dependency folders left out, so tests that need them won't run here: {', '.join(rec['deps_not_linked'][:5])}."
            if rec.get("nested"): msg += f" Copied as plain files, without their git history: {', '.join(rec['nested'][:10])}."
            if rec.get("links_skipped"): msg += f" Links the system wouldn't let us make were left out: {', '.join(rec['links_skipped'][:10])}."
            if rec.get("git") in ("stub", "stub-failed", "none"): msg += " Git history isn't available in the copy (git will say there is no repository); read the code as it is."
            if rec.get("skipped_large"): msg += f" Files over 5 MB were not copied: {', '.join(rec['skipped_large'][:10])}."
        else:
            msg += " No private copy of the project could be made, so Bash is off for you: review by reading (Read, Grep, Glob)."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": msg}}))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
