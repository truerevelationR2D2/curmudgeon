#!/usr/bin/env python3
"""Rung 3 of the evidence ladder: replay recorded review runs through today's counting scripts, with no model. Each
folder in eval/replays/ holds what the models produced in one accepted run (the blind reviews, the dedup agent's
groups and the verifiers' verdicts), plus the cited files as they stood. The replay runs critic_ledger start, then
critic_merge tally, tally --groups and apply, and compares the result (ids, impacts, votes, verifier outcomes and the
counts line), what the tally dropped, retracted, rejected and suppressed, and the verifier log, with expected.json.

  replay.py                         compare; exit 1 on any difference, printing it
  CRITIC_UPDATE_REPLAY=1 replay.py  rewrite expected.json on purpose, after a change meant to alter the outcome

A missing recording file fails; nothing ever falls back to a model. Idea from vcrpy's record-once rule (MIT); this is
our own code."""
import difflib, json, os, pathlib, shutil, subprocess, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
S = HERE.parent / "plugin" / "skills" / "review" / "scripts"

def replay(rec):
    man = json.loads((rec / "manifest.json").read_text())
    need = [rec / p for p in man["reviews"]] + [rec / man["groups"], rec / man["verdicts"], rec / "tree"]
    missing = [str(p.relative_to(rec)) for p in need if not p.exists()]
    if missing: return None, f"recording incomplete: {', '.join(missing)}"
    with tempfile.TemporaryDirectory() as t:
        root = pathlib.Path(t); shutil.copytree(rec / "tree", root, dirs_exist_ok=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        def go(*a):
            r = subprocess.run([sys.executable, "-I", *map(str, a)], cwd=root, capture_output=True, text=True, timeout=300, env=env)
            if r.returncode != 0: raise RuntimeError(f"{a[0].name} {' '.join(map(str, a[1:]))} failed: {r.stdout[-400:]}{r.stderr[-400:]}")
            return r
        go(S / "critic_ledger.py", "start", "review", "--tier", "full")
        (root / ".critic" / "reviews").mkdir(parents=True, exist_ok=True)
        revs = []
        for p in man["reviews"]:
            dst = root / ".critic" / "reviews" / pathlib.Path(p).name; shutil.copy(rec / p, dst); revs.append(f".critic/reviews/{dst.name}")
        shutil.copy(rec / man["groups"], root / ".critic" / "groups.json"); shutil.copy(rec / man["verdicts"], root / "verdicts.json")
        go(S / "critic_merge.py", "tally", *revs)
        go(S / "critic_merge.py", "tally", *revs, "--groups", ".critic/groups.json")
        go(S / "critic_merge.py", "apply", "verdicts.json")
        rows = [json.loads(x) for x in (root / ".critic" / "findings.jsonl").read_text().splitlines() if x.strip()]
        tally = json.loads((root / ".critic" / "tally.json").read_text())
        stages = {k: sorted((x.get("finding") or x).get("id") or "" for x in tally.get(k, [])) for k in ("dropped", "retracted", "rejected", "suppressed")}
        refuted = sorted({(json.loads(x).get("id"), json.loads(x).get("kind")) for x in (root / ".critic" / "refutations.jsonl").read_text().splitlines() if x.strip()}) if (root / ".critic" / "refutations.jsonl").exists() else []
        counts = next((l for l in (root / ".critic" / "counts.md").read_text().splitlines() if l.startswith("Counts for the VERDICT")), "")
    keep = ("id", "impact", "file", "line", "votes", "of", "verifier", "confidence")
    return {"counts": counts, "findings": sorted(({k: r.get(k) for k in keep} for r in rows), key=lambda r: r["id"]),
            "tally": stages, "verifier_log": [list(x) for x in refuted]}, None

def main():
    update = os.environ.get("CRITIC_UPDATE_REPLAY") == "1"; bad = 0
    recs = sorted(p for p in (HERE / "replays").iterdir() if p.is_dir()) if (HERE / "replays").is_dir() else []
    if not recs: print("no recordings in eval/replays/"); return 1
    for rec in recs:
        try: got, err = replay(rec)
        except RuntimeError as e: got, err = None, str(e)
        if err: print(f"FAIL {rec.name}: {err}"); bad += 1; continue
        text = json.dumps(got, indent=1, ensure_ascii=False) + "\n"
        exp = rec / "expected.json"
        if update: exp.write_text(text, encoding="utf-8"); print(f"wrote {rec.name}/expected.json"); continue
        if not exp.exists(): print(f"MISSING {rec.name}/expected.json (run with CRITIC_UPDATE_REPLAY=1 once)"); bad += 1; continue
        if exp.read_text(encoding="utf-8") != text:
            bad += 1; print(f"CHANGED {rec.name}:")
            sys.stdout.writelines(difflib.unified_diff(exp.read_text().splitlines(True), text.splitlines(True), "expected", "now", n=1))
        else: print(f"ok {rec.name}")
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())
