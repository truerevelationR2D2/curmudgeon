#!/usr/bin/env python3
"""Score Critic reviews against a planted-flaw fixture. Measures what it catches AND how often it's wrong.

usage:
  score.py REVIEW.md [REVIEW2.md ...] --suite 1|2|3 [--refactored DIR] [--baseline FILE] [--set-baseline]
  score.py REVIEW.md --clean 1|2           a review of a clean twin: every Critical/High/Medium finding is a false alarm
  score.py --label                         list unmatched findings from the last scoring for labelling (writes fp_labels.json stubs)
  score.py --refutations .critic/refutations.jsonl   label the verifier's drops (refutation_labels.json) and report how often
                                           it dropped a real bug
  score.py R1.md R2.md R3.md --suite N --gate [--model ID]   the accept/kill gate on repeat runs: PASS, FAIL or NOT MEASURED
  score.py --selftest                      break the gate on purpose: a verifier that refutes everything must FAIL it

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
  intervals       every rate is shown with its 95% Wilson interval and its counts, for example "96% (82-99%, 27 of 28)"
  impact          a planted Critical or High defect that ends below Medium is an impact miss
  stamp           plugin version, git SHA, model, a sha256 of the prompt files and the labeller, on every result

Without --gate, a single run is compared point by point with the baseline (indicative only: one run is noisy).
With --gate (at least 2 runs): FAIL when precision, recall or impact misses are worse than the baseline's 95% interval
in most runs, when any run flags more decoys at Medium or above than the baseline (strict floor), when any clean-twin
run says BLOCK (strict floor), or when tokens rise more than 10% with no metric better; NOT MEASURED with fewer than 2
runs, an answer-key leak, or a baseline without counts for a metric. Exit 0 PASS, 1 FAIL, 2 bad usage, 3 NOT MEASURED."""
import hashlib, json, math, pathlib, re, statistics, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name, default=None): return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
FLAGS_WITH_VALUE = {"--suite", "--refactored", "--baseline", "--clean", "--refutations", "--model", "--labeller"}
reviews = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in FLAGS_WITH_VALUE)]
if not reviews and "--label" not in args and "--refutations" not in args and "--selftest" not in args: print(__doc__); sys.exit(2)
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

def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes in n trials."""
    if not n: return (0.0, 1.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))
def rate(k, n): lo, hi = wilson(k, n); return f"{k / n:.0%} ({lo:.0%}-{hi:.0%}, {k} of {n})" if n else "not measured (0 judged)"

PLUGIN = HERE.parent / "plugin"
def stamp():
    """What produced this result: plugin version, git SHA (dirty or clean), model, prompt files' hash, labeller."""
    try: version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text()).get("version")
    except Exception: version = None
    def git(*a):
        try: return subprocess.run(["git", *a], cwd=HERE.parent, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired): return ""
    files = sorted(list((PLUGIN / "agents").glob("*.md")) + list((PLUGIN / "skills").glob("*/SKILL.md")) + list((PLUGIN / "skills" / "review" / "references").glob("*.md")))
    h = hashlib.sha256()
    for f in files: h.update(f.relative_to(PLUGIN).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return {"version": version, "sha": git("rev-parse", "--short=12", "HEAD") or None, "dirty": bool(git("status", "--porcelain", "--", "plugin")),
            "model": opt("--model", "unrecorded"), "prompts_sha256": h.hexdigest()[:16], "labeller": opt("--labeller", labels.get("_labeller", "unrecorded"))}

LEAK_FILES = re.compile(r"^(answer_key\d*\.json|decoys\d*\.json|fp_labels\.json|labels-.*\.json|refutation_labels\.json|score\.py|baseline\.json)$")
def leak(path):
    """Signs the reviewed copy could see the answers: eval files inside the run folder, or answer-key ids in the review."""
    p = pathlib.Path(path).resolve(); run_dir = p.parent.parent if p.parent.name == ".critic" else p.parent
    found = [str(x.relative_to(run_dir)) for x in run_dir.rglob("*") if x.is_file() and LEAK_FILES.match(x.name) and ".git" not in x.parts][:5]
    text = p.read_text(encoding="utf-8", errors="replace")
    if re.search(r"answer[_ ]key|\b[DE]\d{2}\b.*planted|planted (defect|flaw)s? list", text, re.I): found.append("the review names the answer key")
    return found

def run_tokens(path):
    """Tokens the run's agents used, from the run's .critic/cost.jsonl (None when not recorded)."""
    p = pathlib.Path(path).resolve(); cf = (p.parent if p.parent.name == ".critic" else p.parent / ".critic") / "cost.jsonl"
    if not cf.is_file(): return None
    tot = 0
    for line in cf.read_text().splitlines():
        try: r = json.loads(line)
        except ValueError: continue
        tot += sum(r.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    return tot

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
    impact_misses = []  # a planted Critical or High that the review rated below Medium
    for name, bi in hits.items():
        want = key[name].get("impact")
        if want not in ("Critical", "High"): continue
        got = rows[bi].get("impact") if rows else (re.search(r"\b(Critical|High|Medium|Low)\b", blocks[bi]) or [None, None])[1]
        if got not in ("Critical", "High", "Medium"): impact_misses.append((name, want, got))
    blocking = sum(1 for d in decoy_detail if d[1][1] in ("Critical", "High", "Medium"))
    return dict(path=path, key=key, hits=hits, by_area=by, decoy_hits=decoy_hits, decoy_detail=decoy_detail, unmatched=unmatched, labels=lab, precision=precision,
                recall=len(hits) / len(key), contract=c, stated=stated, actual=actual, ids=ids, verdict=verdict, tp=tp, fp=fp,
                impact_misses=impact_misses, decoy_blocking=blocking)

if "--selftest" in args:
    # Break the gate on purpose (SC-71): runs where a verifier refuted every real bug must FAIL; runs equal to the
    # baseline must PASS; one run must be NOT MEASURED; a decoy flagged at Medium must FAIL at once. No model needed.
    import tempfile
    key = json.loads((HERE / "answer_key.json").read_text())
    def text_for(name, k):
        for cand in [name] + [re.sub(r"\\(.)", r"\1", x) for x in k["any"]]:
            if any(re.search(x, f"{k['file']} {cand}", re.I) for x in k["any"]): return cand
        return name
    def make(dirp, rows):
        dirp.mkdir(parents=True); (dirp / "last-review.md").write_text("# review\n## VERDICT\n**CONCERNS**\n")
        (dirp / "findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return str(dirp / "last-review.md")
    good = [{"id": f"F-{i}", "file": k["file"] or "app.js", "line": 1, "category": "x", "impact": k.get("impact", "Medium"), "title": text_for(n, k)} for i, (n, k) in enumerate(key.items())]
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t); bl = t / "baseline.json"
        g = [make(t / f"good{i}", good) for i in range(3)]
        bad = [make(t / f"refuted{i}", []) for i in range(3)]
        low = [make(t / f"low{i}", [dict(r, impact="Low") if r.get("impact") in ("Critical", "High") else r for r in good]) for i in range(3)]
        def go(*a): return subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), *a, "--suite", "1", "--baseline", str(bl)], capture_output=True, text=True).returncode
        checks = [("baseline recorded", go(*g, "--set-baseline") == 0), ("equal runs PASS", go(*g, "--gate") == 0),
                  ("a verifier that refutes everything FAILS", go(*bad, "--gate") == 1), ("impact misses FAIL", go(*low, "--gate") == 1),
                  ("one run is NOT MEASURED", go(g[0], "--gate") == 3)]
    for name, ok in checks: print(f"  {'✓' if ok else '✗'} {name}")
    sys.exit(0 if all(ok for _, ok in checks) else 1)

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
    print(f"Recall: {rate(len(r0['hits']), len(r0['key']))} planted defects found")
    for m in r0["key"]:
        if m not in r0["hits"]: print("  missed:", m)
    if r0["decoy_hits"] or (HERE / f"decoys{suite}.json").exists():
        blocking = [d for d in r0["decoy_detail"] if d[1][1] in ("Critical", "High", "Medium")]
        print(f"Decoys reported as defects: {len(r0['decoy_hits'])} ({len(blocking)} at Medium or above, {len(r0['decoy_hits']) - len(blocking)} Low)")
        for name, (fid, imp, title) in r0["decoy_detail"]: print(f"  decoy hit: {name}\n      by {fid or '?'} [{imp or '?'}] {title}")
    lb = r0["labels"]
    for name, want, got in r0["impact_misses"]: print(f"  impact miss: {name[:70]} was planted {want}, rated {got or 'unrated'}")
    print(f"Precision: {rate(r0['tp'], r0['tp'] + r0['fp'])}  (unmatched findings: {len(r0['unmatched'])} — real {lb['real']}, hallucinated {lb['hallucinated']}, nitpick {lb['nitpick']}, unlabelled {lb['unlabelled']})")
    (HERE / ".last-unmatched.json").write_text(json.dumps(r0["unmatched"]))
    if r0["by_area"]:
        print("Precision by kind of finding (true / judged):")
        for k_, (t_, f_) in sorted(r0["by_area"].items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
            print(f"  {k_:<18} {t_}/{t_ + f_}" + (f"  ({t_ / (t_ + f_):.0%})" if t_ + f_ else ""))
    for k, v in r0["contract"].items(): print(f"  {'✓' if v else '✗'} {k}")
    if not r0["contract"]["verdict counts match the findings"]: print(f"    stated {r0['stated'] or 'nothing'}; counted {r0['actual']}")
    now = {"recall": r0["recall"], "precision": r0["precision"], "contract": sum(r0["contract"].values()) / len(r0["contract"]),
           "recall_k": len(r0["hits"]), "recall_n": len(r0["key"]), "precision_k": r0["tp"], "precision_n": r0["tp"] + r0["fp"],
           "impact_misses": len(r0["impact_misses"]), "decoy_blocking": r0["decoy_blocking"]}
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
st = stamp(); print("Stamp: " + ", ".join(f"{k} {v}" for k, v in st.items()))
leaks = {r: leak(r) for r in reviews}; leaks = {r: v for r, v in leaks.items() if v}
for r, v in leaks.items(): print(f"ANSWER-KEY LEAK in {r}: {', '.join(v)}")
toks = [run_tokens(r) for r in reviews]
if any(t is not None for t in toks): print("Tokens per run: " + ", ".join("unrecorded" if t is None else f"{t:,}" for t in toks))
if "--set-baseline" in args:
    if leaks: print("refusing to set a baseline from a run that could see the answers"); sys.exit(3)
    entry = dict(now, stamp=st)
    if "--clean" not in args and len(res) > 1: entry["runs"] = [{"precision_k": x["tp"], "precision_n": x["tp"] + x["fp"], "recall_k": len(x["hits"]), "recall_n": len(x["key"]),
                                                               "impact_misses": len(x["impact_misses"]), "decoy_blocking": x["decoy_blocking"]} for x in res]
    if any(t is not None for t in toks): entry["tokens"] = statistics.median([t for t in toks if t is not None])
    base[suite_key] = entry; bf.write_text(json.dumps(base, indent=1)); print(f"baseline for {suite_key} set: {now}"); sys.exit(0)
b = base.get(suite_key, {})
if "--gate" in args:
    def verdict_(v, why): print(f"GATE: {v}" + ("".join(f"\n  - {w}" for w in why) if why else "")); sys.exit({"PASS": 0, "FAIL": 1, "NOT MEASURED": 3}[v])
    if leaks: verdict_("NOT MEASURED", ["a run could see the answer key"])
    if len(reviews) < 2: verdict_("NOT MEASURED", ["the gate needs at least 2 runs (3 recommended)"])
    if not b: verdict_("NOT MEASURED", [f"no baseline for {suite_key}"])
    why, missing = [], []
    if "--clean" in args:
        runs = []
        for r in reviews:
            rv, rws, _ = load(r); imps = [x.get("impact") for x in rws] if rws else re.findall(r"IMPACT:\s*\**\s*(Critical|High|Medium|Low)", rv)
            runs.append({"fp": sum(1 for x in imps if x in ("Critical", "High", "Medium")), "block": bool(re.search(r"\bBLOCK\b", (re.search(r"VERDICT(.*)", rv, re.S) or [None, ""])[1][:400]))})
        if any(x["block"] for x in runs): why.append("a clean-twin run says BLOCK (strict floor)")
        worse = sum(1 for x in runs if x["fp"] > b.get("fp_clean", 0))
        if worse * 2 > len(runs): why.append(f"more false alarms than the baseline in {worse} of {len(runs)} runs")
    else:
        def lower(metric):
            k, n = b.get(f"{metric}_k"), b.get(f"{metric}_n")
            if k is None or not n: missing.append(metric); return None
            return wilson(k, n)[0]
        for metric in ("precision", "recall"):
            lo = lower(metric)
            if lo is None: continue
            worse = sum(1 for x in res if (x["tp"] / (x["tp"] + x["fp"]) if metric == "precision" and x["tp"] + x["fp"] else (len(x["hits"]) / len(x["key"]) if metric == "recall" else 1.0)) < lo - 1e-9)
            if worse * 2 > len(res): why.append(f"{metric} below the baseline's 95% interval (lower bound {lo:.0%}) in {worse} of {len(res)} runs")
        if "impact_misses" in b:
            worse = sum(1 for x in res if len(x["impact_misses"]) > b["impact_misses"])
            if worse * 2 > len(res): why.append(f"more impact misses than the baseline in {worse} of {len(res)} runs")
        else: missing.append("impact_misses")
        floor = b.get("decoy_blocking")
        if floor is None and "decoy_block_rate" in b and suite == "3": floor = round(b["decoy_block_rate"] * max(1, len(json.loads((HERE / "decoys3.json").read_text()))))
        if floor is not None and any(x["decoy_blocking"] > floor for x in res): why.append(f"a run flags more decoys at Medium or above than the baseline's {floor} (strict floor)")
        if b.get("tokens") and all(t is not None for t in toks):
            better = any(x["tp"] / max(1, x["tp"] + x["fp"]) > b.get("precision", 1) + 1e-9 or x["recall"] > b.get("recall", 1) + 1e-9 for x in res)
            if statistics.median(toks) > 1.10 * b["tokens"] and not better: why.append(f"tokens rose {statistics.median(toks) / b['tokens'] - 1:.0%} with no metric better (cost regression)")
    if why: verdict_("FAIL", why)
    if missing: verdict_("NOT MEASURED", [f"the baseline has no counts for {', '.join(sorted(set(missing)))}: re-record it with --set-baseline from accepted runs"])
    verdict_("PASS", [])
lower_is_better = {"fp_clean", "false_block", "decoy_rate", "decoy_block_rate", "impact_misses", "decoy_blocking"}
drops = [k for k, v in now.items() if k in b and not k.endswith(("_k", "_n")) and isinstance(v, (int, float)) and ((v > b[k] + 1e-9) if k in lower_is_better else (v + 1e-9 < b[k]))]
if drops: print("BELOW BASELINE: " + ", ".join(f"{k} {now[k]:.2f} vs {b[k]:.2f}" for k in drops)); sys.exit(1)
print("at or above baseline" if b else "no baseline recorded yet (run with --set-baseline once the result is accepted)")
