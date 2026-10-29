#!/usr/bin/env python3
"""The death match (SC-70, rulings §5.8, §5.20, §5.22): a development-time benchmark that runs the same tasks, on the
same model, through Curmudgeon and through the alternatives, and scores every arm with one scorer. It is never part
of a review; nothing from another tool goes into the plugin through it.

usage:
  deathmatch.py plan  [--arms a,b] [--tasks t1,t2]           show what would run (no model calls)
  deathmatch.py run   --yes-spend [--arms ...] [--tasks ...] [--model ID] [--repeat N] [--parallel N] [--plugin DIR]
                                                              run it (model calls cost money: --yes-spend is required)
  deathmatch.py rerun RUN_DIR --yes-spend [--all-errors]     run again the runs a usage limit voided (with --all-errors,
                                                              every failed run); each voided result is kept in voided.jsonl
  deathmatch.py score RUN_DIR                                 score a finished run again (labels added since included)

Tasks come from eval/deathmatch.json: each names a fixture and its answer key (planted defects with file and regex),
or marks the fixture a clean twin (every reported issue there is a false alarm). Arms are headless `claude -p` runs
with a prompt, a tool list and, for Curmudgeon, the plugin folder; a specialist arm (Semgrep, say) is a command that
runs only if the tool is already installed, and is scored only on the tasks it claims.

One scorer for every arm: the output is split into finding blocks (Curmudgeon's findings.jsonl rows when present;
otherwise list items and headed sections of the reply), and every block has the same two parts for every arm: where
it points (file:line and any quoted code) and what it claims (file:line, title and failing case; in a free-form reply,
the item without a Fix:/Remediation: line). A plant is credited only when the block points at it (its file, and, when
the answer key gives them, one of the places in its "at" list or its "quote"; keymatch.py, shared with score.py) and its
pattern is in the claim, never in fix advice; each block credits one plant, each plant once. Every plant in the four
answer keys has "at" (decision 28).
On a clean twin a block that cites a file:line, or that someone labelled false, is a false alarm. Every other block,
there and on the planted suites, is UNLABELLED until someone labels it in RUN_DIR/labels.json ({"<arm>/<task>/<block
n>": "real"|"false"}), and precision is NOT MEASURED while any are unlabelled: nothing is guessed. A run that failed,
timed out or wrote nothing is shown with its error and scored NOT MEASURED, never as a clean result. Cost, tokens and wall
time come from Claude Code's own JSON result. Results: RUN_DIR/results.json and RUN_DIR/report.md."""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import keymatch
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
        if re.match(r"^\s?(?:[-*+]|\d+[.)])\s+\S", l) or re.match(r"^#{2,6}\s+\S", l):  # a top-level item; an indented sub-bullet stays part of its item
            if cur and "".join(cur).strip(): out.append("\n".join(cur))
            cur = [l]
        elif cur: cur.append(l)
    if cur and "".join(cur).strip(): out.append("\n".join(cur))
    keep = [b for b in out if re.search(r"[\w./-]+\.\w+(:\d+)?", b) or re.search(r"(?i)\b(bug|defect|issue|vulnerab|incorrect|wrong|fails?|leak|race|inject)", b)]
    return [b for b in keep if not (NONE_FOUND.search(b) and not CITES.search(b))]  # "No issues found." is not a finding

NONE_FOUND = re.compile(r"(?i)\bno\s+(?:\w+\s+){0,2}(issues?|bugs?|defects?|problems?|findings?|vulnerabilit\w*)\b")

def FIX_strip(text):
    """Remove fix advice: from a Fix:/Remediation: label to the end of its line. The one exception is the item's own
    first line when only the list marker and the location come before the label ("1. app.js:42 Fix: titles are
    injected unescaped"): there the label is all that goes, since the whole claim follows it."""
    out = []
    for k, line in enumerate(text.split("\n")):
        m = FIX_LABEL.search(line)
        if not m: out.append(line); continue
        before = re.sub(r"[\w./-]+\.\w+(:\d+(-\d+)?)?|[*_`#>\-–—:.)(\[\]\s\d]", "", line[:m.start()])
        out.append(line[:m.start()] + line[m.end():] if k == 0 and not before and CITES.search(line[:m.start()]) else line[:m.start()])
    return "\n".join(out)

CITES = re.compile(r"[\w./-]+\.\w+:\d+")
FIX_LABEL = re.compile(r"(?i)(?:\*\*)?\b(?:suggested\s+fix|fix(?:ed)?|remediation|recommendation|solution|to fix|how to fix|mitigation)(?:\*\*)?\s*:(?:\*\*)?")

def blocks_for(arm_dir):
    """[{"loc": where the block points, "claim": what it says is wrong}], the same two parts for every arm; None when
    the arm wrote nothing at all."""
    fj = arm_dir / "findings.jsonl"
    if fj.exists():
        rows = [json.loads(x) for x in fj.read_text().splitlines() if x.strip()]
        out = []
        for r in rows:
            at = f"{r.get('file', '')}:{r.get('line')}" if r.get("line") not in (None, "") else str(r.get("file", ""))
            out.append({"loc": f"{at} {r.get('quote', '')} " + " ".join(str(x) for x in (r.get("locations") or []) if isinstance(x, str)),  # a merged finding's own cited places, as score.py
                        "claim": f"{at} {r.get('title', '')}. {r.get('evidence', '')} {r.get('failing_case', '')}"})  # all it says is wrong, never its fix: the same as a free-form arm's item minus its Fix: line
        return out
    md = arm_dir / "output.md"
    if not md.exists() or not md.read_text().strip(): return None
    js = json_findings(md.read_text())
    if js is not None: return js
    return [{"loc": b, "claim": FIX_strip(b)} for b in blocks_from(md.read_text())]

def json_findings(text):
    """A reply that is a JSON list of findings ({file, line, summary or title, failure_scenario ...}), as Claude Code's
    built-in /code-review writes it: one block per object, the same two parts as every other arm. None when the reply
    is not that shape. Fix advice inside a field is stripped from the claim like anywhere else."""
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S) or re.fullmatch(r"\s*(\[.*\])\s*", text, re.S)
    if not m: return None
    try: rows = json.loads(m.group(1))
    except ValueError: return None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and r.get("file") for r in rows): return None
    out = []
    for r in rows:
        at = f"{r.get('file')}:{r.get('line')}" if r.get("line") not in (None, "") else str(r.get("file"))
        what = " ".join(str(r.get(k, "")) for k in ("summary", "title", "description", "failure_scenario", "issue") if r.get(k))
        out.append({"loc": at, "claim": FIX_strip(f"{at} {what}")})
    return out

def _points_at(k, loc):
    """True when the block points where the plant is: its file, and (when the key gives "at") one of its places
    (keymatch.py, shared with score.py)."""
    if k.get("file") and k["file"].lower() not in loc.lower(): return False
    return keymatch.points_at(k, loc)

def match_plants(plants, blocks):
    """{plant id: block index}: each block credits one plant, each plant once. A plant is credited only when the block
    points at it and the plant's pattern is in the block's claim."""
    return keymatch.max_match({name: [i for i, b in enumerate(blocks) if _points_at(k, b["loc"]) and any(re.search(p, b["claim"], re.I) for p in k["any"])]
                               for name, k in plants.items()})

def plants_of(key):
    """The plants of an answer key in match_plants' shape (a scripted lens's key lists them under "planted")."""
    return key.get("planted") and {p["id"]: {"file": p["where"].rsplit(":", 1)[0], "any": [re.escape(p["rule"])], "at": [[p["where"].rsplit(":", 1)[0], int(p["where"].rsplit(":", 1)[1]), int(p["where"].rsplit(":", 1)[1])]]} for p in key["planted"]} or key

def score_task(task, blocks, labels, prefix):
    if task.get("clean"):  # every claim here is false; one with no file:line still needs a person to say it is a claim
        lab = lambda i: labels.get(f"{prefix}/{i}")
        fa = [i for i, b in enumerate(blocks) if lab(i) == "false" or (CITES.search(b["loc"]) and lab(i) != "real")]
        unl = [i for i, b in enumerate(blocks) if i not in fa and lab(i) is None]
        return {"false_alarms": len(fa), "blocks": len(blocks), "unlabelled": len(unl), "precision": None if unl else (f"0 of {len(fa)}" if fa else "no findings")}
    plants = plants_of(json.loads((HERE / task["key"]).read_text()))
    hit = match_plants(plants, blocks); used = set(hit.values())
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
            out = td / "output.md"
            err = failed(meta, out.read_text(errors="replace") if out.exists() else "") or (None if blocks is not None else "no output")
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

def installed_plugins():
    """Every plugin Claude Code would load here (name@marketplace). Each arm runs with all of them switched off except
    its own, so no arm borrows another reviewer (a synced copy of Curmudgeon, say) without anyone noticing."""
    try: out = subprocess.run(["claude", "plugin", "list"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired): return []
    return sorted(set(re.findall(r"^\s*>\s*(\S+@\S+)", out, re.M)))

def one_run(a, w, td, model):
    """One arm on one task in the work folder w; returns its meta (an error is recorded, never raised past here except
    a timeout, which the caller records)."""
    if a.get("command"):
        r = subprocess.run(a["command"], shell=True, cwd=w, capture_output=True, text=True, timeout=1800, env=dict(os.environ, DM_EVAL=str(HERE)))
        (td / "output.md").write_text(r.stdout); meta = {"exit": r.returncode}
        if r.returncode not in (0, 1): meta["error"] = f"exit {r.returncode}: {(r.stderr or '')[-200:]}"
        return meta
    cmd = ["claude", "-p", a["prompt"], "--output-format", "json", "--allowedTools", ",".join(a.get("tools", ["Read", "Grep", "Glob"]))]
    if model: cmd += ["--model", model]
    if a.get("plugin"): cmd += ["--plugin-dir", str(PLUGIN)]
    for pd in a.get("plugin_dirs") or []:  # another plugin under test, kept outside this repository (its own licence); $VARS from the environment
        d = pathlib.Path(os.path.expandvars(pd)).resolve()  # absolute: claude runs in the task's temporary folder
        if not (d / ".claude-plugin").is_dir() and not (d / "agents").is_dir() and not (d / "skills").is_dir(): return {"error": f"plugin folder not found: {d} (set its variable; nothing is installed for you)"}
        cmd += ["--plugin-dir", str(d)]
    keep = set(a.get("plugin_enable") or [])
    cmd += ["--settings", json.dumps({"enabledPlugins": {p: (p in keep) for p in PLUGINS}})]
    r = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=3600, stdin=subprocess.DEVNULL)
    try:
        j = json.loads(r.stdout); u = j.get("usage") or {}
        (td / "output.md").write_text(str(j.get("result") or ""))
        return {"total_cost_usd": j.get("total_cost_usd"), "tokens": sum(int(u.get(x) or 0) for x in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")),
                "is_error": j.get("is_error"), "num_turns": j.get("num_turns"), "agents_launched": agents_launched(w),
                **({"error_text": str(j.get("result") or j.get("subtype") or "")[-300:]} if j.get("is_error") else {})}  # so a usage limit can be told from a real failure
    except ValueError: return {"error": (r.stderr or r.stdout)[-500:] or f"no result (exit {r.returncode})"}

def agents_launched(work, root=None):
    """How many subagents a run started (Agent or Task tool calls in its transcript), so a reviewer that is meant to fan
    out to agents and didn't is reported as such, never assumed (ruling §5.53). The transcript is found by the run's own
    work folder (Claude Code files it under the folder's path with every other character turned to '-'); a session id
    is no key, because a headless run started from another session can inherit that session's id. Subagents' own files
    (in subfolders) are not counted. None when there is no transcript."""
    if not work: return None
    root = pathlib.Path(root or os.path.expanduser("~/.claude/projects"))
    folder = root / re.sub(r"[^A-Za-z0-9]", "-", str(work))
    files = sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
    if not files: return None
    n = 0
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            try: rec = json.loads(line)
            except ValueError: continue
            content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
            for c in content if isinstance(content, list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"): n += 1
    return n

PLUGINS = []
GIT = ["git", "-c", "user.email=dm@example.invalid", "-c", "user.name=dm"]

def one_job(a, t, k, repeat, out, model):
    td = out / a["id"] / (t["id"] + (f"~{k + 1}" if repeat > 1 else "")); td.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="dm-") as tmp:
        w = pathlib.Path(tmp) / "work"; shutil.copytree(HERE / t["fixture"], w, ignore=shutil.ignore_patterns(".critic"))
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=w)
        if a.get("pr"):  # a pull-request reviewer: the task is a branch over an empty base, so every line is part of the change
            subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "base"], cwd=w); subprocess.run(["git", "checkout", "-q", "-b", "change"], cwd=w)
        subprocess.run(["git", "add", "."], cwd=w); subprocess.run(GIT + ["commit", "-qm", "task"], cwd=w)
        t0 = time.time()
        try: meta = one_run(a, w, td, model)
        except subprocess.TimeoutExpired as e: meta = {"error": f"timeout after {int(e.timeout)} s"}  # recorded; the other runs go on
        except FileNotFoundError as e: meta = {"error": f"not found: {e.filename or e} (nothing is installed for you)"}
        meta["wall_s"] = round(time.time() - t0, 1)
        for f_ in ("findings.jsonl", "last-review.md"):
            if (w / ".critic" / f_).exists(): shutil.copy2(w / ".critic" / f_, td / f_)
        (td / "meta.json").write_text(json.dumps(meta, indent=1))
    return f"done {a['id']} / {td.name} ({meta.get('wall_s')} s)" + (f" error: {str(meta['error'])[:80]}" if meta.get("error") else "")

VOID = re.compile(r"(?i)usage limit|rate.?limit|limit reached|hit your [\w -]*limit|\b429\b|overloaded|credit balance|quota")

def failed(meta, reply=""):
    """Why a run failed, or None. reply is the run's output.md. A run whose result shows no model work (0 tokens)
    and whose reply is empty or a limit message failed even when Claude Code called it a success: on 29 Oct a usage
    limit came back as is_error false with 0 tokens and the limit message as the reply, and 35 such runs were first
    scored as clean "found nothing" results. 0 tokens alone is not a failure: the built-in /code-review's result
    reports 0 tokens even when it reviewed and replied."""
    zero = meta.get("tokens") == 0 and (not (reply or "").strip() or VOID.search((reply or "")[-500:]))
    return meta.get("error") or ("the run reported an error (is_error)" if meta.get("is_error") else None) or \
        ("the run did no model work (0 tokens, and its reply is empty or a limit message)" if zero else None)

def voided(meta, reply=""):
    """True when a run failed because of a usage or rate limit rather than the tool under test (ruling §5.53: such a
    run is void and is run again; any other failure counts against the arm)."""
    return bool(failed(meta, reply)) and bool(VOID.search(json.dumps(meta) + "\n" + (reply or "")[-500:]))

def run(arms, tasks, model, repeat, parallel=1):
    import concurrent.futures as cf
    PLUGINS[:] = installed_plugins()
    out = HERE / "runs" / time.strftime("%Y-%m-%d-%H%M%S"); out.mkdir(parents=True)
    (out / "run.json").write_text(json.dumps({"model": model, "repeat": repeat, "plugin": str(PLUGIN), "arms": [a["id"] for a in arms],
                                               "tasks": [t["id"] for t in tasks], "plugins_off": PLUGINS, "started": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
    jobs = []
    for a in arms:
        if a.get("requires") and not shutil.which(a["requires"]): print(f"skip {a['id']}: {a['requires']} not installed"); continue
        jobs += [(a, t, k) for k in range(repeat) for t in tasks if not (a.get("tasks") and t["id"] not in a["tasks"])]
    with cf.ThreadPoolExecutor(max(1, parallel)) as ex:  # several sessions at once; each has its own folder, so none sees another
        for f in cf.as_completed([ex.submit(one_job, a, t, k, repeat, out, model) for a, t, k in jobs]): print(f.result(), flush=True)
    return score(out)

def rerun(run_dir, all_errors=False, parallel=1):
    """Run again, in place, every run of RUN_DIR that a usage limit voided (or, with all_errors, that failed at all), with
    the model, repeat count and plugin folder recorded when it first ran. The voided result is appended to voided.jsonl,
    so how many runs were voided is never lost."""
    import concurrent.futures as cf
    global PLUGIN
    run_dir = pathlib.Path(run_dir); info = json.loads((run_dir / "run.json").read_text())
    PLUGIN = pathlib.Path(info["plugin"]); PLUGINS[:] = info.get("plugins_off") or installed_plugins()
    cfg = load_cfg(); arms = {x["id"]: x for x in cfg["arms"]}; tasks = {x["id"]: x for x in cfg["tasks"]}; jobs = []
    for td in sorted(run_dir.glob("*/*/meta.json")):
        meta = json.loads(td.read_text()); out = td.parent / "output.md"; reply = out.read_text(errors="replace") if out.exists() else ""
        if not (voided(meta, reply) or (all_errors and failed(meta, reply))): continue
        arm, name = td.parent.parent.name, td.parent.name; tid, _, k = name.partition("~")
        with open(run_dir / "voided.jsonl", "a") as f: f.write(json.dumps({"run": f"{arm}/{name}", "voided_by_limit": voided(meta, reply), "meta": meta, "reply_tail": reply[-300:]}) + "\n")
        shutil.rmtree(td.parent); jobs.append((arms[arm], tasks[tid], int(k or 1) - 1))
    with cf.ThreadPoolExecutor(max(1, parallel)) as ex:
        for f in cf.as_completed([ex.submit(one_job, a, t, k, info.get("repeat") or 1, run_dir, info.get("model")) for a, t, k in jobs]): print(f.result(), flush=True)
    print(f"{len(jobs)} run(s) run again")
    return score(run_dir)

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d
    if a[0] == "score": return score(a[1]) if len(a) > 1 else 2
    if a[0] == "rerun":
        if len(a) < 2 or "--yes-spend" not in a: print("refused: a rerun makes paid model calls; pass RUN_DIR and --yes-spend"); return 2
        return rerun(a[1], "--all-errors" in a, int(opt("--parallel", "1")))
    global PLUGIN
    if opt("--plugin"): PLUGIN = pathlib.Path(opt("--plugin")).resolve()  # a frozen copy of the build under test, not this checkout
    cfg = load_cfg(); arms = pick(cfg["arms"], opt("--arms")); tasks = pick(cfg["tasks"], opt("--tasks"))
    if a[0] == "plan": return plan(arms, tasks)
    if a[0] == "run":
        if "--yes-spend" not in a: print("refused: a run makes paid model calls; pass --yes-spend after checking `deathmatch.py plan`"); return 2
        return run(arms, tasks, opt("--model"), int(opt("--repeat", "1")), int(opt("--parallel", "1")))
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
