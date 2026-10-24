#!/usr/bin/env python3
"""One command for the scripted half of a Curmudgeon review (SC-31). It reads where the run stands, runs the next
scripted step itself, and prints what the lead must do next: which agents to start, with which files. The counting stays
in critic_merge.py and the ledger; the models still write the reviews, the dedup groups and the verdicts.

usage:
  critic_run.py begin [--audit] [--tier trivial|lite|full] [--base GIT_REF] [--files PATH ...] [--intent TEXT]
        start a run (critic_ledger.py start) and map the change (critic_map.py); prints the reviewers to start
  critic_run.py next [--apply-now]
        look at the run and do the next step: the first tally, the tally with the dedup groups, or apply (verdict files
        go in .critic/verdicts/*.json); prints the next agents to start, or that the teardown can be written
  critic_run.py status
        say where the run stands, change nothing

Steps it never takes: starting agents (only the lead can), writing a review or a verdict, or deciding anything a model
decides. Each script it runs is logged in .critic/runlog.jsonl like any other."""
import json, os, pathlib, subprocess, sys, re, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
REVIEWERS = {"trivial": ["A"], "lite": ["A"], "full": ["A", "B", "C"]}
FORCE = False  # next --apply-now: apply with the verdicts there are (a finding with no verdict stays, at lower confidence)

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
    newest_review = max(mtime(p) for p in reviews)
    if need_dedup and mtime(groups) < newest_review: return "dedup", L, tier, [cands]  # tally rewrites the candidates every time, so the groups are judged against the reviews
    if need_dedup and mtime(tally) < mtime(groups): return "tally-groups", L, tier, reviews
    verdicts = sorted((D / "verdicts").glob("*.json")) if (D / "verdicts").is_dir() else []
    fresh = [v for v in verdicts if mtime(v) >= mtime(tally)]  # a verdict file older than this tally is from an earlier one: never applied
    packets = sorted((D / "verify").glob("*.json")) if (D / "verify").is_dir() else []
    covered = set()
    for v in fresh:
        try: rows = json.loads(v.read_text())
        except (OSError, ValueError): continue
        covered |= {str(r.get("id")) for r in (rows if isinstance(rows, list) else [rows]) if isinstance(r, dict)}
    try: t = json.loads(tally.read_text())
    except (OSError, ValueError): t = {}
    contested = {str(f.get("id")) for f in t.get("contested", []) if isinstance(f, dict)}
    outside = {str(f.get("id")) for f in t.get("kept", []) + t.get("contested", []) if isinstance(f, dict) and f.get("outside_only")}
    def wanted(p):  # the review skill's step 4.2: what each tier verifies
        if tier == "full" or p.stem in outside or p.stem in contested: return True  # step 4.1: contested findings are verified in every tier
        if tier == "trivial": return p.stem in contested
        try: return json.loads(p.read_text()).get("impact") in ("Critical", "High")
        except (OSError, ValueError): return True
    missing = [p for p in packets if p.stem not in covered and wanted(p)]
    if missing and not FORCE: return "verify", L, tier, missing
    if mtime(D / "findings.jsonl") < max([mtime(tally)] + [mtime(v) for v in fresh]): return "apply", L, tier, fresh
    return "teardown", L, tier, []

def say_next(st, tier, items):
    rel = lambda p: str(p.relative_to(ROOT))
    if st == "reviewing":
        print(f"next: start {len(items)} curmudgeon:curmudgeon-reviewer agent(s) by name (never a fork), blind, one per letter: "
              + ", ".join(p.stem[-1] for p in items) + ". Give each the text of its brief, unchanged, as its prompt: " + ", ".join(f".critic/briefs/brief-{p.stem[-1]}.md" for p in items) + ". Each writes " + ", ".join(rel(p) for p in items) + ".")
    elif st == "dedup": print(f"next: start curmudgeon:curmudgeon-dedup on {rel(items[0])}; it writes .critic/groups.json. Then run critic_run.py next.")
    elif st == "verify":
        batches = [items[i:i + 5] for i in range(0, len(items), 5)]
        print(f"next: start {len(batches)} curmudgeon:curmudgeon-verifier agent(s), blind, on these packets without a verdict yet (save each agent's ```json verdict list as .critic/verdicts/<n>.json, a new n each time); "
              "then critic_run.py next. If a verifier can't answer, critic_run.py next --apply-now applies what there is (a finding with no verdict stays, at lower confidence):")
        for i, b in enumerate(batches, 1): print(f"  verifier {i}: " + " ".join(rel(p) for p in b))
    elif st == "teardown": print("next: write the teardown from .critic/counts.md (references/output-contract.md), save .critic/last-review.md, then critic_ledger.py stamp <payload>.")
    elif st == "idle": print("next: no run is active; critic_run.py begin starts one.")

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    cmd, rest = a[0], a[1:]
    if cmd == "begin":
        audit = "--audit" in rest; rest = [x for x in rest if x != "--audit"]
        tier = rest[rest.index("--tier") + 1] if "--tier" in rest and rest.index("--tier") + 1 < len(rest) else ""
        if audit:
            tier = "full"
            print("audit mode (someone else's system): audit, not repair; nothing is changed. Rules of engagement:")
            print("  - active checks beyond this computer only for origins in .critic/scope.json, confirmed per run with --allow-live HOST" + (" (scope.json present)" if (D / "scope.json").is_file() else " (no scope.json: nothing beyond this computer is loaded)"))
            print("  - every requirement is stated (with its file:line) or inferred (capped at Medium)")
            print("  - findings carry difficulty, an exploit scenario, a short-term and a long-term fix")
            if (ROOT / ".mcp.json").is_file():
                print("  - WARNING: this repository ships .mcp.json. Its servers start without a prompt in claude -p, SDK and cloud runs: "
                      "audit it with --strict-mcp-config, or block them with disabledMcpjsonServers, before running anything headless here.")
        map_args = [x for i, x in enumerate(rest) if not (x == "--tier" or (i and rest[i - 1] == "--tier"))]
        sh("critic_map.py", *map_args)
        sh("critic_plan.py")  # SC-69: the job plan (tier, agents, lenses, expected cost); the user may change it
        if not tier:
            try: tier = json.loads((D / "plan.json").read_text()).get("tier") or "full"
            except (OSError, ValueError): tier = "full"
        sh("critic_ledger.py", "start", "review", "--tier", tier)
        sh("critic_brief.py", "--letters", ",".join(REVIEWERS.get(tier, REVIEWERS["full"])))
        files = [str(f) for f in (json.loads((D / "change-map.json").read_text()).get("files") or [])] if (D / "change-map.json").exists() else []
        only = ""
        if files and not (D / "scan-only.txt").is_symlink():
            (D / "scan-only.txt").write_text("\n".join(files) + "\n", encoding="utf-8"); only = " --only .critic/scan-only.txt"
        print(f"now, in the background (Bash with run_in_background), while the reviewers work: python3 {HERE / 'critic_scan.py'} . --root .{only} "
              "(add --page <page> for a UI). Reviewers can't read its output (their private copies and the read guard), so it no longer waits for them.")
        st, L, tier, items = state(); say_next(st, tier, items); return 0
    if cmd == "status":
        st, L, tier, items = state(); print(f"run {L.get('run', 0)}, tier {tier}, round {L.get('round', 0)}: {st}"); say_next(st, tier, items); return 0
    if cmd == "next":
        global FORCE; FORCE = "--apply-now" in rest
        st, L, tier, items = state()
        letters = [f".critic/reviews/review-{x}.json" for x in REVIEWERS.get(tier, REVIEWERS["full"])]
        for _ in range(4):  # run the scripted steps back to back until one needs an agent (or the teardown)
            if st == "tally":
                sh("critic_merge.py", "tally", *letters)
            elif st == "tally-groups":
                sh("critic_merge.py", "tally", *letters, "--groups", ".critic/groups.json")
            elif st == "apply":
                if not items:  # nothing needed a verdict, or --apply-now with none back: apply with an empty verdict list
                    (D / "verdicts").mkdir(exist_ok=True); none = D / "verdicts" / f"none-{int(time.time())}.json"; none.write_text("[]\n"); items = [none]
                sh("critic_ledger.py", "acted"); sh("critic_merge.py", "apply", *[str(p.relative_to(ROOT)) for p in items])
            else: break
            st, L, tier, items = state()
        say_next(st, tier, items); return 0
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
