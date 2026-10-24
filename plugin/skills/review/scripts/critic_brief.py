#!/usr/bin/env python3
"""Build each blind reviewer's brief (SC-30), cache-friendly: one shared part, byte-identical for every reviewer, then a
short per-reviewer part (the letter, the reading order and the file to write). Parallel reviewers that start with the
same prefix can share a prompt cache; whether they do is measured with the cost hook (critic_ledger.py tokens:
cache_read_input_tokens per reviewer), not assumed.

usage:
  critic_brief.py [--letters A,B,C] [--intent TEXT]
        reads .critic/change-map.json and the ledger; writes .critic/briefs/brief-<letter>.md and prints their paths.
        The lead passes each file's text, unchanged, as that reviewer's prompt.

What a brief holds (shared part): the tier, the stated intent, the references folder, the rules and change-map paths,
the owner's recorded decisions, up to five past false positives, and the payload list in a fixed (sorted) order.
Per reviewer: A reads in risk order, B reversed, C shuffled (seeded by the run number, so a rerun gives the same order).
Nothing from the scan, the other reviews or the author's conversation is ever included."""
import json, os, pathlib, random, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT", os.getcwd())).resolve(); D = ROOT / ".critic"

def load(p, default):
    try: return json.loads(p.read_text()) if p.is_file() and not p.is_symlink() else default
    except (OSError, ValueError): return default

def order_for(letter, files, run):
    if letter == "A": return list(files)
    if letter == "B": return list(reversed(files))
    out = list(files); random.Random(f"{run}-{letter}").shuffle(out); return out

def main(a):
    if a[:1] in (["-h"], ["--help"]): print(__doc__); return 0
    letters, intent = None, None
    if "--letters" in a and a.index("--letters") + 1 < len(a): letters = [x.strip().upper() for x in a[a.index("--letters") + 1].split(",") if x.strip()]
    if "--intent" in a and a.index("--intent") + 1 < len(a): intent = a[a.index("--intent") + 1]
    cm = load(D / "change-map.json", None)
    if not cm: sys.exit("critic_brief: no .critic/change-map.json; run critic_map.py first")
    L = load(D / "ledger.json", {})
    tier = L.get("tier") or cm.get("tier") or "full"
    letters = letters or (["A", "B", "C"] if tier == "full" else ["A"])
    files = [str(f) for f in cm.get("files") or []]
    intent = intent if intent is not None else (cm.get("intent") or "")
    decisions = [d.get("text", "") for d in L.get("decisions", []) if isinstance(d, dict) and d.get("text")]
    fps = []
    for x in (L.get("false_positives") or [])[-5:]:
        what = (L.get("findings") or {}).get(x.get("id", ""), {}).get("summary", x.get("rule", ""))
        fps.append(f"{what} at {x.get('where', '')}: {x.get('why', '')}")
    refs = HERE.parent / "references"
    shared = ["# Curmudgeon review brief", "",
              "You are reviewing work by an unknown contractor. Follow your agent instructions; this brief only says what to review.", "",
              f"- Tier: {tier}",
              f"- Stated intent: {intent if intent else '(none stated; do not guess one)'}",
              f"- References folder: {refs} (read rubrics.md, sandbox.md, ai-tells.md and output-contract.md)",
              f"- Change map: {D / 'change-map.md'}"]
    if (D / "rules.md").is_file(): shared.append(f"- Project rules: {D / 'rules.md'} (apply only the rules whose paths match the payload)")
    shared += ["", "## The owner's recorded decisions (not re-argued on taste)"] + ([f"- {x}" for x in decisions] or ["- none recorded"])
    shared += ["", "## Not findings (the owner's past rulings)"] + ([f"- {x}" for x in fps] or ["- none recorded"])
    shared += ["", f"## Payload ({len(files)} files; your reading order is below)"] + [f"- {f}" for f in sorted(files)]
    shared_text = "\n".join(shared) + "\n"
    out = D / "briefs"
    if out.is_symlink() or D.is_symlink(): sys.exit("critic_brief: .critic/briefs is a link; refusing to write through it")
    out.mkdir(parents=True, exist_ok=True)
    for x in letters:
        mine = ["", "---", "", f"Reviewer letter: {x}", "", "Read the files in this order:"] + [f"{i}. {f}" for i, f in enumerate(order_for(x, files, L.get("run", 0)), 1)]
        mine += ["", f"Write your result to {D / 'reviews' / f'review-{x}.json'}"]
        p = out / f"brief-{x}.md"; p.write_text(shared_text + "\n".join(mine) + "\n", encoding="utf-8"); print(p.relative_to(ROOT))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
