#!/usr/bin/env python3
"""One command for the scripted half of a Curmudgeon review (SC-31). It reads where the run stands, runs the next
scripted step itself, and prints what the lead must do next: which agents to start, with which files. The counting stays
in critic_merge.py and the ledger; the models still write the reviews, the dedup groups and the verdicts.

usage:
  critic_run.py begin [--audit | --fix] [--security] [--tier trivial|lite|full] [--base GIT_REF] [--files PATH ...] [--intent TEXT]
        start a run (critic_ledger.py start) and map the change (critic_map.py); prints the reviewers to start. --fix
        records a full-mode run (review and fix), so the stop gate holds open Critical and High findings to it.
        --security is the security scan mode (5.2): the tier's panel, security lenses and focus only, and the feed step
  critic_run.py next [--apply-now] [--no-scan]
        look at the run and do the next step: the first tally, the tally with the dedup groups, or apply (the stop hook
        saves each verifier's verdicts in .critic/verdicts/); prints the next agents to start, or that the teardown can
        be written. Both tallies get the scan's report and the outside review when they exist (§5.56); the tally waits
        for this run's scan report, and --no-scan goes on without it, which marks the run DEGRADED
  critic_run.py status
        say where the run stands, change nothing
  critic_run.py early
        the scripted checks' FAIL rows, as soon as the background scan has written its report (SC-80, fastest results
        first): show them to the user while the reviewers work; they are scripted, not yet reviewed, and the teardown
        repeats them. Prints each scan report once; `next` prints it too if nobody has yet

Steps it never takes: starting agents (only the lead can), writing a review or a verdict, or deciding anything a model
decides. Each script it runs is logged in .critic/runlog.jsonl like any other."""
import json, os, pathlib, subprocess, sys, re, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
REVIEWERS = {"trivial": ["A"], "lite": ["A"], "full": ["A", "B", "C"]}
VERIFY_BATCH = 5  # packets per verifier agent; 10 (SC-78) was measured and reverted: no saving, quality worse (03 §5.37)
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

SCAN, OUTSIDE, NO_SCAN = D / "scan" / "report.json", D / "outside" / "outside-review.json", D / "scan-skipped"

def scan_cmd():
    """The scan command for this run, as begin prints it: limited to the change's files (scan-only.txt) and to security in
    the security scan mode, so a scan started later (a new round) covers the same ground (§5.56 round 3)."""
    only = " --only .critic/scan-only.txt" if (D / "scan-only.txt").is_file() and not (D / "scan-only.txt").is_symlink() else ""
    try: sec = json.loads((D / "focus.json").read_text()).get("focus") == "security" if (D / "focus.json").is_file() else False
    except (OSError, ValueError): sec = False
    return f"python3 {HERE / 'critic_scan.py'} . --root .{only}{' --focus security' if sec else ''}"

def is_fresh(p, started): return p.is_file() and not p.is_symlink() and mtime(p) >= started

def tally_extra(started, reviews=()):
    """What a tally gets besides the reviews (§5.56): the scan's FAILs and the outside review, when this run has them,
    and the dedup agent's groups when they were made for these reviews. A scan or an outside answer that arrives after
    the dedup step reruns the tally; without the groups that rerun would drop every issue the dedup agent merged."""
    extra = ["--scan", str(SCAN.relative_to(ROOT))] if is_fresh(SCAN, started) else ["--no-scan"]
    extra += ["--outside", str(OUTSIDE.relative_to(ROOT))] if is_fresh(OUTSIDE, started) else []
    G = D / "groups.json"
    if is_fresh(G, started) and reviews and mtime(G) >= max(mtime(p) for p in reviews): extra += ["--groups", str(G.relative_to(ROOT))]
    return extra

def state():
    L = ledger(); tier = L.get("tier") or "full"
    started = L.get("started_at") or 0
    if not started or mtime(D / "last-review.md") >= started: return "idle", L, tier, []
    letters = REVIEWERS.get(tier, REVIEWERS["full"])
    reviews = [D / "reviews" / f"review-{x}.json" for x in letters]
    have = [p for p in reviews if p.exists() and mtime(p) >= started - 2]
    if len(have) < len(reviews): return "reviewing", L, tier, [p for p in reviews if p not in have]
    tally, groups = D / "tally.json", D / "groups.json"
    if not is_fresh(SCAN, started) and not is_fresh(NO_SCAN, started): return "scan", L, tier, []  # scanner FAILs are findings: never tally without them unless told to
    inputs = reviews + [p for p in (SCAN, OUTSIDE) if is_fresh(p, started)]
    if mtime(tally) < max(mtime(p) for p in inputs): return "tally", L, tier, reviews
    cands = D / "dedup-candidates.json"
    try: listed = json.loads(cands.read_text() or "{}").get("findings_by_file") or {} if cands.exists() and mtime(cands) >= started else {}
    except (OSError, ValueError): listed = {}
    need_dedup = sum(len(v) for v in listed.values()) > 1  # the merge script's own rule: one issue has nothing to group with
    newest_review = max(mtime(p) for p in reviews + ([OUTSIDE] if is_fresh(OUTSIDE, started) else []))  # a late outside answer brings new candidates: the dedup agent judges them too (SKILL.md 3b)
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
    found = {str(f.get("id")): f for f in t.get("kept", []) + t.get("contested", []) if isinstance(f, dict)}
    from critic_findings import verdict_required
    def wanted(p):  # the review skill's step 4.2: what each tier verifies (one rule, shared with apply)
        return p.stem not in found or verdict_required(tier, found[p.stem], p.stem in contested)
    missing = [p for p in packets if p.stem not in covered and wanted(p)]
    if missing and not FORCE: return "verify", L, tier, missing
    if mtime(D / "findings.jsonl") < max([mtime(tally)] + [mtime(v) for v in fresh]): return "apply", L, tier, fresh
    return "teardown", L, tier, []

def early(force=False):
    """The scan's FAIL rows, once per scan report (SC-80). Returns True when it printed something."""
    rp = D / "scan" / "report.json"; mark = D / "early-shown"
    L = ledger(); started = L.get("started_at") or 0
    if not rp.is_file() or mtime(rp) < started: return False
    try: shown = float(mark.read_text().strip() or 0)
    except (OSError, ValueError): shown = 0
    if not force and shown >= mtime(rp): return False
    try: j = json.loads(rp.read_text())
    except (OSError, ValueError): return False
    fails = [x for x in j.get("findings", []) if x.get("sev") == "FAIL"]
    deg = j.get("degraded") or []
    print(f"early results (scripted checks, not yet reviewed; the teardown repeats them): {len(fails)} FAIL" + (f"; could not run: {', '.join(deg)}" if deg else ""))
    for x in fails[:10]: print(f"  - {x.get('id', '')} {x.get('where', '')}: {x.get('what', '')}")
    if len(fails) > 10: print(f"  - and {len(fails) - 10} more in .critic/scan/report.md")
    if not mark.is_symlink(): mark.write_text(str(mtime(rp)) + "\n")
    return True

def say_next(st, tier, items):
    rel = lambda p: str(p.relative_to(ROOT))
    if st == "scan":
        print(f"next: the scripted checks have not written a report for this run (or round) yet. If the background scan is running, wait for it; if none was started "
              f"(a new round, say), run it now: {scan_cmd()} Then run critic_run.py next again. "
              "Only if it can't run at all: critic_run.py next --no-scan goes on without it, and the counts say the run is DEGRADED.")
    elif st == "reviewing":
        print(f"next: start {len(items)} curmudgeon:curmudgeon-reviewer agent(s) by name (never a fork), blind, one per letter: "
              + ", ".join(p.stem[-1] for p in items) + ". Give each the text of its brief, unchanged, as its prompt: " + ", ".join(f".critic/briefs/brief-{p.stem[-1]}.md" for p in items) + ". Each writes " + ", ".join(rel(p) for p in items) + ".")
    elif st == "dedup": print(f"next: start curmudgeon:curmudgeon-dedup on {rel(items[0])}; it writes .critic/groups.json. Then run critic_run.py next.")
    elif st == "verify":
        batches = [items[i:i + VERIFY_BATCH] for i in range(0, len(items), VERIFY_BATCH)]
        print(f"next: start {len(batches)} curmudgeon:curmudgeon-verifier agent(s), blind, on these packets without a verdict yet (each verifier's ```json verdict list is saved in .critic/verdicts/ by the stop hook, unchanged; don't copy verdicts yourself); "
              "then critic_run.py next. If a verifier can't answer, critic_run.py next --apply-now applies what there is (a finding with no verdict stays, at lower confidence):")
        for i, b in enumerate(batches, 1): print(f"  verifier {i}: " + " ".join(rel(p) for p in b))
    elif st == "teardown":
        print("next: write the teardown from .critic/counts.md (references/output-contract.md), save .critic/last-review.md, then critic_ledger.py stamp <payload>.")
    elif st == "idle": print("next: no run is active; critic_run.py begin starts one.")

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    cmd, rest = a[0], a[1:]
    if cmd in ("begin", "next"):
        from critic_findings import refuse_linked_state; refuse_linked_state(ROOT)
    if cmd == "begin":
        audit = "--audit" in rest; fix = "--fix" in rest and not audit; security = "--security" in rest
        rest = [x for x in rest if x not in ("--audit", "--fix", "--security")]
        D.mkdir(parents=True, exist_ok=True); fp = D / "focus.json"
        if fp.is_symlink(): sys.exit("critic_run: .critic/focus.json is a link; refusing")
        if security: fp.write_text(json.dumps({"focus": "security"}) + "\n")
        elif fp.exists(): fp.unlink()  # a plain run never inherits an earlier run's focus
        tier = rest[rest.index("--tier") + 1] if "--tier" in rest and rest.index("--tier") + 1 < len(rest) else ""
        if audit:
            tier = "full"
            mine = D / "audit-owner.json"  # written by an earlier begin --audit here: that ledger is ours, unless the repository shipped the marker
            shipped = subprocess.run(["git", "ls-files", "--error-unmatch", ".critic/audit-owner.json"], cwd=ROOT, capture_output=True).returncode == 0
            ours = mine.is_file() and not mine.is_symlink() and not shipped
            foreign = [n for n in ("ledger.json", "ledger.md", "decisions.md", "scope.json") if (D / n).is_file()] if not ours else []
            if foreign:  # the audited repository's own records are its owner's, not the auditor's: never their decisions, rulings or scope
                aside = D / "history" / ("audited-repo-" + time.strftime("%Y%m%d-%H%M%S")); aside.mkdir(parents=True, exist_ok=True)
                for n in foreign: (D / n).rename(aside / n)
                print(f"set aside the audited repository's own {', '.join(foreign)} (moved to {aside.relative_to(ROOT)}): its decisions, false-positive rulings and scope are its owner's, not yours. Write your own .critic/scope.json for any live checks.")
            D.mkdir(parents=True, exist_ok=True); mine.write_text(json.dumps({"audit_started": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
            print("audit mode (someone else's system): audit, not repair; nothing is changed. Rules of engagement:")
            print("  - active checks beyond this computer only for origins in .critic/scope.json, confirmed per run with --allow-live HOST" + (" (scope.json present)" if (D / "scope.json").is_file() else " (no scope.json: nothing beyond this computer is loaded)"))
            print("  - every requirement is stated (with its file:line) or inferred (capped at Medium)")
            print("  - findings carry difficulty, an exploit scenario, a short-term and a long-term fix")
            if (ROOT / ".mcp.json").is_file():
                print("  - WARNING: this repository ships .mcp.json. Its servers start without a prompt in claude -p, SDK and cloud runs: "
                      "audit it with --strict-mcp-config, or block them with disabledMcpjsonServers, before running anything headless here.")
        map_args = [x for i, x in enumerate(rest) if not (x == "--tier" or (i and rest[i - 1] == "--tier"))]
        sh("critic_map.py", *map_args)
        sh("critic_plan.py", *(["--tier", tier] if tier else []))  # SC-69: the job plan (tier, agents, lenses, expected cost), showing the tier in force
        if not tier:
            try: tier = json.loads((D / "plan.json").read_text()).get("tier") or "full"
            except (OSError, ValueError): tier = "full"
        sh("critic_ledger.py", "start", "audit" if audit else ("full" if fix else "review"), "--tier", tier)
        sh("critic_brief.py", "--letters", ",".join(REVIEWERS.get(tier, REVIEWERS["full"])))
        files = [str(f) for f in (json.loads((D / "change-map.json").read_text()).get("files") or [])] if (D / "change-map.json").exists() else []
        only = ""
        if files and not (D / "scan-only.txt").is_symlink():
            (D / "scan-only.txt").write_text("\n".join(files) + "\n", encoding="utf-8"); only = " --only .critic/scan-only.txt"
        if security:
            r = subprocess.run([sys.executable, str(HERE / "security_feed.py"), "status"], capture_output=True, text=True)
            print(r.stdout.strip().splitlines()[0] if r.stdout.strip() else "security feed: status unreadable")
            print(f"  feed step (03 §5.38, §5.40), only if it says never switched on and the user is present; never ask unattended (it stays off): "
                  f"1. ask once, default off: \"Build a local security database (OSV and CISA's exploited list) so dependency checks send nothing about your project?\" No: python3 {HERE / 'security_feed.py'} set --cadence off. "
                  f"2. python3 {HERE / 'security_feed.py'} pick-folder opens a folder window (prints the path; NO_WINDOW means ask for the full path instead). "
                  f"3. python3 {HERE / 'security_feed.py'} estimate --folder <folder> (a size-only request to each source) and show the user the estimate. "
                  f"4. ask them to sign off on that size and pick a schedule (daily, weekly, biweekly, monthly). "
                  f"5. python3 {HERE / 'security_feed.py'} set --cadence <schedule> --folder <folder> --signed-off <bytes>, then python3 {HERE / 'security_feed.py'} update. "
                  f"If it is already on and due: python3 {HERE / 'security_feed.py'} update (exit 5 means the database grew past the signed-off size: show the new estimate and ask again)")
            only += " --focus security"
        print(f"now, in the background (Bash with run_in_background), while the reviewers work: python3 {HERE / 'critic_scan.py'} . --root .{only} "
              "(add --page <page> for a UI). Reviewers can't read its output (their private copies and the read guard), so it no longer waits for them.")
        st, L, tier, items = state(); say_next(st, tier, items); return 0
    if cmd == "early":
        if not early(force=True): print("early results: the scan has not written its report for this run yet")
        return 0
    if cmd == "status":
        st, L, tier, items = state(); print(f"run {L.get('run', 0)}, tier {tier}, round {L.get('round', 0)}: {st}"); say_next(st, tier, items); return 0
    if cmd == "next":
        global FORCE; FORCE = "--apply-now" in rest
        if "--no-scan" in rest and not NO_SCAN.is_symlink(): D.mkdir(parents=True, exist_ok=True); NO_SCAN.write_text("the tally went on without the scan (critic_run.py next --no-scan)\n")
        early()  # fastest results first: the scan's FAILs as soon as they exist, once
        st, L, tier, items = state()
        letters = [f".critic/reviews/review-{x}.json" for x in REVIEWERS.get(tier, REVIEWERS["full"])]
        for _ in range(4):  # run the scripted steps back to back until one needs an agent (or the teardown)
            if st == "tally":
                sh("critic_merge.py", "tally", *letters, *tally_extra(L.get("started_at") or 0, [ROOT / x for x in letters]))
            elif st == "tally-groups":
                sh("critic_merge.py", "tally", *letters, *tally_extra(L.get("started_at") or 0, [ROOT / x for x in letters]))
            elif st == "apply":
                if not items:  # nothing needed a verdict, or --apply-now with none back: apply with an empty verdict list
                    (D / "verdicts").mkdir(exist_ok=True); none = D / "verdicts" / f"none-{int(time.time())}.json"; none.write_text("[]\n"); items = [none]
                sh("critic_ledger.py", "acted"); sh("critic_merge.py", "apply", *[str(p.relative_to(ROOT)) for p in items])
            else: break
            st, L, tier, items = state()
        say_next(st, tier, items); return 0
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
