#!/usr/bin/env python3
"""Blind labelling for the death match (ruling §5.53): every finding that did not match a planted defect is judged by
two labellers who never see which tool wrote it, the answer key, or each other's labels; a third breaks their ties.
Planted-bug detection stays with the script's answer-key match (deathmatch.py) and is never relabelled here.

usage:
  label.py export RUN_DIR --apps DIR [--chunk N] [--controls N]
                                                   write blind packets and bare copies of the apps to label against
  label.py ties   RUN_DIR A.json B.json            agreement between the two labellers; packets for the tiebreaker
  label.py final  RUN_DIR A.json B.json [T.json]   write RUN_DIR/labels.json (and labels-detail.json) for the scorer
  label.py recheck RUN_DIR RECHECK_DIR             how a later blind relabel of a sample agrees with the final labels

A packet holds an opaque id, the app's opaque name and the finding's own words with markdown removed: never the arm,
the run, the task's answer key or another finding's label. The ids are shuffled across arms, so order says nothing.
The map from id to "<arm>/<task>/<block>" stays in RUN_DIR/labelling/map.json, which no labeller is shown.

A labeller returns one JSON object per packet:
  {"id": ..., "verdict": "real" | "trivial" | "wrong" | "none", "actionable": true | false, "severity": "critical" | "high" |
   "medium" | "low" | null}
real: the code really behaves as claimed and it matters; trivial: true but not worth acting on (style, naming, a nit);
wrong: the code does not do what the finding says; none: not a finding at all (a heading, a summary, a note about
the review itself), so a free-form reply's framing is never counted as a false alarm. actionable: a developer
could fix it from what the finding says. severity: for real findings only.

Known-truth controls, mixed in blind: for each planted task with a clean twin (suite1 and suite1-clean, say), up to N
findings the answer key credited to a plant (default 3) are shown once against the planted app (truth: real) and once
against its clean twin, where that defect is fixed (truth: wrong). Each labeller's accuracy on them is reported, so
a labeller who calls everything real is caught; controls never reach labels.json. They live in controls.json.

Two labels agree when verdict and actionable are the same; then a severity difference takes the lower of the two
(a check may lower an impact, never raise it, as Curmudgeon's verifiers do). Any other difference goes to the
tiebreaker, whose label stands. Agreement is reported as the share agreeing and as Cohen's kappa on the verdict.
For the scorer, real is "real", wrong is "false", and trivial and none are "trivial" and "none" (counted neither way in
precision; none is left out of every share as well)."""
import json, pathlib, random, re, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deathmatch

VERDICTS = ("real", "trivial", "wrong", "none")
SEVERITIES = ("low", "medium", "high", "critical")

def plain(text):
    """The finding's words without markdown decoration, so formatting doesn't say which tool wrote it."""
    t = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), text, flags=re.S)
    t = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)", "", t, flags=re.M)
    t = re.sub(r"\*\*|__|`", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

def unmatched(run_dir):
    """[(key, task, text)] for every finding block that states no planted defect (on a clean twin, every block), from
    runs that finished. A block that restates a plant another block was credited for is left out too: it is the
    same bug, not a separate finding."""
    cfg = deathmatch.load_cfg(); tasks = {t["id"]: t for t in cfg["tasks"]}; out = []
    for arm_dir in sorted(p for p in pathlib.Path(run_dir).iterdir() if p.is_dir() and p.name != "labelling"):
        for td in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            t = tasks.get(td.name.split("~")[0])
            meta = json.loads((td / "meta.json").read_text()) if (td / "meta.json").exists() else {}
            blocks = deathmatch.blocks_for(td)
            if not t or blocks is None or deathmatch.failed(meta, (td / "output.md").read_text(errors="replace") if (td / "output.md").exists() else ""): continue
            used = set()
            if not t.get("clean"):  # a credited plant, and any second report of one, is the answer key's business
                used = deathmatch.plant_blocks(deathmatch.plants_of(json.loads((HERE / t["key"]).read_text())), blocks)
            for i, b in enumerate(blocks):
                if i not in used: out.append((f"{arm_dir.name}/{td.name}/{i}", t, plain(b["claim"] if b["claim"].strip() else b["loc"])))
    return out

def plant_hits(run_dir):
    """{task id: [finding text]} for findings the answer key credited to a plant, from runs that finished."""
    cfg = deathmatch.load_cfg(); tasks = {t["id"]: t for t in cfg["tasks"]}; out = {}
    for td in sorted(pathlib.Path(run_dir).glob("*/*/")):
        t = tasks.get(td.name.split("~")[0])
        if not t or t.get("clean") or td.parent.name == "labelling": continue
        meta = json.loads((td / "meta.json").read_text()) if (td / "meta.json").exists() else {}
        blocks = deathmatch.blocks_for(td)
        if blocks is None or deathmatch.failed(meta, (td / "output.md").read_text(errors="replace") if (td / "output.md").exists() else ""): continue
        hit = deathmatch.match_plants(deathmatch.plants_of(json.loads((HERE / t["key"]).read_text())), blocks)
        out.setdefault(t["id"], []).extend(plain(blocks[i]["claim"]) for i in sorted(hit.values()))
    return out

# Words in the fixtures that tell a reader what the answer is. The labellers' copies get neutral text in their place,
# line for line, so every line number a finding cites still points at the same code.
GIVEAWAYS = [(re.compile(r"__PLANTED_([A-Z0-9_]*)__"), r"__\1VALUE__"), (re.compile(r"(?i)\bplanted\b"), "example"),
             (re.compile(r"(?im)^(\s*(?://|#|<!--|/\*)).*\b(?:decoys?|clean twin|answer key)\b.*$"), r"\1")]

def neutral_copy(src, dst):
    """Copy an app for the labellers with the GIVEAWAYS replaced in every text file (line count unchanged)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".critic", ".git"))
    for f in dst.rglob("*"):
        if not f.is_file(): continue
        try: text = f.read_text()
        except (UnicodeDecodeError, OSError): continue
        new = text
        for pat, rep in GIVEAWAYS: new = pat.sub(rep, new)
        if new != text: f.write_text(new)

def export(run_dir, apps, chunk=30, seed=None, controls=3):
    """Blind packets: each app gets an opaque name (app-<hex>) and its own folder, so neither the name nor the folder
    says which app is a clean twin; the id-to-finding map and the name-to-app map stay in RUN_DIR/labelling/."""
    run_dir = pathlib.Path(run_dir); lab = run_dir / "labelling"; apps = pathlib.Path(apps)
    if apps.resolve().is_relative_to(HERE.resolve()): sys.exit("--apps must be outside eval/, so a labeller can't reach the answer keys")
    items = unmatched(run_dir); rng = random.Random(seed); rng.shuffle(items)
    ids = set(); idmap = {}; by_app = {}; alias = {}
    def name(fixture):
        while fixture not in alias:
            a = "app-" + "".join(rng.choice("0123456789abcdef") for _ in range(6))
            if a not in alias.values(): alias[fixture] = a
        return alias[fixture]
    for key, t, text in items:
        pid = "F" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
        while pid in ids: pid = "F" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
        ids.add(pid); idmap[pid] = key
        by_app.setdefault(t["fixture"], []).append({"id": pid, "app": name(t["fixture"]), "finding": text})
    tasks = {t["id"]: t for t in deathmatch.load_cfg()["tasks"]}; ctl = {}
    for tid, texts in sorted(plant_hits(run_dir).items()):
        twin = tasks.get(tid + "-clean")
        if not twin or not texts: continue
        for text in rng.sample(texts, min(controls, len(texts))):
            for app, truth in ((tasks[tid]["fixture"], "real"), (twin["fixture"], "wrong")):
                pid = "F" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
                while pid in ids: pid = "F" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
                ids.add(pid); ctl[pid] = {"truth": truth, "app": app}
                by_app.setdefault(app, []).append({"id": pid, "app": name(app), "finding": text})
    for ps in by_app.values(): rng.shuffle(ps)
    (lab).mkdir(parents=True, exist_ok=True); (lab / "controls.json").write_text(json.dumps(ctl, indent=1))
    (lab / "packets").mkdir(parents=True, exist_ok=True)
    for app in by_app:
        dst = apps / alias[app]
        if dst.exists(): shutil.rmtree(dst)
        neutral_copy(HERE / app, dst)
    files = []
    for app, ps in sorted(by_app.items(), key=lambda kv: alias[kv[0]]):
        for k in range(0, len(ps), chunk):
            f = lab / "packets" / f"{alias[app]}-{k // chunk + 1}.json"; f.write_text(json.dumps(ps[k:k + chunk], indent=1)); files.append(f)
    (lab / "map.json").write_text(json.dumps(idmap, indent=1))
    (lab / "apps.json").write_text(json.dumps({v: k for k, v in alias.items()}, indent=1))
    print(f"{len(items)} finding(s) and {len(ctl)} control(s) to label in {len(files)} packet file(s); apps copied to {apps}")
    return files

def load_labels(path):
    rows = json.loads(pathlib.Path(path).read_text()); out = {}
    if not isinstance(rows, list): raise ValueError(f"{path}: not a JSON list of labels")
    for r in rows:
        v = r.get("verdict"); s = r.get("severity")
        bad_actionable = v != "none" and not isinstance(r.get("actionable"), bool)
        if r.get("id") is None or v not in VERDICTS or bad_actionable or (s is not None and s not in SEVERITIES):
            raise ValueError(f"{path}: a label is not in the agreed shape: {r}")
        out[r["id"]] = {"verdict": v, "actionable": bool(r.get("actionable")) and v != "none", "severity": s if v == "real" else None}
    return out

def agree(a, b): return a["verdict"] == b["verdict"] and a["actionable"] == b["actionable"]

def lower(s1, s2):
    if s1 is None or s2 is None: return s1 or s2
    return min(s1, s2, key=SEVERITIES.index)

def kappa(pairs):
    """Cohen's kappa on the verdict for [(a, b)]; None when it is undefined (every label the same category)."""
    n = len(pairs)
    if not n: return None
    po = sum(1 for a, b in pairs if a == b) / n
    pe = sum((sum(1 for a, _ in pairs if a == c) / n) * (sum(1 for _, b in pairs if b == c) / n) for c in VERDICTS)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)

def control_accuracy(run_dir, labels):
    """{"n", "correct", "real_right", "wrong_right"} for one labeller on the known-truth controls; None without any."""
    f = pathlib.Path(run_dir) / "labelling" / "controls.json"
    ctl = json.loads(f.read_text()) if f.exists() else {}
    if not ctl: return None
    missing = [p for p in ctl if p not in labels]
    if missing: raise ValueError(f"{len(missing)} control(s) have no label, e.g. {missing[:3]}")
    ok = lambda p: labels[p]["verdict"] == "real" if ctl[p]["truth"] == "real" else labels[p]["verdict"] in ("wrong", "none")
    return {"n": len(ctl), "correct": sum(1 for p in ctl if ok(p)),
            "real_right": f"{sum(1 for p in ctl if ctl[p]['truth'] == 'real' and ok(p))} of {sum(1 for p in ctl if ctl[p]['truth'] == 'real')}",
            "wrong_right": f"{sum(1 for p in ctl if ctl[p]['truth'] == 'wrong' and ok(p))} of {sum(1 for p in ctl if ctl[p]['truth'] == 'wrong')}"}

def compare(run_dir, fa, fb):
    idmap = json.loads((pathlib.Path(run_dir) / "labelling" / "map.json").read_text())
    A, B = load_labels(fa), load_labels(fb)
    missing = sorted(set(idmap) - set(A)) + sorted(set(idmap) - set(B))
    if missing: raise ValueError(f"{len(missing)} packet(s) have no label from one labeller, e.g. {missing[:3]}")
    both = sorted(idmap)
    ties = [p for p in both if not agree(A[p], B[p])]
    stats = {"findings": len(both), "agreed": len(both) - len(ties), "agreement": round((len(both) - len(ties)) / len(both), 3) if both else None,
             "kappa_verdict": kappa([(A[p]["verdict"], B[p]["verdict"]) for p in both]),
             "controls_a": control_accuracy(run_dir, A), "controls_b": control_accuracy(run_dir, B)}
    return idmap, A, B, ties, stats

def ties(run_dir, fa, fb):
    idmap, A, B, tie_ids, stats = compare(run_dir, fa, fb)
    lab = pathlib.Path(run_dir) / "labelling"; packets = {}
    for f in sorted((lab / "packets").glob("*.json")):
        for p in json.loads(f.read_text()): packets[p["id"]] = p
    (lab / "ties.json").write_text(json.dumps([packets[p] for p in tie_ids], indent=1))  # the tiebreaker sees neither label
    (lab / "agreement.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats), f"\n{len(tie_ids)} tie(s) written to {lab / 'ties.json'}")
    return tie_ids, stats

def final(run_dir, fa, fb, ft=None):
    idmap, A, B, tie_ids, stats = compare(run_dir, fa, fb)
    T = load_labels(ft) if ft else {}
    left = [p for p in tie_ids if p not in T]
    if left: raise ValueError(f"{len(left)} tie(s) have no tiebreaker label, e.g. {left[:3]}")
    detail = {}
    for p, key in idmap.items():
        if p in tie_ids: d = dict(T[p], decided_by="tiebreaker")
        else: d = dict(A[p], severity=lower(A[p]["severity"], B[p]["severity"]), decided_by="agreed")
        detail[key] = d
    run_dir = pathlib.Path(run_dir)
    labels = json.loads((run_dir / "labels.json").read_text()) if (run_dir / "labels.json").exists() else {}
    labels.update({k: {"real": "real", "wrong": "false", "trivial": "trivial", "none": "none"}[d["verdict"]] for k, d in detail.items()})
    (run_dir / "labels.json").write_text(json.dumps(labels, indent=1, sort_keys=True))
    (run_dir / "labels-detail.json").write_text(json.dumps({"agreement": stats, "tiebroken": len(tie_ids), "labels": detail}, indent=1, sort_keys=True))
    print(json.dumps(stats), f"\n{len(detail)} label(s) written; {len(tie_ids)} decided by the tiebreaker")
    return detail, stats

def recheck(run_dir, rdir):
    """Agreement between a later blind relabel of a sample (RECHECK_DIR: map.json, controls.json, labels.json, as
    export and one labeller write them) and RUN_DIR's final labels, beside how the first labeller (labelling/A.json)
    agreed with the same final labels on the same sample; and the relabel's accuracy on its controls."""
    run_dir, rdir = pathlib.Path(run_dir), pathlib.Path(rdir)
    final = json.loads((run_dir / "labels-detail.json").read_text())["labels"]
    idmap = json.loads((rdir / "map.json").read_text()); ctl = json.loads((rdir / "controls.json").read_text())
    new = load_labels(rdir / "labels.json")
    omap = json.loads((run_dir / "labelling" / "map.json").read_text()); first = {omap[k]: v for k, v in load_labels(run_dir / "labelling" / "A.json").items() if k in omap}
    keys = [(p, idmap[p]) for p in new if p in idmap and idmap[p] in final]
    out = {"sample": len(keys), "relabel_agrees": sum(1 for p, k in keys if agree(new[p], final[k])),
           "first_labeller_agrees": sum(1 for p, k in keys if k in first and agree(first[k], final[k]))}
    good = lambda p: new[p]["verdict"] == "real" if ctl[p]["truth"] == "real" else new[p]["verdict"] in ("wrong", "none")
    out["controls"] = f"{sum(1 for p in ctl if p in new and good(p))} of {len(ctl)}"
    print(json.dumps(out)); return out

def main(a):
    if len(a) >= 2 and a[0] == "export":
        apps = a[a.index("--apps") + 1] if "--apps" in a else sys.exit("--apps DIR is required (outside eval/)")
        chunk = int(a[a.index("--chunk") + 1]) if "--chunk" in a else 30
        export(a[1], apps, chunk, controls=int(a[a.index("--controls") + 1]) if "--controls" in a else 3); return 0
    if len(a) == 4 and a[0] == "ties": ties(*a[1:]); return 0
    if len(a) in (4, 5) and a[0] == "final": final(*a[1:]); return 0
    if len(a) == 3 and a[0] == "recheck": recheck(*a[1:]); return 0
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
