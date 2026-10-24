#!/usr/bin/env python3
"""One command for the scripted half of a Curmudgeon review (SC-31). It reads where the run stands, runs the next
scripted step itself, and prints what the lead must do next: which agents to start, with which files. The counting stays
in critic_merge.py and the ledger; the models still write the reviews, the dedup groups and the verdicts.

usage:
  critic_run.py begin [--tier trivial|lite|full] [--base GIT_REF] [--files PATH ...] [--intent TEXT]
        start a run (critic_ledger.py start) and map the change (critic_map.py); prints the reviewers to start
  critic_run.py next
        look at the run and do the next step: the first tally, the tally with the dedup groups, or apply (verdict files
        go in .critic/verdicts/*.json); prints the next agents to start, or that the teardown can be written
  critic_run.py status
        say where the run stands, change nothing

Steps it never takes: starting agents (only the lead can), writing a review or a verdict, or deciding anything a model
decides. Each script it runs is logged in .critic/runlog.jsonl like any other."""
import json, os, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT", os.getcwd())).resolve(); D = ROOT / ".critic"
REVIEWERS = {"trivial": ["A"], "lite": ["A"], "full": ["A", "B", "C"]}

def sh(script, *a):
    r = subprocess.run([sys.executable, str(HERE / script), *a], cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
    if r.returncode not in (0, 3): sys.exit(f"critic_run: {script} {' '.join(a)} failed (exit {r.returncode}); fix that, then run next again")
    return r

def ledger():
    try: return json.loads((D / "ledger.json").read_text())
    except (OSError, ValueError): return {}

def mtime(p): return p.stat().st_mtime if p.exists() else 0

def state():
    L = ledger(); tier = L.get("tier") or "full"
    started = L.get("started_at") or 0
    if not started or mtime(D / "last-review.md") >= started: return "idle", L, tier, []
    letters = REVIEWERS.get(tier, REVIEWERS["full"])
    reviews = [D / "reviews" / f"review-{x}.json" for x in letters]
    have = [p for p in reviews if p.exists() and mtime(p) >= started - 2]
    if len(have) < len(reviews): return "reviewing", L, tier, [p for p in reviews if p not in have]
    tally, groups = D / "tally.json", D / "groups.json"
    if mtime(tally) < max(mtime(p) for p in reviews): return "tally", L, tier, reviews
    cands = D / "dedup-candidates.json"
    try: listed = json.loads(cands.read_text() or "{}").get("findings_by_file") or {} if cands.exists() and mtime(cands) >= started else {}
    except (OSError, ValueError): listed = {}
    need_dedup = sum(len(v) for v in listed.values()) > 1  # the merge script's own rule: one issue has nothing to group with
    if need_dedup and mtime(groups) < mtime(cands): return "dedup", L, tier, [cands]
    if need_dedup and mtime(tally) < mtime(groups): return "tally-groups", L, tier, reviews
    verdicts = sorted((D / "verdicts").glob("*.json")) if (D / "verdicts").is_dir() else []
    packets = sorted((D / "verify").glob("*.json")) if (D / "verify").is_dir() else []
    if packets and not [v for v in verdicts if mtime(v) >= mtime(tally)]: return "verify", L, tier, packets
    if mtime(D / "findings.jsonl") < max([mtime(tally)] + [mtime(v) for v in verdicts]): return "apply", L, tier, verdicts
    return "teardown", L, tier, []

def say_next(st, tier, items):
    rel = lambda p: str(p.relative_to(ROOT))
    if st == "reviewing":
        print(f"next: start {len(items)} curmudgeon:curmudgeon-reviewer agent(s) by name (never a fork), blind, one per letter: "
              + ", ".join(p.stem[-1] for p in items) + ". Each writes " + ", ".join(rel(p) for p in items) + " (A ranked, B reversed, C shuffled).")
    elif st == "dedup": print(f"next: start curmudgeon:curmudgeon-dedup on {rel(items[0])}; it writes .critic/groups.json. Then run critic_run.py next.")
    elif st == "verify":
        batches = [items[i:i + 5] for i in range(0, len(items), 5)]
        print(f"next: start {len(batches)} curmudgeon:curmudgeon-verifier agent(s), blind, on these packets (save each agent's ```json verdict list as .critic/verdicts/<n>.json):")
        for i, b in enumerate(batches, 1): print(f"  verifier {i}: " + " ".join(rel(p) for p in b))
    elif st == "teardown": print("next: write the teardown from .critic/counts.md (references/output-contract.md), save .critic/last-review.md, then critic_ledger.py stamp <payload>.")
    elif st == "idle": print("next: no run is active; critic_run.py begin starts one.")

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    cmd, rest = a[0], a[1:]
    if cmd == "begin":
        tier = rest[rest.index("--tier") + 1] if "--tier" in rest and rest.index("--tier") + 1 < len(rest) else ""
        map_args = [x for i, x in enumerate(rest) if not (x == "--tier" or (i and rest[i - 1] == "--tier"))]
        sh("critic_map.py", *map_args)
        if not tier:
            try: tier = json.loads((D / "change-map.json").read_text()).get("tier") or "full"
            except (OSError, ValueError): tier = "full"
        sh("critic_ledger.py", "start", "review", "--tier", tier)
        st, L, tier, items = state(); say_next(st, tier, items); return 0
    if cmd == "status":
        st, L, tier, items = state(); print(f"run {L.get('run', 0)}, tier {tier}, round {L.get('round', 0)}: {st}"); say_next(st, tier, items); return 0
    if cmd == "next":
        st, L, tier, items = state()
        letters = [f".critic/reviews/review-{x}.json" for x in REVIEWERS.get(tier, REVIEWERS["full"])]
        if st == "tally":
            sh("critic_merge.py", "tally", *letters); st, L, tier, items = state()
        elif st == "tally-groups":
            sh("critic_merge.py", "tally", *letters, "--groups", ".critic/groups.json"); st, L, tier, items = state()
        elif st == "apply":
            sh("critic_ledger.py", "acted"); sh("critic_merge.py", "apply", *[str(p.relative_to(ROOT)) for p in items]); st, L, tier, items = state()
        say_next(st, tier, items); return 0
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
