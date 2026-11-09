"""Which project a folder belongs to, for the hooks and every script (one rule, not ten copies: 5.4.0 blind round).

A folder inside an agent's copy (<project>/.critic/scratch/...) belongs to the project above it, as always. Any other
folder inside a project's .critic (the briefs folder a lead cd'd into: run report N1) does too, but only when that
.critic is Curmudgeon's own, so a project kept under a folder named .critic (~/.critic/projects/app) stays itself."""
import os, re

SCRATCH = re.compile(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$")  # leftmost, as before: a copy's own nested .critic never counts
MARKS = ("ledger.json", "runlog.jsonl", "change-map.json", "plan.json", "briefs", "reviews", "scratch")  # what a run leaves in .critic

def project_of(cwd):
    cwd = str(cwd)
    if SCRATCH.search(cwd): return SCRATCH.sub("", cwd) or cwd
    if os.path.isdir(os.path.join(cwd, ".critic")): return cwd  # the folder holds its own .critic: it is the project
    m = re.match(r"^(.*)[\\/]\.critic(?:[\\/].*)?$", cwd)  # greedy: the last .critic in the path
    if m and m.group(1):
        state = os.path.join(m.group(1), ".critic")
        if any(os.path.exists(os.path.join(state, x)) for x in MARKS): return m.group(1)
    return cwd
