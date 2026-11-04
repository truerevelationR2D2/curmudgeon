#!/usr/bin/env python3
"""Carry the 5.2.4 labels across the splitter fix of 3 Nov 2026 (audit V18, CHANGELOG "batch 4").

The free-form splitter (eval/deathmatch.py blocks_from) now keeps a bold-numbered finding's flush bullets with it and
ends a list at the prose that follows. Labels are keyed by block number, so the code-review plugin's free-form replies
need their labels moved to the new block numbers. Nothing is guessed:
- a new block whose text is the text of one or more old blocks takes their label when the labelled ones agree
  (verdict, actionable and severity; a "none" part, a heading, is left out when a labelled finding is beside it);
- a new block credited to a plant needs no label (the answer key's business, as before); one that restates a plant
  keeps its label, which bench_stats.py leaves out of every count, as before;
- a new block whose text matches no old block, and an unlabelled one (an old block left unlabelled because it restated
  a plant), keeps no label;
- every other block (its parts disagree, or it is new text) is written to blind packets for two labellers and a
  tiebreaker, exactly as label.py does (labeller-brief.md), and their labels are merged in with `apply`.

usage:
  rekey_2026_11_03.py plan  OLD_DEATHMATCH RUN_DIR... --apps DIR   write the packets and the carried labels (labels.rekey.json)
  rekey_2026_11_03.py apply RUN_DIR... A.json B.json [T.json]       merge the new labels, then write labels.json and labels-detail.json
OLD_DEATHMATCH is the scorer before the fix: `git show 1d5d0cb:eval/deathmatch.py > old.py`, run from eval/."""
import importlib.util, json, pathlib, random, sys

HERE = pathlib.Path(__file__).resolve().parent; EV = HERE.parent
sys.path.insert(0, str(EV))
import deathmatch as new, label

def _load_old(path):
    s = importlib.util.spec_from_file_location("dm_old", path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    m.HERE = EV; return m

def _sig(d): return (d["verdict"], d["actionable"], d.get("severity"))

def plan(old_path, run_dirs, apps):
    old = _load_old(old_path); tasks = {t["id"]: t for t in new.load_cfg()["tasks"]}
    rng = random.Random(20261103); packets = {}; idmap = {}; alias = {}; report = []
    for rd in map(pathlib.Path, run_dirs):
        detail = json.loads((rd / "labels-detail.json").read_text(encoding="utf-8"))["labels"]
        carried = {k: v for k, v in detail.items()}; moved = 0
        for td in sorted(p for p in rd.glob("*/*") if p.is_dir() and p.parent.name != "labelling"):
            t = tasks.get(td.name.split("~")[0])
            if not t: continue
            bo, bn = old.blocks_for(td), new.blocks_for(td)
            if bo is None or bn is None or [b["claim"] for b in bo] == [b["claim"] for b in bn]: continue
            pre = f"{td.parent.name}/{td.name}"
            for k in [k for k in carried if k.startswith(pre + "/")]: del carried[k]
            used = set() if t.get("clean") else set(new.match_plants(new.plants_of(json.loads((EV / t["key"]).read_text(encoding="utf-8"))), bn).values())
            for i, b in enumerate(bn):
                if i in used: continue
                parts = ([j for j, o in enumerate(bo) if o["loc"].strip() and o["loc"].strip() in b["loc"]]
                         or [j for j, o in enumerate(bo) if b["loc"].strip() and b["loc"].strip() in o["loc"]])
                labs = [detail[f"{pre}/{j}"] for j in parts if f"{pre}/{j}" in detail]
                if parts and not labs and any(o["claim"] == b["claim"] for o in bo): continue  # unlabelled before, unchanged text
                sigs = {_sig(d) for d in labs if d["verdict"] != "none"} or {_sig(d) for d in labs}
                if len(sigs) == 1:
                    carried[f"{pre}/{i}"] = dict(next(d for d in labs if _sig(d) in sigs), decided_by="carried (V18 rekey)"); moved += 1; continue
                while t["fixture"] not in alias:
                    a = "app-" + "".join(rng.choice("0123456789abcdef") for _ in range(6))
                    if a not in alias.values(): alias[t["fixture"]] = a
                pid = "R" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
                idmap[pid] = f"{rd.name}|{pre}/{i}"
                packets.setdefault(t["fixture"], []).append({"id": pid, "app": alias[t["fixture"]], "finding": label.plain(b["claim"] if b["claim"].strip() else b["loc"])})
        (rd / "labels.rekey.json").write_text(json.dumps(carried, indent=1, sort_keys=True), encoding="utf-8")
        report.append(f"{rd.name}: {moved} label(s) carried to new block numbers")
    out = HERE / "rekey-2026-11-03"; out.mkdir(exist_ok=True)
    apps = pathlib.Path(apps)
    if apps.resolve().is_relative_to(EV.resolve()): sys.exit("--apps must be outside eval/, so a labeller can't reach the answer keys")
    for fx, ps in packets.items():
        rng.shuffle(ps); label.neutral_copy(EV / fx, apps / alias[fx])
        (out / f"{alias[fx]}.json").write_text(json.dumps(ps, indent=1), encoding="utf-8")
    (out / "map.json").write_text(json.dumps(idmap, indent=1, sort_keys=True), encoding="utf-8"); (out / "apps.json").write_text(json.dumps({v: k for k, v in alias.items()}, indent=1), encoding="utf-8")
    print("\n".join(report)); print(f"{len(idmap)} block(s) to label blindly, in {len(packets)} packet file(s) in {out}; apps copied to {apps}")

def apply(run_dirs, a, b, t=None):
    out = HERE / "rekey-2026-11-03"; idmap = json.loads((out / "map.json").read_text(encoding="utf-8"))
    A, B = ({x["id"]: x for x in json.loads(pathlib.Path(f).read_text(encoding="utf-8"))} for f in (a, b))
    T = {x["id"]: x for x in json.loads(pathlib.Path(t).read_text(encoding="utf-8"))} if t else {}
    new_labels = {}; ties = []
    for pid, where in idmap.items():
        x, y = A[pid], B[pid]
        if (x["verdict"], x["actionable"]) == (y["verdict"], y["actionable"]):
            sev = None if x["verdict"] != "real" else min((x.get("severity"), y.get("severity")), key=lambda s: ["low", "medium", "high", "critical"].index(s or "low"))
            new_labels[where] = {"verdict": x["verdict"], "actionable": x["actionable"], "severity": sev, "decided_by": "agreed (V18 rekey)"}
        elif pid in T: new_labels[where] = dict({k: T[pid][k] for k in ("verdict", "actionable", "severity")}, decided_by="tiebreaker (V18 rekey)")
        else: ties.append(pid)
    if ties: sys.exit(f"{len(ties)} tie(s) need the tiebreaker: {', '.join(sorted(ties))}")
    for rd in map(pathlib.Path, run_dirs):
        lab = json.loads((rd / "labels.rekey.json").read_text(encoding="utf-8"))
        lab.update({w.split("|", 1)[1]: v for w, v in new_labels.items() if w.split("|", 1)[0] == rd.name})
        dfile = rd / "labels-detail.json"; full = json.loads(dfile.read_text(encoding="utf-8"))
        keep = rd / "labels-detail.as-labelled.json"  # the labels as labelled, keyed as the packets were cut: label.py recheck reads these
        if not keep.exists(): keep.write_text(dfile.read_text(encoding="utf-8"), encoding="utf-8")
        full["labels"] = dict(sorted(lab.items()))
        full["rekey_2026_11_03"] = "labels moved to the splitter's new block numbers (audit V18); see eval/benchmark-5.2.4/rekey_2026_11_03.py"
        dfile.write_text(json.dumps(full, indent=1), encoding="utf-8")
        (rd / "labels.json").write_text(json.dumps({k: {"wrong": "false"}.get(v["verdict"], v["verdict"]) for k, v in sorted(lab.items())}, indent=1), encoding="utf-8")
        (rd / "labels.rekey.json").unlink()
    print(f"{len(new_labels)} new label(s) merged")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["plan"] and "--apps" in a:
        i = a.index("--apps"); plan(a[1], a[2:i], a[i + 1])
    elif a[:1] == ["apply"] and len(a) >= 4:
        files = [x for x in a[1:] if x.endswith(".json")]; dirs = [x for x in a[1:] if not x.endswith(".json")]
        apply(dirs, *files)
    else: sys.exit(__doc__)
