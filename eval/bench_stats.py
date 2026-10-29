#!/usr/bin/env python3
"""Statistics for the 5.2.4 benchmark (ruling §5.53), from one or more death-match run folders after scoring and
labelling (deathmatch.py score, label.py final). Nothing here calls a model.

usage: bench_stats.py RUN_DIR [RUN_DIR ...] [--out FILE.md] [--base ARM] [--seed N]

Per arm:
- completion: runs that finished, of runs made (a run voided by a usage limit and run again counts once);
- planted recall: plants found / plants, over the planted tasks, with a 95% bootstrap interval (runs resampled);
- independently assessed findings (every finding that matched no plant, labelled blind by two labellers and a
  tiebreaker): how many were labelled real, trivial and wrong, and the share confirmed real and actionable, overall
  and by severity (findings that are not findings at all, such as headings, are left out of every share);
- false alarms on the clean twins: the share of clean runs with at least one false alarm, with its 95% upper bound
  (the rule of three, 3/n, when none was seen; otherwise the exact Clopper-Pearson bound), and false alarms per run;
- cost per confirmed bug: total cost / (planted bugs found + findings confirmed real and actionable);
- median wall time, and the agent-launch rate (runs that started at least one subagent).
Paired comparisons: against --base (default curmudgeon), on the same task and repeat, the mean difference in
confirmed bugs per run and in cost per run, each with a 95% bootstrap interval."""
import json, math, pathlib, random, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deathmatch

B = 10000

def boot(values, f=statistics.fmean, seed=0):
    """95% percentile bootstrap interval of f over values (resampled with replacement); None when there are none."""
    if not values: return None
    rng = random.Random(seed); n = len(values)
    est = sorted(f([values[rng.randrange(n)] for _ in range(n)]) for _ in range(B))
    return est[int(0.025 * B)], est[int(0.975 * B) - 1]

def ratio_boot(pairs, seed=0):
    """Interval for sum(a)/sum(b) over [(a, b)] runs, resampling runs."""
    pairs = [p for p in pairs if p[1] is not None]
    if not pairs or not sum(b for _, b in pairs): return None
    return boot(pairs, lambda xs: sum(a for a, _ in xs) / (sum(b for _, b in xs) or math.nan), seed)

def upper95(k, n):
    """95% upper bound for a proportion with k of n: 3/n when k is 0 (the rule of three), else Clopper-Pearson."""
    if n == 0: return None
    if k == 0: return min(1.0, 3 / n)
    if k == n: return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):  # one-sided 97.5% bound by bisection on the binomial tail P(X <= k; p) = 0.025
        mid = (lo + hi) / 2
        tail = sum(math.comb(n, i) * mid ** i * (1 - mid) ** (n - i) for i in range(k + 1))
        lo, hi = (mid, hi) if tail > 0.025 else (lo, mid)
    return hi

def load(run_dirs):
    cfg = deathmatch.load_cfg(); tasks = {t["id"]: t for t in cfg["tasks"]}; runs = []
    for rd in map(pathlib.Path, run_dirs):
        res = json.loads((rd / "results.json").read_text())
        detail = (json.loads((rd / "labels-detail.json").read_text()) if (rd / "labels-detail.json").exists() else {}).get("labels", {})
        agree = (json.loads((rd / "labels-detail.json").read_text()) if (rd / "labels-detail.json").exists() else {}).get("agreement")
        voids = sum(1 for _ in open(rd / "voided.jsonl")) if (rd / "voided.jsonl").exists() else 0
        for r in res:
            tid, _, k = r["task"].partition("~"); t = tasks.get(tid) or {}
            meta = json.loads((rd / r["arm"] / r["task"] / "meta.json").read_text()) if (rd / r["arm"] / r["task"] / "meta.json").exists() else {}
            labs = [d for key, d in detail.items() if key.startswith(f"{r['arm']}/{r['task']}/")]
            runs.append({"dir": rd.name, "arm": r["arm"], "task": tid, "rep": int(k or 1), "clean": bool(t.get("clean")), "ok": not r.get("error"),
                         "found": r.get("found") or 0, "plants": r.get("plants"), "false_alarms": r.get("false_alarms"), "cost": r.get("cost_usd"),
                         "wall": r.get("wall_s"), "agents": meta.get("agents_launched"), "labels": labs, "unlabelled": r.get("unlabelled")})
        runs.append({"_agreement": agree, "_voids": voids, "dir": rd.name})
    return [r for r in runs if "arm" in r], [r for r in runs if "_agreement" in r]

def confirmed(r): return r["found"] + sum(1 for d in r["labels"] if d["verdict"] == "real" and d["actionable"])

def arm_stats(rs, seed):
    ok = [r for r in rs if r["ok"]]; planted = [r for r in ok if not r["clean"]]; clean = [r for r in ok if r["clean"]]
    labs = [d for r in ok for d in r["labels"] if d["verdict"] != "none"]
    real_act = [d for d in labs if d["verdict"] == "real" and d["actionable"]]
    by_sev = {s: sum(1 for d in real_act if d["severity"] == s) for s in ("critical", "high", "medium", "low")}
    fa_runs = sum(1 for r in clean if (r["false_alarms"] or 0) > 0)
    cost = sum(r["cost"] or 0 for r in ok); conf = sum(confirmed(r) for r in ok)
    agents = [r["agents"] for r in ok if r["agents"] is not None]
    return {
        "runs": len(rs), "completed": len(ok), "completion": round(len(ok) / len(rs), 3) if rs else None,
        "planted_found": sum(r["found"] for r in planted), "plants": sum(r["plants"] or 0 for r in planted),
        "recall": round(sum(r["found"] for r in planted) / sum(r["plants"] for r in planted), 3) if planted and sum(r["plants"] for r in planted) else None,
        "recall_ci": ratio_boot([(r["found"], r["plants"]) for r in planted], seed),
        "assessed": len(labs), "real": sum(1 for d in labs if d["verdict"] == "real"), "trivial": sum(1 for d in labs if d["verdict"] == "trivial"),
        "wrong": sum(1 for d in labs if d["verdict"] == "wrong"), "unlabelled": sum(r["unlabelled"] for r in ok if isinstance(r["unlabelled"], int)),
        "actionable_share": round(len(real_act) / len(labs), 3) if labs else None,
        "actionable_by_severity": {s: {"n": n, "share": round(n / len(labs), 3) if labs else None} for s, n in by_sev.items()},
        "clean_runs": len(clean), "clean_runs_with_false_alarm": fa_runs,
        "false_alarm_run_rate": round(fa_runs / len(clean), 3) if clean else None, "false_alarm_run_rate_upper95": round(upper95(fa_runs, len(clean)), 3) if clean else None,
        "false_alarms_per_clean_run": round(statistics.fmean(r["false_alarms"] or 0 for r in clean), 2) if clean else None,
        "cost_usd": round(cost, 2), "confirmed_bugs": conf, "cost_per_confirmed": round(cost / conf, 3) if conf else None,
        "cost_per_confirmed_ci": ratio_boot([(r["cost"] or 0, confirmed(r)) for r in ok], seed),
        "median_wall_s": statistics.median([r["wall"] for r in ok if r["wall"] is not None]) if ok else None,
        "agent_launch_rate": round(sum(1 for a in agents if a > 0) / len(agents), 3) if agents else None,
        "agents_per_run": round(statistics.fmean(agents), 1) if agents else None, "agent_counts_known": len(agents),
    }

def paired(runs, base, other, seed):
    key = lambda r: (r["dir"], r["task"], r["rep"])
    A = {key(r): r for r in runs if r["arm"] == base and r["ok"]}; O = {key(r): r for r in runs if r["arm"] == other and r["ok"]}
    both = sorted(set(A) & set(O))
    if not both: return None
    d_conf = [confirmed(A[k]) - confirmed(O[k]) for k in both]; d_cost = [(A[k]["cost"] or 0) - (O[k]["cost"] or 0) for k in both]
    return {"pairs": len(both), "confirmed_diff_mean": round(statistics.fmean(d_conf), 2), "confirmed_diff_ci": boot(d_conf, seed=seed),
            "cost_diff_mean": round(statistics.fmean(d_cost), 3), "cost_diff_ci": boot(d_cost, seed=seed),
            "base_better": sum(1 for x in d_conf if x > 0), "other_better": sum(1 for x in d_conf if x < 0), "tied": sum(1 for x in d_conf if x == 0)}

def fmt_ci(ci, nd=2): return "n/a" if not ci else f"{ci[0]:.{nd}f} to {ci[1]:.{nd}f}"

def report(run_dirs, base="curmudgeon", seed=0):
    runs, meta = load(run_dirs)
    arms = sorted({r["arm"] for r in runs}, key=lambda a: (a != base, a))
    S = {a: arm_stats([r for r in runs if r["arm"] == a], seed) for a in arms}
    P = {a: paired(runs, base, a, seed) for a in arms if a != base}
    md = ["# 5.2.4 benchmark statistics", "", f"Run folders: {', '.join(m['dir'] for m in meta)}. Runs voided by a usage limit and run again: {sum(m['_voids'] for m in meta)}.",
          "Labeller agreement: " + "; ".join(f"{m['dir']}: {m['_agreement']['agreed']} of {m['_agreement']['findings']} agreed, kappa {m['_agreement']['kappa_verdict']}" if m["_agreement"] else f"{m['dir']}: not labelled" for m in meta) + ".", "",
          "| Arm | Completed | Planted recall (95% CI) | Assessed findings: real / trivial / wrong | Real and actionable | Clean runs with a false alarm (95% upper) | Cost | Confirmed bugs | Cost per confirmed (95% CI) | Median time (s) | Runs that launched agents |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        s = S[a]
        md.append(f"| {a} | {s['completed']} of {s['runs']} | {s['planted_found']} of {s['plants']}" + (f" ({fmt_ci(s['recall_ci'])})" if s['recall_ci'] else "") +
                  f" | {s['real']} / {s['trivial']} / {s['wrong']}" + (f" ({s['unlabelled']} unlabelled)" if s['unlabelled'] else "") +
                  f" | {'n/a' if s['actionable_share'] is None else format(s['actionable_share'], '.0%')}"
                  f" | {s['clean_runs_with_false_alarm']} of {s['clean_runs']} ({'n/a' if s['false_alarm_run_rate_upper95'] is None else format(s['false_alarm_run_rate_upper95'], '.0%')})"
                  f" | ${s['cost_usd']:.2f} | {s['confirmed_bugs']} | {'n/a' if s['cost_per_confirmed'] is None else '$' + format(s['cost_per_confirmed'], '.3f')} ({fmt_ci(s['cost_per_confirmed_ci'], 3)})"
                  f" | {s['median_wall_s']} | {'unknown' if s['agent_launch_rate'] is None else format(s['agent_launch_rate'], '.0%')} ({s['agent_counts_known']} known) |")
    md += ["", "Real and actionable findings by severity (share of each arm's assessed findings):", "", "| Arm | Critical | High | Medium | Low |", "|---|---|---|---|---|"]
    for a in arms:
        sv = S[a]["actionable_by_severity"]
        md.append(f"| {a} | " + " | ".join(f"{sv[x]['n']}" + ("" if sv[x]["share"] is None else f" ({sv[x]['share']:.0%})") for x in ("critical", "high", "medium", "low")) + " |")
    md += ["", f"Paired against {base} (same task and repeat; positive means {base} found more or cost more):", "",
           "| Arm | Pairs | Confirmed bugs per run, difference (95% CI) | Runs: base better / other better / tied | Cost per run, difference (95% CI) |", "|---|---|---|---|---|"]
    for a, p in P.items():
        md.append(f"| {a} | n/a | n/a | n/a | n/a |" if not p else f"| {a} | {p['pairs']} | {p['confirmed_diff_mean']:+.2f} ({fmt_ci(p['confirmed_diff_ci'])}) | {p['base_better']} / {p['other_better']} / {p['tied']} | {p['cost_diff_mean']:+.3f} ({fmt_ci(p['cost_diff_ci'], 3)}) |")
    return "\n".join(md) + "\n", {"arms": S, "paired": P, "agreement": [m["_agreement"] for m in meta], "voided": sum(m["_voids"] for m in meta)}

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a else d
    dirs = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    md, js = report(dirs, opt("--base", "curmudgeon"), int(opt("--seed", "0")))
    if opt("--out"): pathlib.Path(opt("--out")).write_text(md); pathlib.Path(opt("--out")).with_suffix(".json").write_text(json.dumps(js, indent=1))
    print(md); return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
