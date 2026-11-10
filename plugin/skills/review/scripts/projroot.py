"""Which project a folder belongs to, for the hooks and every script (one rule, not ten copies: 5.4.0 blind rounds).

The project is the folder above the first .critic in the path: <project>/.critic/... always maps back, however deep
(an agent's copy under scratch, the briefs folder a lead cd'd into: run report N1, a .critic inside a .critic, an empty
one), in any letter case (Windows and macOS ignore it). No guess is made from what a folder holds.

`base` is the project Claude Code's session started in (hooks get it as CLAUDE_PROJECT_DIR, which stays put when the
session cds; the Bash tool doesn't get it). A .critic above it is ignored, so a project kept under a folder named
.critic (~/.critic/projects/app) stays itself. Scripts have no base: for such a project, set CRITIC_ROOT."""
import os, re

PART = re.compile(r"[\\/]\.critic(?=[\\/]|$)", re.IGNORECASE)

def _fold(p): return os.path.normcase(p).replace("\\", "/").rstrip("/").casefold()

def project_of(cwd, base=None):
    cwd = os.path.normpath(str(cwd))
    b = _fold(os.path.normpath(base)) if base else ""
    for m in PART.finditer(cwd):
        prefix = cwd[:m.start()]
        if b and (b + "/").startswith(_fold(cwd[:m.end()]) + "/"): continue  # a .critic at or above the session's folder is never the project's own (settled: "Settled design decisions" 1)
        if not prefix: return os.sep  # /.critic/...
        if re.fullmatch(r"[A-Za-z]:", prefix): return prefix + "\\"  # C:\.critic\... -> C:\, never "C:" (the current folder on C)
        return prefix
    return cwd
