#!/usr/bin/env python3
"""The death match (SC-70, rulings §5.8, §5.20, §5.22): a development-time benchmark that runs the same tasks, on the
same model, through Curmudgeon and through the alternatives, and scores every arm with one scorer. It is never part
of a review; nothing from another tool goes into the plugin through it.

usage:
  deathmatch.py plan  [--arms a,b] [--tasks t1,t2]           show what would run (no model calls)
  deathmatch.py run   --yes-spend [--arms ...] [--tasks ...] [--model ID] [--repeat N]
                                                              run it (model calls cost money: --yes-spend is required)
  deathmatch.py score RUN_DIR                                 score a finished run again (labels added since included)

Tasks come from eval/deathmatch.json: each names a fixture and its answer key (planted defects with file and regex),
or marks the fixture a clean twin (every reported issue there is a false alarm). Arms are headless `claude -p` runs
with a prompt, a tool list and, for Curmudgeon, the plugin folder; a specialist arm (Semgrep, say) is a command that
runs only if the tool is already installed, and is scored only on the tasks it claims.

One scorer for every arm: the output is split into finding blocks (Curmudgeon's findings.jsonl rows when present;
otherwise list items and headed sections of the reply), and every block has the same two parts for every arm: where
it points (file:line and any quoted code) and what it claims (file:line, title and failing case; in a free-form reply,
the item with its Fix:/Remediation: text removed). A plant is credited only when its file is where the block points and
its pattern is in the claim, never in fix advice (each block credits one plant, each plant once). On a clean twin a
block that cites a file:line, or that someone labelled false, is a false alarm; a heading or a "no issues" line is not.
Other blocks are UNLABELLED until someone labels them in RUN_DIR/labels.json ({"<arm>/<task>/<block n>":
"real"|"false"}), and precision is NOT MEASURED while any are unlabelled: nothing is guessed. A run that failed, timed
out or wrote nothing is shown with its error and scored NOT MEASURED, never as a clean result. Cost, tokens and wall
time come from Claude Code's own JSON result. Results: RUN_DIR/results.json and RUN_DIR/report.md."""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugin"
CFG = HERE / "deathmatch.json"

def load_cfg(): return json.loads(CFG.read_text())

def pick(items, names):
    if not names: return items
    want = set(names.split(","))
    return [x for x in items if x["id"] in want]

def blocks_from(text):
    """Finding blocks from a free-form review: top-level list items and headed sections, each with its text."""
    lines = text.split("\n"); out = []; cur = []
    for l in lines:
        if re.match(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+\S", l) or re.match(r"^#{2,6}\s+\S", l):
            if cur and "".join(cur).strip(): out.append("\n".join(cur))
            cur = [l]
        elif cur: cur.append(l)
    if cur and "".join(cur).strip(): out.append("\n".join(cur))
    keep = [b for b in out if re.search(r"[\w./-]+\.\w+(:\d+)?", b) or re.search(r"(?i)\b(bug|defect|issue|vulnerab|incorrect|wrong|fails?|leak|race|inject)", b)]
    return keep

CITES = re.compile(r"[\w./-]+\.\w+:\d+")
FIX = re.compile(r"(?im)(?:^\s*(?:[-*+]\s*)?|\s)(?:\*\*)?(?:suggested\s+fix|fix(?:ed)?|remediation|recommendation|solution|to fix|how to fix|mitigation)(?:\*\*)?\s*:.*$")

def blocks_for(arm_dir):
    """[{"loc": where the block points, "claim": what it says is wrong}], the same two parts for every arm; None when
    the arm wrote nothing at all."""
    fj = arm_dir / "findings.jsonl"
    if fj.exists():
        rows = [json.loads(x) for x in fj.read_text().splitlines() if x.strip()]
        out = []
        for r in rows:
            at = f"{r.get('file', '')}:{r.get('line')}" if r.get("line") not in (None, "") else str(r.get("file", ""))
            out.append({"loc": f"{at} {r.get('quote', '')}", "claim": f"{at} {r.get('title', '')}. {r.get('failing_case', '')}"})
        return out
    md = arm_dir / "output.md"
    if not md.exists(): return None
    return [{"loc": b, "claim": FIX.sub("", b)} for b in blocks_from(md.read_text())]

def score_task(task, blocks, labels, prefix):
    if task.get("clean"):
        fa = [i for i, b in enumerate(blocks) if labels.get(f"{prefix}/{i}") == "false" or (CITES.search(b["loc"]) and labels.get(f"{prefix}/{i}") != "real")]
        return {"false_alarms": len(fa), "blocks": len(blocks)}
    key = json.loads((HERE / task["key"]).read_text())
    plants = key.get("planted") and {p["id"]: {"file": p["where"].split(":")[0], "any": [re.escape(p["rule"])]} for p in key["planted"]} or key
    hit, used = {}, set()
    for name, k in plants.items():
        for i, b in enumerate(blocks):
            if i in used: continue
            if (not k.get("file") or k["file"].lower() in b["loc"].lower()) and any(re.search(p, b["claim"], re.I) for p in k["any"]):
                hit[name] = i; used.add(i); break
    unl = [i for i in range(len(blocks)) if i not in used and f"{prefix}/{i}" not in labels]
    real = sum(1 for i in range(len(blocks)) if i not in used and labels.get(f"{prefix}/{i}") == "real")
    false = sum(1 for i in range(len(blocks)) if i not in used and labels.get(f"{prefix}/{i}") == "false")
    return {"recall": f"{len(hit)} of {len(plants)}", "found": len(hit), "plants": len(plants), "blocks": len(blocks), "unlabelled": len(unl),
            "precision": None if unl else (f"{len(hit) + real} of {len(hit) + real + false}" if (len(hit) + real + false) else "no findings")}

def score(run_dir):
    run_dir = pathlib.Path(run_dir); cfg = load_cfg()
    labels = json.loads((run_dir / "labels.json").read_text()) if (run_dir / "labels.json").exists() else {}
    tasks = {t["id"]: t for t in cfg["tasks"]}; res = []
    for arm_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        for td in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            tid = td.name.split("~")[0]
            if tid not in tasks: continue
            meta = json.loads((td / "meta.json").read_text()) if (td / "meta.json").exists() else {}
            blocks = blocks_for(td)
            err = meta.get("error") or ("the run reported an error (is_error)" if meta.get("is_error") else None) or (None if blocks is not None else "no output")
            if err: r = {"recall": "NOT MEASURED", "found": None, "precision": None, "false_alarms": None if tasks[tid].get("clean") else "-", "unlabelled": "-"}  # a failed run is never a clean result
            else: r = score_task(tasks[tid], blocks, labels, f"{arm_dir.name}/{td.name}")
            r.update(arm=arm_dir.name, task=td.name, cost_usd=meta.get("total_cost_usd"), wall_s=meta.get("wall_s"), tokens=meta.get("tokens"), error=err)
            res.append(r)
    (run_dir / "results.json").write_text(json.dumps(res, indent=1))
    md = ["# Death match results", "", "One scorer for every arm. Precision is NOT MEASURED while any block is unlabelled.", "",
          "| Arm | Task | Recall | False alarms (clean twin) | Unlabelled | Precision | Cost (USD) | Tokens | Wall (s) | Error |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        fa = r.get("false_alarms", "-"); fa = "NOT MEASURED" if fa is None else fa
        md.append(f"| {r['arm']} | {r['task']} | {r.get('recall', '-')} | {fa} | {r.get('unlabelled', '-')} | {r.get('precision') or 'NOT MEASURED' if 'precision' in r else '-'} | {r.get('cost_usd') if r.get('cost_usd') is not None else '?'} | {r.get('tokens') or '?'} | {r.get('wall_s') or '?'} | {(r.get('error') or '').replace('|', '/')[:80]} |")
    (run_dir / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md)); return 0

def plan(arms, tasks):
    print(f"{len(arms)} arm(s) x {len(tasks)} task(s) = {len(arms) * len(tasks)} run(s); every run is a headless Claude Code session that costs money.")
    for a in arms:
        avail = "" if not a.get("requires") or shutil.which(a["requires"]) else f"  (skipped: {a['requires']} is not installed; never installed for you)"
        print(f"- {a['id']}: {a.get('prompt') or a.get('command')}{avail}")
    for t in tasks: print(f"  task {t['id']}: {t['fixture']}" + (" (clean twin)" if t.get("clean") else f" key {t['key']}"))
    return 0

def one_run(a, w, td, model):
    """One arm on one task in the work folder w; returns its meta (an error is recorded, never raised past here except
    a timeout, which the caller records)."""
    if a.get("command"):
        r = subprocess.run(a["command"], shell=True, cwd=w, capture_output=True, text=True, timeout=1800)
        (td / "output.md").write_text(r.stdout); meta = {"exit": r.returncode}
        if r.returncode not in (0, 1): meta["error"] = f"exit {r.returncode}: {(r.stderr or '')[-200:]}"
        return meta
    cmd = ["claude", "-p", a["prompt"], "--output-format", "json", "--allowedTools", ",".join(a.get("tools", ["Read", "Grep", "Glob"]))]
    if model: cmd += ["--model", model]
    if a.get("plugin"): cmd += ["--plugin-dir", str(PLUGIN)]
    r = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=3600, stdin=subprocess.DEVNULL)
    try:
        j = json.loads(r.stdout); u = j.get("usage") or {}
        (td / "output.md").write_text(str(j.get("result") or ""))
        return {"total_cost_usd": j.get("total_cost_usd"), "tokens": sum(int(u.get(x) or 0) for x in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")),
                "is_error": j.get("is_error"), "num_turns": j.get("num_turns")}
    except ValueError: return {"error": (r.stderr or r.stdout)[-500:] or f"no result (exit {r.returncode})"}

def run(arms, tasks, model, repeat):
    out = HERE / "runs" / time.strftime("%Y-%m-%d-%H%M%S"); out.mkdir(parents=True)
    for a in arms:
        if a.get("requires") and not shutil.which(a["requires"]): print(f"skip {a['id']}: {a['requires']} not installed"); continue
        for t in tasks:
            if a.get("tasks") and t["id"] not in a["tasks"]: continue
            for k in range(repeat):
                td = out / a["id"] / (t["id"] + (f"~{k + 1}" if repeat > 1 else "")); td.mkdir(parents=True)
                with tempfile.TemporaryDirectory(prefix="dm-") as tmp:
                    w = pathlib.Path(tmp) / "work"; shutil.copytree(HERE / t["fixture"], w, ignore=shutil.ignore_patterns(".critic"))
                    subprocess.run(["git", "init", "-q"], cwd=w); subprocess.run(["git", "add", "."], cwd=w)
                    subprocess.run(["git", "-c", "user.email=dm@example.invalid", "-c", "user.name=dm", "commit", "-qm", "task"], cwd=w)
                    t0 = time.time()
                    try: meta = one_run(a, w, td, model)
                    except subprocess.TimeoutExpired as e: meta = {"error": f"timeout after {int(e.timeout)} s"}  # recorded; the other runs go on
                    meta["wall_s"] = round(time.time() - t0, 1)
                    for f_ in ("findings.jsonl", "last-review.md"):
                        if (w / ".critic" / f_).exists(): shutil.copy2(w / ".critic" / f_, td / f_)
                    (td / "meta.json").write_text(json.dumps(meta, indent=1))
                print(f"done {a['id']} / {td.name} ({meta.get('wall_s')} s)")
    return score(out)

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d
    if a[0] == "score": return score(a[1]) if len(a) > 1 else 2
    cfg = load_cfg(); arms = pick(cfg["arms"], opt("--arms")); tasks = pick(cfg["tasks"], opt("--tasks"))
    if a[0] == "plan": return plan(arms, tasks)
    if a[0] == "run":
        if "--yes-spend" not in a: print("refused: a run makes paid model calls; pass --yes-spend after checking `deathmatch.py plan`"); return 2
        return run(arms, tasks, opt("--model"), int(opt("--repeat", "1")))
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
