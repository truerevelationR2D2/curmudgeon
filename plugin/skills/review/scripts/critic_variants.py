#!/usr/bin/env python3
"""The variant hunt (SC-56, after Big Sleep's variant analysis): a confirmed Critical or High bug is often written
again elsewhere. This finds the same pattern in other files, and every hit is then judged like any finding.

usage:
  critic_variants.py find
        For each finding in .critic/findings.jsonl that is Critical or High and confirmed or likely, turn its quote into
        a pattern (identifiers and operators kept; string and number literals and spacing loosened) and search the
        project's files of the same kind for it, the original line excluded. Each hit becomes a verify packet in
        .critic/verify-variants/ (the real line as its quote, the original finding's failing case to check against).
        Prints the verifier batches to start; at most 10 hits per finding, 50 in all.
  critic_variants.py apply [VERDICT_FILE ...]
        Apply the blind verifiers' verdicts with the same rules as critic_merge.py apply: a confirmation needs its
        evidence, a refutation needs a real guard. Only CONFIRMED variants (or downgraded ones) are kept; a variant
        with no verdict or an unclear one is listed as not verified and never reported as a finding, because a script's
        guess is not a finding (precision first). Writes .critic/variants.jsonl and .critic/variants.md.

Variants never change the main counts: the teardown lists them in their own section, from variants.md."""
import json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from critic_findings import verifier_batches, confirmation_problem, downgrade_problem, refutation_problem, security_refutation_problem, redact_finding_text, read_jsonl, log_run, refuse_linked_state, scrub

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
SKIP = {"node_modules", "dist", "build", "vendor", ".git", "__pycache__", ".next", "coverage", ".critic", ".venv", "venv"}
PER, TOTAL = 10, 50
IMP = ["Low", "Medium", "High", "Critical"]

def pattern(quote):
    """A regex from a quoted line: identifiers and operators exact, literals and spaces loose. None when too generic."""
    q = str(quote or "").strip()
    if len(re.sub(r"\W", "", q)) < 8: return None
    toks = re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`|\d+(?:\.\d+)?|\w+|\S", q)
    out = []
    for t in toks:
        if t[0] in "'\"`": out.append(r"(?:'[^']*'|\"[^\"]*\"|`[^`]*`)")
        elif re.fullmatch(r"\d+(?:\.\d+)?", t): out.append(r"\d+(?:\.\d+)?")
        else: out.append(re.escape(t))
    words = [t for t in toks if re.fullmatch(r"[A-Za-z_]\w*", t)]
    if len(set(words)) < 2: return None  # one identifier alone matches too much
    return re.compile(r"\s*".join(out))

def files_like(ext):
    for top, dirs, names in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP and not os.path.islink(os.path.join(top, x))]
        for n in names:
            if os.path.splitext(n)[1] == ext:
                p = pathlib.Path(top) / n
                if p.is_file() and not p.is_symlink() and p.stat().st_size < 2_000_000: yield p

def find():
    rows = read_jsonl(D / "findings.jsonl") if (D / "findings.jsonl").exists() else []
    out = D / "verify-variants"
    if out.is_symlink(): sys.exit("critic_variants: .critic/verify-variants is a link; refusing")
    out.mkdir(parents=True, exist_ok=True)
    vv = D / "verdicts-variants"  # verdicts on the packets being replaced: their ids are reused, so they must never meet the new ones (§5.56 round 2)
    if vv.is_dir() and not vv.is_symlink():
        for old in vv.glob("*.json"): old.unlink()
    for old in out.glob("*.json"): old.unlink()
    for stale in (D / "variants.md", D / "variants.jsonl"):  # an earlier run's variants are never read as this run's
        if stale.is_file() and not stale.is_symlink(): stale.unlink()
    n = 0
    for f in rows:
        if f.get("impact") not in ("Critical", "High") or f.get("confidence") not in ("confirmed", "likely"): continue
        rx = pattern(f.get("quote")); ext = os.path.splitext(str(f.get("file") or ""))[1]
        if not rx or not ext: continue
        hits = 0
        for p in files_like(ext):
            rel = str(p.relative_to(ROOT))
            try: lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError: continue
            for i, l in enumerate(lines, 1):
                if len(l) > 2000 or not rx.search(l): continue
                if rel == f.get("file") and i == int(f.get("line") or 0): continue
                vid = f"V-{f['id'][2:8]}-{hits + 1}"
                packet = {"id": vid, "variant_of": f["id"], "category": f.get("category"), "impact": f.get("impact"), "file": rel, "line": i, "quote": l.strip()[:300],
                          "title": f"Possible variant of {f['id']}: {f.get('title', '')}"[:200], "failing_case": f"The same failure as {f['id']}: {f.get('failing_case', '')}"[:600]}
                (out / f"{vid}.json").write_text(json.dumps(scrub(packet), indent=1, ensure_ascii=False))
                hits += 1; n += 1
                if hits >= PER or n >= TOTAL: break
            if hits >= PER or n >= TOTAL: break
        if n >= TOTAL: break
    packets = sorted(out.glob("*.json"))
    mark = D / "variants-found.json"  # critic_run.py next reads this: the hunt ran for these findings, even when it found nothing
    if not mark.is_symlink(): mark.write_text(json.dumps({"variants": n}) + "\n")
    print(f"variant hunt: {n} possible variant(s) in .critic/verify-variants")
    try: tier = json.loads((D / "ledger.json").read_text()).get("tier") or "full"
    except (OSError, ValueError, AttributeError): tier = "full"  # as critic_run.py next: an unknown tier is treated as the full one
    for i, b in enumerate(verifier_batches(packets, tier), 1): print(f"  verifier {i}: " + " ".join(str(p.relative_to(ROOT)) for p in b))
    if n: print("next: start curmudgeon:curmudgeon-verifier agents on these packets (blind, as in step 4); the stop hook saves each verifier's ```json list in .critic/verdicts-variants/ (never retype one), then critic_variants.py apply .critic/verdicts-variants/*.json")
    return 0

def apply(paths):
    packets = {p.stem: json.loads(p.read_text()) for p in sorted((D / "verify-variants").glob("*.json"))} if (D / "verify-variants").is_dir() else {}
    verdicts = {}; by_hand = []
    for p in paths:
        try: rows = json.loads(pathlib.Path(p).read_text())
        except (OSError, ValueError) as e: sys.exit(f"critic_variants: can't read {p}: {e}")
        if pathlib.Path(p).resolve().parent != (D / "verdicts-variants").resolve(): by_hand.append(pathlib.Path(p).name)  # not saved by the verifier's stop hook (batch 1 review, as critic_merge.py apply)
        for v in rows if isinstance(rows, list) else [rows]:
            if isinstance(v, dict) and v.get("id") in packets: verdicts[v["id"]] = v
    kept, refuted, open_, ignored = [], [], [], []
    for vid, f in packets.items():
        v = verdicts.get(vid)
        if not v: open_.append((f, "no verdict")); continue
        kind = str(v.get("verdict", "unclear")).lower(); raw = str(v.get("refutation") or v.get("reason") or "")
        if kind == "confirmed" and confirmation_problem(v, root=ROOT): kind = "unclear"
        if kind == "refuted":
            if not (refutation_problem(raw, f["impact"], v.get("reproduced"), root=ROOT) or security_refutation_problem(v, f)): refuted.append((f, redact_finding_text(raw))); continue
            kind = "unclear"
        if kind == "downgrade":  # a lower impact is a judgement, not evidence: a variant needs the confirmation's evidence too
            kind = "confirmed" if not confirmation_problem(v, root=ROOT) else "unclear"
            new_ = str(v.get("impact_after", "")).title()  # the same downgrade rule as the main findings (03 §5.57.2); without it the variant keeps its impact
            if kind == "confirmed" and new_ in IMP:
                dp = downgrade_problem(f["impact"], new_, v.get("reproduced"), str(v.get("note") or raw), root=ROOT)
                if not dp: f = dict(f, impact=new_)
                else: f = dict(f, confidence="likely"); ignored.append(f"{vid}: downgrade to {new_} ignored ({dp}); kept at {f['impact']}")  # as critic_merge.py apply: not a clean confirmation
        if kind == "confirmed": kept.append(dict(f, confidence=f.get("confidence", "confirmed"), source="variant", verifier_note=redact_finding_text(str(v.get("note") or ""))[:300]))
        else: open_.append((f, "unclear"))
    (D / "variants.jsonl").write_text("".join(json.dumps(scrub(x), ensure_ascii=False) + "\n" for x in kept))
    md = ["# Variants (the variant hunt; listed apart, never in the main counts)", ""]
    if by_hand: md += [f"DEGRADED: verdicts not saved by the verifier's stop hook (written or edited outside .critic/verdicts-variants/): {', '.join(by_hand[:8])}", ""]
    md += [f"Confirmed by blind verification: {len(kept)}" + (f" ({sum(x['confidence'] == 'likely' for x in kept)} of them likely: a downgrade was ignored)" if any(x["confidence"] == "likely" for x in kept) else "")]
    md += [f"- {x['id']} {x['impact']} {x['file']}:{x['line']}: {x['title']}" + (" (likely)" if x["confidence"] == "likely" else "") for x in kept]
    md += [f"  (note) {x}" for x in ignored]
    md += ["", f"Not verified (no verdict or unclear; not findings): {len(open_)}"] + [f"- {f['id']} {f['file']}:{f['line']} ({why})" for f, why in open_]
    md += ["", f"Refuted: {len(refuted)}"] + [f"- {f['id']} {f['file']}:{f['line']}: {why[:160]}" for f, why in refuted]
    (D / "variants.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"variants: {len(kept)} confirmed, {len(open_)} not verified, {len(refuted)} refuted (.critic/variants.md)")
    return 0

def main(a):
    refuse_linked_state(ROOT)
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    log_run(ROOT, "script", "critic_variants.py " + " ".join(a[:1]))
    if a[0] == "find": return find()
    if a[0] == "apply": return apply(a[1:])  # with no verdict files every variant is listed as not verified (critic_run.py next --apply-now; batch 1 review)
    print(__doc__); return 2

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
