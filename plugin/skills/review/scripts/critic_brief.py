#!/usr/bin/env python3
"""Build each blind reviewer's brief (SC-30), cache-friendly: one shared part, byte-identical for every reviewer, then a
short per-reviewer part (the letter, the reading order and the file to write). Parallel reviewers that start with the
same prefix can share a prompt cache; whether they do is measured with the cost hook (critic_ledger.py tokens:
cache_read_input_tokens per reviewer), not assumed.

usage:
  critic_brief.py [--letters A,B,C] [--intent TEXT] [--packet]
        reads .critic/change-map.json and the ledger; writes .critic/briefs/brief-<letter>.md and prints their paths.
        The lead passes each file's text, unchanged, as that reviewer's prompt.

What a brief holds (shared part): the tier, the stated intent, the references folder, the rules and change-map paths,
the owner's recorded decisions, up to five past false positives, and the payload list in a fixed (sorted) order.
Per reviewer: A reads in risk order, B reversed, C shuffled (seeded by the run number, so a rerun gives the same order).
Nothing from the scan, the other reviews or the author's conversation is ever included.

--packet (SC-35, opt-in until the eval measures it): for a lite or trivial review of a git change, the shared part also
carries a compact change packet: each changed hunk with CONTEXT lines around it and line numbers, a deletion-only hunk
as one line, a new file whole. Reviewers can still open whole files in their copy. Off by default, because a bug that
spans hunks could be missed; Ryan's A/B run on the kit decides whether it becomes the default."""
import json, os, pathlib, random, sys, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"

def load(p, default):
    try: return json.loads(p.read_text()) if p.is_file() and not p.is_symlink() else default
    except (OSError, ValueError): return default

def order_for(letter, files, run):
    if letter == "A": return list(files)
    if letter == "B": return list(reversed(files))
    out = list(files); random.Random(f"{run}-{letter}").shuffle(out); return out

CONTEXT = 3
PACKET_MAX = 60_000  # characters; past this the packet is left out and the reviewer reads the files

def packet(cm):
    """The compact change packet, or None when it doesn't apply (not a git change) or wouldn't be smaller."""
    if cm.get("mode") != "diff" or not isinstance(cm.get("hunks"), dict): return None
    out = ["", "## Change packet (changed lines with context; open the whole file in your copy when you need more)"]
    new = set(cm.get("new_files") or [])
    for f in cm.get("files") or []:
        p = ROOT / f
        try: lines = p.read_text(encoding="utf-8", errors="replace").split("\n") if p.is_file() and not p.is_symlink() else None
        except OSError: lines = None
        if lines is None: out.append(f"\n### {f}\n(deleted or unreadable)"); continue
        if f in new: out.append(f"\n### {f} (new file)"); out += [f"{i:>5}  {t}" for i, t in enumerate(lines, 1)]; continue
        spans, gone = [], []
        for start, count in cm["hunks"].get(f, []):
            if count == 0: gone.append(start); continue
            spans.append([max(1, start - CONTEXT), min(len(lines), start + count - 1 + CONTEXT)])
        spans.sort(); merged = []
        for a_, b_ in spans:
            if merged and a_ <= merged[-1][1] + 1: merged[-1][1] = max(merged[-1][1], b_)
            else: merged.append([a_, b_])
        if not merged and not gone: continue
        out.append(f"\n### {f}")
        for g in gone: out.append(f"(lines deleted after line {g})")
        for a_, b_ in merged:
            out.append(f"@@ lines {a_}-{b_}"); out += [f"{i:>5}  {lines[i - 1]}" for i in range(a_, b_ + 1)]
    text = "\n".join(out) + "\n"
    return text if len(text) <= PACKET_MAX else None

UI_EXT = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss", ".less"}

def reading_list(files):
    """Only the references this payload needs (decision 31): the core rubric, the sandbox and the finding record always;
    the design rubric and the AI-tells list for interface files; the lens rows the job plan picked."""
    ui = any(pathlib.PurePosixPath(f).suffix.lower() in UI_EXT for f in files)
    plan = load(D / "plan.json", None)
    if isinstance(plan, dict) and isinstance(plan.get("lenses"), list): lenses = plan["lenses"]
    else:
        import critic_plan
        lenses = critic_plan.lenses_for(files)
    out = ["rubrics.md" + (" (both rubrics)" if ui else " (Rubric 1 and the rest; skip Rubric 2: design, no interface files here)"), "sandbox.md", "finding-record.md"]
    if ui: out.append("ai-tells.md")
    if lenses: out.append("lenses.md, only the sections " + ", ".join(f'"{x[0].upper() + x[1:]}"' for x in lenses))
    return "; ".join(out) + "."

SECURITY_FOCUS = ("- Focus: security (security scan mode). Look for ways this can be attacked, abused or made to leak: injection, "
                  "authentication and access control, secrets, unsafe parsing or deserialisation, requests the server makes for a "
                  "user (SSRF), path traversal, the supply chain, and the integrity of what a page loads, links to or posts to. "
                  "Report a defect outside security only when it is Critical.")

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
              *([SECURITY_FOCUS] if load(D / "focus.json", {}).get("focus") == "security" else []),
              f"- Stated intent: {intent if intent else '(none stated; do not guess one)'}",
              f"- References folder: {refs}. Read: " + reading_list(files),
              f"- Change map: {D / 'change-map.md'}",
              f"- Python syntax tree, to trace instead of guess (run from your workspace): python3 {HERE / 'ast_view.py'} FILE [LINE|START-END]"]
    if (D / "rules.md").is_file(): shared.append(f"- Project rules: {D / 'rules.md'} (apply only the rules whose paths match the payload)")
    shared += ["", "## The owner's recorded decisions (not re-argued on taste)"] + ([f"- {x}" for x in decisions] or ["- none recorded"])
    shared += ["", "## Not findings (the owner's past rulings)"] + ([f"- {x}" for x in fps] or ["- none recorded"])
    shared += ["", f"## Payload ({len(files)} files; your reading order is below)"] + [f"- {f}" for f in sorted(files)]
    shared_text = "\n".join(shared) + "\n"
    if "--packet" in a and tier in ("lite", "trivial"):
        pk = packet(cm)
        shared_text += pk if pk else "\n(No change packet: this is not a git change, or the packet would not be smaller than the files.)\n"
    from critic_findings import refuse_linked_state
    refuse_linked_state(ROOT)  # never write a brief through a link a cloned repository planted in .critic/
    out = D / "briefs"
    if out.is_symlink() or D.is_symlink(): sys.exit("critic_brief: .critic/briefs is a link; refusing to write through it")
    out.mkdir(parents=True, exist_ok=True)
    for x in letters:
        mine = ["", "---", "", f"Reviewer letter: {x}", "", "Read the files in this order:"] + [f"{i}. {f}" for i, f in enumerate(order_for(x, files, L.get("run", 0)), 1)]
        mine += ["", f"Write your result to {D / 'reviews' / f'review-{x}.json'}"]
        p = out / f"brief-{x}.md"; p.write_text(shared_text + "\n".join(mine) + "\n", encoding="utf-8"); print(p.relative_to(ROOT))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
