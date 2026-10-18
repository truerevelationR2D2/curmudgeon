#!/usr/bin/env python3
"""Score Critic reviews against a planted-flaw fixture. Measures what it catches AND how often it's wrong.

usage:
  score.py REVIEW.md [REVIEW2.md ...] --suite 1|2|3 [--refactored DIR] [--baseline FILE] [--set-baseline]
  score.py REVIEW.md --clean 1|2           a review of a clean twin: every Critical/High/Medium finding is a false alarm
  score.py --label                         list unmatched findings from the last scoring for labelling (writes fp_labels.json stubs)
  score.py --refutations .critic/refutations.jsonl   label the verifier's drops (refutation_labels.json) and report how often
                                           it dropped a real bug

Each REVIEW is a teardown (.critic/last-review.md). When a .critic/findings.jsonl sits beside it, the structured
findings are used; otherwise finding blocks are parsed from the markdown.

Reported:
  recall          planted defects found (each matched inside one finding that names the right file)
  precision       true findings / (true + labelled false alarms). Unlabelled unmatched findings are listed, not guessed
  decoy rate      suite 3: correct-but-suspicious code reported as a defect (should be 0)
  contract        the output contract, parsed
  behaviour       browser tests on the refactored copy (suites 1 and 2)
  repeats         with several reviews of the same suite: recall range, plants found in every run (pass^k), and the
                  overlap of finding ids between runs (stability)
Exit 1 when any recorded baseline number drops (precision included, even if recall rose). Exit 2 on bad usage."""
import json, pathlib, re, statistics, sys
HERE = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None): return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
FLAGS_WITH_VALUE = {"--suite", "--refactored", "--baseline", "--clean", "--refutations"}
reviews = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in FLAGS_WITH_VALUE)]
if not reviews and "--label" not in args and "--refutations" not in args: print(__doc__); sys.exit(2)
LABELS = HERE / "fp_labels.json"; labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}

def load(path):
    p = pathlib.Path(path)
    try: text = p.read_text(encoding="utf-8")
    except OSError as e: print(f"score.py: can't read {path}: {e}"); sys.exit(2)
    fj = p.parent / "findings.jsonl"
    rows = []
    if fj.exists():
        for line in fj.read_text().splitlines():
            if line.strip(): rows.append(json.loads(line))
    blocks = re.split(r"\n(?=\s*[-*]?\s*\*\*[CUADL]\d+\*\*|\s*[-*]?\s*L\d+\s|#{2,4} )", text)
    if rows:  # one block per structured finding: its fields joined, so matching sees the same words the teardown shows
        blocks = [" ".join(str(r.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation")) for r in rows]
    return text, rows, blocks

def match_key(key, blocks):
    hits, used = {}, set()
    for name, k in key.items():
        for bi, b in enumerate(blocks):
            if (not k["file"] or k["file"].lower() in b.lower()) and any(re.search(p, b, re.I) for p in k["any"]):
                hits[name] = bi; used.add(bi); break
    return hits, used

def lab_key(b): return re.sub(r"\W+", " ", b.lower())[:160]

def contract(review, rows):
    def section(title):
        m = re.search(r"^#{2,4}[^\n]*" + re.escape(title) + r"[^\n]*\n(.*?)(?=\n#{2,4} |\Z)", review, re.S | re.I | re.M)
        return m.group(1) if m else None
    verdict = section("VERDICT") or ""
    ids = {}
    for fid, imp in re.findall(r"\*\*([CUAD]\d+)\*\*[^\n]*?\b(Critical|High|Medium|Low)\b", review): ids.setdefault(fid, imp.title())
    lows = re.findall(r"^\s*[-*]?\s*\**L\d+\**\s", review, re.M)
    actual = {s: sum(1 for x in ids.values() if x == s) for s in ("Critical", "High", "Medium", "Low")}; actual["Low"] += len(lows)
    cline = next((l for l in verdict.splitlines() if re.search(r"\bcounts?\b", l, re.I)), verdict)  # the contract's Counts line, when there is one
    stated = {k: int(v) for k, v in re.findall(r"(Critical|High|Medium|Low)\s*[:=]?\s*(\d+)", cline)} or {k: int(v) for v, k in re.findall(r"(\d+)\s*(Critical|High|Medium|Low)\b", cline)}
    if rows:  # with structured findings, the stated counts must equal the merged findings
        actual = {s: sum(1 for r in rows if r.get("impact") == s) for s in ("Critical", "High", "Medium", "Low")}
    cu = sum(1 for k in ids if k[0] in "CU")
    c = {
        "no opening filler": not re.search(r"^\W*(great|nice|good|solid|overall|this (is|looks)|thanks|here is|here's|i )", review.strip()[:120], re.I),
        "all contract headers": all(section(h) is not None for h in ["INTENT GATE", "RISK MAP", "SANDBOX LEDGER", "CRITICAL CODE ARCHITECTURE DEFECTS", "UI/UX", "ANTI-AI", "CLAIMS, NUMBERS", "VERDICT"]),
        "exactly one verdict word": len(set(re.findall(r"\*\*(BLOCK|CONCERNS|CLEAN)\*\*", verdict))) == 1 or len(set(re.findall(r"\b(BLOCK|CONCERNS|CLEAN)\b", verdict))) == 1,
        "verdict counts match the findings": bool(stated) and all(stated.get(s, 0) == actual[s] for s in actual),
        "evidence on every code/UX finding": cu == 0 or len(re.findall(r"\*\*Evidence:?\*\*", review, re.I)) >= cu,
        "failing case on every code/UX finding": cu == 0 or len(re.findall(r"\*\*Failing case:?\*\*", review, re.I)) >= cu,
        "Not checked line": "Not checked:" in verdict,
        "Not reviewed line": "Not reviewed:" in verdict,
        "banner when single context": (not re.search(r"single context|could not start|cannot start", review[:400], re.I)) or review.lstrip().startswith(("DEGRADED", "BLOCKED")),
        "no reasoning dump tags": "<auditor_logic>" not in review,
        "hooks offered": bool(re.search(r"/(critic|curmudgeon):", review)),
    }
    if "--refactored" in args:
        c["refactoring manifest"] = "<refactoring_manifest>" in review
        c["state ledger"] = "<workspace_state_ledger>" in review
        c["closure table"] = bool(re.search(r"closure table", review, re.I))
    return c, stated, actual, verdict

AREAS = [("accessibility", r"\ba11y\b|wcag|\bfocus|keyboard|contrast|\blabel|aria|screen.?reader|accessib|\bzoom\b|target size"),
         ("security", r"\bxss\b|inject|secret|api.?key|\bauth|csrf|\beval\b|sanitiz|unsafe|password|\btoken|permission|idempot"),
         ("data and state", r"\bdata\b|storage|\bstate\b|\brace\b|\blost\b|overwrit|\bsave|corrupt|\bstale\b|\btabs?\b|\bsync|\bids?\b|collid"),
         ("logic and numbers", r"logic|\bmath|revenue|\btotal|\bsum\b|off.by|pagina|calc|\bnan\b|\bnumber|price|\btax\b|discount"),
         ("errors", r"\berror|\bfail|\bcatch\b|exception|\bstatus\b|timeout|retry|\bthrow"),
         ("layout and UX", r"layout|scroll|responsive|\bux\b|hover|\bempty\b|toast|\bcopy\b|wording|confirm|\bstyle|design|\blook\b|template"),
         ("docs and claims", r"readme|\bclaim|\bdocs?\b|comment")]
def area_of(text):
    for name, rx in AREAS:
        if re.search(rx, text, re.I): return name
    return "other"

def score_one(path, suite):
    keyf = HERE / ("answer_key.json" if suite == "1" else f"answer_key{suite}.json")
    if not keyf.exists(): print(f"score.py: no answer key for suite {suite}"); sys.exit(2)
    key = json.loads(keyf.read_text()); review, rows, blocks = load(path)
    hits, used = match_key(key, blocks)
    decoys = json.loads((HERE / f"decoys{suite}.json").read_text()) if (HERE / f"decoys{suite}.json").exists() else {}
    decoy_hits, decoy_detail = [], []
    for name, d in decoys.items():
        for bi, b in enumerate(blocks):
            if bi in used: continue
            if (not d["file"] or d["file"].lower() in b.lower()) and any(re.search(p, b, re.I) for p in d["any"]) and re.search(d["categories"], b, re.I):
                decoy_hits.append(name); used.add(bi)
                decoy_detail.append((name, (rows[bi].get("id"), rows[bi].get("impact"), rows[bi].get("title")) if rows else (None, None, b[:80]))); break
    unmatched = [b for bi, b in enumerate(blocks) if bi not in used and re.search(r"\b(Critical|High|Medium|Low)\b|IMPACT", b) and len(b) > 40] if not rows else [b for bi, b in enumerate(blocks) if bi not in used]
    lab = {"real": 0, "hallucinated": 0, "nitpick": 0, "unlabelled": 0}
    for b in unmatched: lab[labels.get(lab_key(b), "unlabelled")] += 1
    tp = len(hits) + lab["real"]; fp = lab["hallucinated"] + lab["nitpick"] + len(decoy_hits)
    precision = tp / (tp + fp) if tp + fp else 1.0
    # precision by kind of finding, so a noisy area shows up even when the total looks fine
    by = {}
    hit_idx = set(hits.values()); decoy_idx = {bi for bi in used if bi not in hit_idx}
    for bi, b in enumerate(blocks):
        # the finding's own category and title decide its kind; the full text is only a fallback
        # the finding's own category decides; the title only when the category names no area; the whole block last
        kind = area_of(str(rows[bi].get("category", ""))) if rows else "other"
        if kind == "other" and rows: kind = area_of(str(rows[bi].get("title", "")))
        if kind == "other": kind = area_of(b)
        if bi in hit_idx: by.setdefault(kind, [0, 0])[0] += 1
        elif bi in decoy_idx: by.setdefault(kind, [0, 0])[1] += 1
        else:
            l_ = labels.get(lab_key(b))
            if l_ == "real": by.setdefault(kind, [0, 0])[0] += 1
            elif l_ in ("hallucinated", "nitpick"): by.setdefault(kind, [0, 0])[1] += 1
    c, stated, actual, verdict = contract(review, rows)
    ids = {r.get("id") for r in rows} if rows else set()
    return dict(path=path, key=key, hits=hits, by_area=by, decoy_hits=decoy_hits, decoy_detail=decoy_detail, unmatched=unmatched, labels=lab, precision=precision,
                recall=len(hits) / len(key), contract=c, stated=stated, actual=actual, ids=ids, verdict=verdict)

if "--refutations" in args:
    # the verifier's drops, judged: a refutation labelled "real" means the verifier talked the review out of a real bug
    rp = pathlib.Path(opt("--refutations")); RL = HERE / "refutation_labels.json"
    rl = json.loads(RL.read_text()) if RL.exists() else {}
    rows_ = [json.loads(x) for x in rp.read_text().splitlines() if x.strip()] if rp.exists() else []
    for r_ in rows_: rl.setdefault(f"{r_.get('id')}|{r_.get('kind')}", "unlabelled")
    RL.write_text(json.dumps(rl, indent=1))
    judged = [v for v in rl.values() if v in ("real", "correct")]
    wrong = sum(1 for v in judged if v == "real")
    print(f"{len(rows_)} refutation(s)/downgrade(s) in {rp.name}; labels in {RL.name} (set each to real = the verifier dropped a real bug, or correct)")
    print(f"verifier wrongly dropped {wrong} of {len(judged)} judged" + (f" ({wrong / len(judged):.0%})" if judged else ""))
    sys.exit(0)

if "--label" in args:
    pend = json.loads((HERE / ".last-unmatched.json").read_text()) if (HERE / ".last-unmatched.json").exists() else []
    for b in pend: labels.setdefault(lab_key(b), "unlabelled")
    LABELS.write_text(json.dumps(labels, indent=1)); print(f"{len(pend)} unmatched finding(s) written to {LABELS.name}: set each to real, hallucinated or nitpick"); sys.exit(0)

if "--clean" in args:
    review, rows, blocks = load(reviews[0])
    imps = [r.get("impact") for r in rows] if rows else re.findall(r"IMPACT:\s*\**\s*(Critical|High|Medium|Low)", review)
    fa = sum(1 for x in imps if x in ("Critical", "High", "Medium"))
    block = bool(re.search(r"\bBLOCK\b", (re.search(r"VERDICT(.*)", review, re.S) or [None, ""])[1][:400]))
    print(f"Clean twin {opt('--clean')}: {fa} Critical/High/Medium finding(s) (each is a false alarm unless it's a real unplanted bug), {imps.count('Low')} Low; verdict BLOCK: {block}")
    for r in rows:
        if r.get("impact") in ("Critical", "High", "Medium"): print(f"  - {r.get('impact')}: {r.get('file')}:{r.get('line')} {r.get('title')}")
    blocks_ = [" ".join(str(r.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation")) for r in rows if r.get("impact") in ("Critical", "High", "Medium")]
    labs_ = [labels.get(lab_key(b), "unlabelled") for b in blocks_]
    if blocks_: print(f"  labelled: real (unplanted bugs) {labs_.count('real')}, nitpick {labs_.count('nitpick')}, hallucinated {labs_.count('hallucinated')}, unlabelled {labs_.count('unlabelled')}")
    now = {"fp_clean": fa - labs_.count("real"), "false_block": int(block)}
    suite_key = f"clean{opt('--clean')}"
else:
    suite = opt("--suite", "1"); res = [score_one(r, suite) for r in reviews]; r0 = res[0]
    print(f"Recall: {len(r0['hits'])}/{len(r0['key'])} planted defects found ({round(100 * r0['recall'])}%)")
    for m in r0["key"]:
        if m not in r0["hits"]: print("  missed:", m)
    if r0["decoy_hits"] or (HERE / f"decoys{suite}.json").exists():
        blocking = [d for d in r0["decoy_detail"] if d[1][1] in ("Critical", "High", "Medium")]
        print(f"Decoys reported as defects: {len(r0['decoy_hits'])} ({len(blocking)} at Medium or above, {len(r0['decoy_hits']) - len(blocking)} Low)")
        for name, (fid, imp, title) in r0["decoy_detail"]: print(f"  decoy hit: {name}\n      by {fid or '?'} [{imp or '?'}] {title}")
    lb = r0["labels"]
    print(f"Precision: {r0['precision']:.2f}  (unmatched findings: {len(r0['unmatched'])} — real {lb['real']}, hallucinated {lb['hallucinated']}, nitpick {lb['nitpick']}, unlabelled {lb['unlabelled']})")
    (HERE / ".last-unmatched.json").write_text(json.dumps(r0["unmatched"]))
    if r0["by_area"]:
        print("Precision by kind of finding (true / judged):")
        for k_, (t_, f_) in sorted(r0["by_area"].items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
            print(f"  {k_:<18} {t_}/{t_ + f_}" + (f"  ({t_ / (t_ + f_):.0%})" if t_ + f_ else ""))
    for k, v in r0["contract"].items(): print(f"  {'✓' if v else '✗'} {k}")
    if not r0["contract"]["verdict counts match the findings"]: print(f"    stated {r0['stated'] or 'nothing'}; counted {r0['actual']}")
    now = {"recall": r0["recall"], "precision": r0["precision"], "contract": sum(r0["contract"].values()) / len(r0["contract"])}
    if suite == "3":
        nd = max(1, len(json.loads((HERE / "decoys3.json").read_text())))
        now["decoy_rate"] = len(r0["decoy_hits"]) / nd
        now["decoy_block_rate"] = sum(1 for d in r0["decoy_detail"] if d[1][1] in ("Critical", "High", "Medium")) / nd
    if len(res) > 1:
        rec = [x["recall"] for x in res]
        always = [m for m in r0["key"] if all(m in x["hits"] for x in res)]
        jac = []
        for i in range(len(res)):
            for j in range(i + 1, len(res)):
                a, b = res[i]["ids"], res[j]["ids"]
                if a or b: jac.append(len(a & b) / max(1, len(a | b)))
        print(f"Repeats ({len(res)} runs): recall {min(rec):.2f}–{max(rec):.2f} (mean {statistics.mean(rec):.2f}); found in every run: {len(always)}/{len(r0['key'])}; finding-id overlap between runs: {statistics.mean(jac):.2f}" if jac else
              f"Repeats ({len(res)} runs): recall {min(rec):.2f}–{max(rec):.2f}; found in every run: {len(always)}/{len(r0['key'])}")
        now["pass_k"] = len(always) / len(r0["key"])
    if "--refactored" in args:
        d = opt("--refactored")
        if not d or not pathlib.Path(d).is_dir(): print("score.py: --refactored needs a folder"); sys.exit(2)
        if suite in ("1", "2"):
            sys.path.insert(0, str(HERE)); mod = __import__(f"behaviour{suite}")
            rb = mod.run(pathlib.Path(d)); now["behaviour"] = sum(rb.values()) / len(rb)
            print(f"Refactor behaviour: {sum(rb.values())}/{len(rb)} pass")
            for k, v in rb.items(): print(f"  {'✓' if v else '✗'} {k}")
    suite_key = f"suite{suite}"

bf = pathlib.Path(opt("--baseline", HERE / "baseline.json")); base = json.loads(bf.read_text()) if bf.exists() else {}
if "--set-baseline" in args:
    base[suite_key] = now; bf.write_text(json.dumps(base, indent=1)); print(f"baseline for {suite_key} set: {now}"); sys.exit(0)
b = base.get(suite_key, {})
lower_is_better = {"fp_clean", "false_block", "decoy_rate", "decoy_block_rate"}
drops = [k for k, v in now.items() if k in b and ((v > b[k] + 1e-9) if k in lower_is_better else (v + 1e-9 < b[k]))]
if drops: print("BELOW BASELINE: " + ", ".join(f"{k} {now[k]:.2f} vs {b[k]:.2f}" for k in drops)); sys.exit(1)
print("at or above baseline" if b else "no baseline recorded yet (run with --set-baseline once the result is accepted)")
