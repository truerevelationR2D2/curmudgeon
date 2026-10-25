#!/usr/bin/env python3
"""The mechanical half of the teardown, written by a script (SC-76, the lead diet; a lab until measured, rulings
§5.37 and §5.38). It reads what the merge already decided (.critic/findings.jsonl, nits.jsonl, tally.json, counts.md,
change-map.json, variants.md) and writes .critic/teardown-skeleton.md in the output contract's layout: the verdict line,
the counts, every finding with its evidence, failing case and remedy, the Lows as one line each, the Nits, the sandbox
ledger, the panel line, Not reviewed and the hooks. The lead fills only the parts marked <!-- LEAD: ... -->: the intent
gate, the risk map's pre-mortem, the five fixes worth the most, and Not checked. Nothing here decides a finding.

usage: critic_skeleton.py            (writes .critic/teardown-skeleton.md)
Switched on for a run by CURMUDGEON_LAB=skeleton (critic_run.py next then writes it before the teardown step)."""
import json, os, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import IMPACTS, read_jsonl, refuse_linked_state

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
LEAD = lambda what: f"<!-- LEAD: {what} -->"

def section_of(f):
    """Which contract section a finding belongs in, from its own category (the reviewer's choice)."""
    c = str(f.get("category", "")).lower()
    if re.search(r"anti-?ai|ai-tell|boilerplate|default", c): return "A"
    if re.search(r"claim|doc|readme|number|arith", c): return "D"
    if re.search(r"a11y|ux|ui|layout|focus|contrast|wcag|responsive|visual|copy", c): return "U"
    return "C"

def one(f, n, prefix):
    where = f"{f.get('file', '')}:{f.get('line', '')}"
    more = [x for x in (f.get("locations") or []) if x != where]
    head = (f"- **{prefix}{n}** `{where}`" + (f" (also at {', '.join(more[:6])})" if more else "") +
            f" | **IMPACT: {f['impact']}** | `{f.get('id', '')}` · confidence {f.get('confidence', '?')} · votes {f.get('votes', 1)}/{f.get('of', 1)}"
            f" | **{'UX flaw' if prefix == 'U' else 'Defect'}:** {f.get('title', '')}")
    if f["impact"] == "Low":  # the contract allows one line for a Low
        return [f"- **{prefix}{n}** `{where}` | Low | `{f.get('id', '')}` | {f.get('title', '')}" + (f" {f.get('remediation', '')}" if f.get("remediation") else "")]
    out = [head, f"  - **Evidence:** {f.get('evidence') or LEAD('evidence missing from the finding record')}",
           f"  - **Failing case:** {f.get('failing_case') or LEAD('failing case missing')}",
           f"  - **Remediation theory:** {f.get('remediation') or LEAD('remedy missing')}"]
    if f.get("memory_note"): out.append(f"  - Like past dismissals: {f['memory_note']}")
    return out

def verdict_word(final):
    imp = {f["impact"] for f in final}
    return "BLOCK" if imp & {"Critical", "High"} else ("CONCERNS" if imp & {"Medium", "Low"} else "CLEAN")

def main():
    refuse_linked_state(ROOT)
    final = read_jsonl(D / "findings.jsonl"); nits = read_jsonl(D / "nits.jsonl")
    try: T = json.loads((D / "tally.json").read_text())
    except (OSError, ValueError): T = {}
    try: cm = json.loads((D / "change-map.json").read_text())
    except (OSError, ValueError): cm = {}
    counts_md = (D / "counts.md").read_text() if (D / "counts.md").is_file() else ""
    cnt = {k: sum(1 for f in final if f["impact"] == k) for k in IMPACTS}
    counts = ", ".join(f"{cnt[k]} {k}" for k in IMPACTS)
    word = verdict_word(final)
    md = [f"**{word}** · Counts: {counts}", "", "#### INTENT GATE",
          (f"Stated intent: {cm['intent']}. " if cm.get("intent") else "No stated intent. ") + LEAD("questions asked and answers, or 'not needed: why'; Asked but not done / Done but not asked"),
          "", "#### RISK MAP", "Reading order by risk: " + ", ".join(f"`{x}`" for x in (cm.get("files") or [])[:12]) + ".", LEAD("one-line pre-mortem"), "", "#### SANDBOX LEDGER"]
    sb = T.get("sandbox") or []
    md += [f"- {x['id']} {x['scenario']} → {x['happens']} → {x['result']} ({x['how']})" for x in sb] if sb else ["none recorded"]
    by = {"C": [], "U": [], "A": [], "D": []}
    for f in final: by[section_of(f)].append(f)
    titles = {"C": "1. CODE AND ARCHITECTURE", "U": "2. UI/UX & INTERACTION FRICTION", "A": "3. THE \"ANTI-AI\" CLEANUP", "D": "4. CLAIMS, NUMBERS AND CONSISTENCY"}
    for k in ("C", "U", "A", "D"):
        md += ["", f"#### {titles[k]}"]
        if not by[k]: md.append("None."); continue
        for i, f in enumerate(by[k], 1): md += one(f, i, k)
    md += ["", "**Nits** (not counted): " + ("; ".join(f"`{n_.get('file', '')}:{n_.get('line', '')}` {n_.get('title', '')}" for n_ in nits[:20]) or "none") + "."]
    panel = re.search(r"^Reviewers: .*$", counts_md, re.M)
    nr = re.search(r"^Not reviewed[^\n]*$", counts_md, re.M)
    md += ["", "#### 5. VERDICT", f"**{word}**", f"Counts: {counts}",
           f"Panel: {panel.group(0) if panel else 'see counts.md'}; dropped {len(T.get('dropped', []))}, retracted {len(T.get('retracted', []))}, rejected {len(T.get('rejected', []))}, hidden by your rulings {len(T.get('suppressed', []))}.",
           "The five fixes worth the most per hour: " + LEAD("five fixes, ranked"),
           "Not checked: " + LEAD("everything in scope not verified, and why"),
           nr.group(0) if nr else "Not reviewed: " + LEAD("from counts.md")]
    if (D / "variants.md").is_file(): md.append("Variants: see `.critic/variants.md` (listed apart, not in the Counts line).")
    md += ["Change map: `.critic/change-map.md`", "", "- `/curmudgeon:review fix` to fix every finding.", "- `/curmudgeon:fix patch [id]` to fix only that one."]
    out = D / "teardown-skeleton.md"
    if out.is_symlink(): sys.exit("critic_skeleton: refusing to write through a link")
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(final)} findings, {len(nits)} nits, {sum(1 for l in md if 'LEAD:' in l)} parts for the lead")
    return 0

if __name__ == "__main__":
    if any(a in ("-h", "--help") for a in sys.argv[1:]): print(__doc__); sys.exit(0)
    sys.exit(main())
