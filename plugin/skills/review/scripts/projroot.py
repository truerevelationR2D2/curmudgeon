"""Which project a folder belongs to, for the hooks and every script (one rule, not ten copies: 5.4.0 blind round).

The path's .critic folders are tried from the left, and the first that is Curmudgeon's own wins: the path ends at it,
the next folder is one Curmudgeon writes there (an agent's copy under scratch, the briefs folder a lead cd'd into: run
report N1), or it holds Curmudgeon's records. Its parent is the project. So <project>/.critic/... always maps back,
however deep, even when a .critic has a .critic of its own inside it, while a project kept under a folder named .critic
(~/.critic/projects/app) stays itself."""
import os, re

NAMES = {"ledger.json", "ledger.md", "runlog.jsonl", "change-map.json", "change-map.md", "plan.json", "focus.json", "briefs",
         "reviews", "scratch", "outside", "scan", "verify", "verdicts", "history", "restore", "audit-owner.json", "last-review.md",
         "tally.json", "counts.md", "findings.jsonl", "decisions.md", "scan-only.txt", "manifest.json"}  # what Curmudgeon writes in .critic
PART = re.compile(r"[\\/]\.critic(?=[\\/]|$)")

def project_of(cwd):
    cwd = str(cwd)
    for m in PART.finditer(cwd):
        prefix = cwd[:m.start()]
        if not prefix: continue
        nxt = re.split(r"[\\/]", cwd[m.end():].lstrip("\\/"), maxsplit=1)[0]
        state = os.path.join(prefix, ".critic")
        if not nxt or nxt in NAMES or any(os.path.lexists(os.path.join(state, n)) for n in NAMES): return prefix
    return cwd
