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
  score.py --funnel RUN_DIR --suite N      for each planted defect the run missed, the stage where it was lost
  options: --plugin DIR (the build that ran, for the stamp), --labels FILE, --baseline FILE, --meta-cost (cost from each
           run's meta.json, the eval runner's whole-session total, in place of the plugin's own token log)

Each REVIEW is a teardown (.critic/last-review.md). When a .critic/findings.jsonl sits beside it, the structured
findings are used; otherwise finding blocks are parsed from the markdown.

Reported:
  recall          planted defects found (each matched inside one finding that names the right file and points at one
                  of the plant's places, the answer key's "at"; keymatch.py). A suite whose baseline was recorded before
                  that rule is compared loosely (file and pattern), with the strict figure shown beside it
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
runs, an answer-key leak, or a baseline without counts for a metric. Exit 0 PASS, 1 FAIL, 2 bad usage, 3 NOT MEASURED, 4 the scorer itself crashed."""
import hashlib, json, math, os, pathlib, re, statistics, subprocess, sys, traceback
def _crash(t, v, tb):  # a crash must never look like a gate verdict: FAIL is 1, a crash is 4
    traceback.print_exception(t, v, tb); sys.stderr.flush(); sys.stdout.flush(); os._exit(4)
sys.excepthook = _crash
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import keymatch
args = sys.argv[1:]
def opt(name, default=None): return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default
FLAGS_WITH_VALUE = {"--suite", "--refactored", "--baseline", "--clean", "--refutations", "--model", "--labeller", "--funnel", "--labels", "--plugin"}
reviews = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in FLAGS_WITH_VALUE)]
if not reviews and "--label" not in args and "--refutations" not in args and "--selftest" not in args and "--funnel" not in args: print(__doc__); sys.exit(2)
LABELS = pathlib.Path(opt("--labels", HERE / "fp_labels.json")); labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}

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

def locs_of(rows, blocks):
    """Where each finding points: file:line and its quote for a structured finding (as deathmatch.py builds it), the
    block's own text otherwise."""
    return [f"{r.get('file', '')}:{r.get('line')} {r.get('quote', '')} " + " ".join(str(x) for x in (r.get("locations") or []) if isinstance(x, str)) for r in rows] if rows else list(blocks)  # never the evidence (it can name other files); a merged finding's own cited places, yes

def strict_mode(suite_key):
    """Decision 28: a finding credits a plant only when it points at one of the plant's places. A baseline recorded
    before that (no "scoring": "strict") is compared the way it was scored, loosely, with the strict figure shown
    beside it; --set-baseline always records strictly."""
    if "--set-baseline" in args: return True
    bfp = pathlib.Path(opt("--baseline", HERE / "baseline.json"))
    try: b_ = json.loads(bfp.read_text()).get(suite_key) if bfp.exists() else None
    except ValueError: b_ = None
    return not b_ or b_.get("scoring") == "strict"

def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes in n trials."""
    if not n: return (0.0, 1.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))
def rate(k, n): lo, hi = wilson(k, n); return f"{k / n:.0%} ({lo:.0%}-{hi:.0%}, {k} of {n})" if n else "not measured (0 judged)"

PLUGIN = pathlib.Path(opt("--plugin", HERE.parent / "plugin"))  # --plugin: the build that ran (an A/B arm), so the stamp names it, not this checkout
def stamp():
    """What produced this result: plugin version, git SHA (dirty or clean), model, prompt files' hash, labeller."""
    try: version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text()).get("version")
    except Exception: version = None
    def git(*a):
        try: return subprocess.run(["git", *a], cwd=PLUGIN.parent, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired): return ""
    files = sorted(list((PLUGIN / "agents").glob("*.md")) + list((PLUGIN / "skills").glob("*/SKILL.md")) + list((PLUGIN / "skills" / "review" / "references").glob("*.md")))
    h = hashlib.sha256()
    for f in files: h.update(f.relative_to(PLUGIN).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return {"version": version, "sha": git("rev-parse", "--short=12", "HEAD") or None, "dirty": bool(git("status", "--porcelain", "--", "plugin")),
            "model": opt("--model", "unrecorded"), "prompts_sha256": h.hexdigest()[:16], "labeller": opt("--labeller", labels.get("_labeller", "unrecorded"))}

LEAK_FILES = re.compile(r"^(answer_key\d*\.json|decoys\d*\.json|fp_labels\.json|labels-.*\.json|refutation_labels\.json|score\.py|baseline\.json)$")
def leak(path, key=None):
    """Signs the reviewed copy could see the answers: eval files inside the run folder, answer-key ids, or an answer-key
    entry's wording copied into the review."""
    p = pathlib.Path(path).resolve(); run_dir = p.parent.parent if p.parent.name == ".critic" else p.parent
    found = [str(x.relative_to(run_dir)) for x in run_dir.rglob("*") if x.is_file() and LEAK_FILES.match(x.name) and ".git" not in x.parts][:5]
    text = p.read_text(encoding="utf-8", errors="replace")
    if re.search(r"answer[_ ]key|\b[DEGR]\d{1,2}\b.*planted|planted (defect|flaw)s? list", text, re.I): found.append("the review names the answer key")
    low = re.sub(r"\s+", " ", text.lower())
    for name in (key or {}):
        words = re.sub(r"\s+", " ", name.split(" ", 1)[-1].lower())[:48]
        if len(words) >= 30 and words in low: found.append(f"the review copies an answer-key entry ({name.split()[0]})"); break
    return found

def run_tokens(path):
    """Tokens the run's agents used, from the run's .critic/cost.jsonl (None when not recorded). With --meta-cost, the
    whole session's cost from the eval runner's meta.json instead, in millionths of a dollar: the same source for both
    arms of an A/B, lead and subagents together, whatever each version's own cost hook records."""
    p = pathlib.Path(path).resolve()
    if "--meta-cost" in args:
        run_dir = p.parent.parent if p.parent.name == ".critic" else p.parent
        try: c = json.loads((run_dir / "meta.json").read_text()).get("cost_usd")
        except (OSError, ValueError): return None
        return round(c * 1e6) if isinstance(c, (int, float)) else None
    cf = (p.parent if p.parent.name == ".critic" else p.parent / ".critic") / "cost.jsonl"
    if not cf.is_file(): return None
    rows = []
    for line in cf.read_text().splitlines():
        try: rows.append(json.loads(line))
        except ValueError: continue
    if not rows: return None
    last = max((r.get("run") or 0) for r in rows)  # the latest run only, as critic_ledger.py tokens does
    return sum(sum(r.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")) for r in rows if (r.get("run") or 0) == last)

def verdict_word(review):
    """The one verdict word (BLOCK, CONCERNS or CLEAN) the teardown gives, or None. Bold first, then a line that starts
    with the word; a sentence that merely mentions BLOCK is not a verdict."""
    sec = (re.search(r"VERDICT(.*)", review, re.S) or [None, ""])[1][:600]
    m = re.search(r"\*\*(BLOCK|CONCERNS|CLEAN)\*\*", sec) or re.search(r"(?m)^\W*(BLOCK|CONCERNS|CLEAN)\b", sec)
    return m.group(1) if m else None

def clean_counts(path):
    """A clean-twin run: Critical/High/Medium findings that are false alarms (minus those labelled real, as the
    baseline does), the unlabelled ones, and whether the verdict is BLOCK."""
    review, rows, _ = load(path)
    if rows: chm = [r for r in rows if r.get("impact") in ("Critical", "High", "Medium")]; blocks_ = [" ".join(str(r.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation")) for r in chm]
    else: blocks_ = [m.group(0) for m in re.finditer(r"IMPACT:\s*\**\s*(Critical|High|Medium)[^\n]*", review)]
    labs_ = [labels.get(lab_key(b), "unlabelled") for b in blocks_]
    return {"fp": len(blocks_) - labs_.count("real"), "unlabelled": labs_.count("unlabelled"), "block": verdict_word(review) == "BLOCK",
            "labs": labs_, "chm": len(blocks_), "low": (sum(1 for r in rows if r.get("impact") == "Low") if rows else len(re.findall(r"IMPACT:\s*\**\s*Low", review)))}

IMPACT_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

def match_key(key, blocks, locs=None, impacts=None):
    """locs given: strict (the finding must point at one of the plant's places, keymatch.py). impacts given: a plant's
    candidates are tried highest impact first, so the finding credited is the one that rated it most seriously."""
    rank = lambda bi: IMPACT_RANK.get((impacts or {}).get(bi) if impacts else None, 4)
    eligible = {name: sorted([bi for bi, b in enumerate(blocks) if (locs is None or keymatch.points_at(k, locs[bi]))
                       and (not k["file"] or k["file"].lower() in (b + " " + (locs[bi] if locs else "")).lower()) and any(re.search(p, b, re.I) for p in k["any"])], key=lambda bi: (rank(bi), bi)) for name, k in key.items()}
    serious = {name: [bi for bi in c if rank(bi) <= 2] for name, c in eligible.items() if impacts and key[name].get("impact") in ("Critical", "High")}
    hits = keymatch.serious_first(eligible, serious) if serious else keymatch.max_match(eligible)  # one finding per plant, as many plants as possible
    return dict(sorted(hits.items(), key=lambda kv: list(key).index(kv[0]))), set(hits.values())

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
        "all contract headers": all((any(section(x) is not None for x in h) if isinstance(h, tuple) else section(h) is not None) for h in ["INTENT GATE", "RISK MAP", "SANDBOX LEDGER", ("CODE AND ARCHITECTURE", "CRITICAL CODE ARCHITECTURE DEFECTS"), "UI/UX", "ANTI-AI", "CLAIMS, NUMBERS", "VERDICT"]),
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
    locs = locs_of(rows, blocks); strict = strict_mode(f"suite{suite}")
    imp = {i: r.get("impact") for i, r in enumerate(rows)} if rows else None
    strict_hits, _ = match_key(key, blocks, locs, imp); loose_hits, _ = match_key(key, blocks, None, imp)
    hits, used = match_key(key, blocks, locs if strict else None, imp)
    decoys = json.loads((HERE / f"decoys{suite}.json").read_text()) if (HERE / f"decoys{suite}.json").exists() else {}
    decoy_hits, decoy_detail = [], []
    for name, d in decoys.items():
        for bi, b in enumerate(blocks):
            if bi in used: continue
            if (not d["file"] or d["file"].lower() in b.lower()) and any(re.search(p, b, re.I) for p in d["any"]) and re.search(d["categories"], b, re.I):
                decoy_hits.append(name); used.add(bi)
                decoy_detail.append((name, (rows[bi].get("id"), rows[bi].get("impact"), rows[bi].get("title")) if rows else (None, (re.search(r"\b(Critical|High|Medium|Low)\b", b) or [None, None])[1], b[:80]))); break
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
                impact_misses=impact_misses, decoy_blocking=blocking, strict=strict, strict_hits=strict_hits, loose_hits=loose_hits)

if "--funnel" in args:
    # Where each missed plant was lost (SC-15; idea from Kodus and Sashiko, rebuilt here): never raised, set aside by a
    # reviewer, failed the contract, retracted by the quote check, suppressed by a memory, dropped on votes, refuted or
    # downgraded by a verifier. Reads the run's own .critic/ files; nothing is re-run.
    run_dir = pathlib.Path(opt("--funnel")); C = run_dir / ".critic"; suite = opt("--suite", "1")
    key = json.loads((HERE / ("answer_key.json" if suite == "1" else f"answer_key{suite}.json")).read_text())
    def blk(f): return " ".join(str(f.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation"))
    def jl(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() else []
    def hit(k, rows): return [r for r in rows if keymatch.points_at(k, f"{r.get('file', '')}:{r.get('line')} {r.get('quote', '')}") and (not k["file"] or k["file"].lower() in blk(r).lower()) and any(re.search(x, blk(r), re.I) for x in k["any"])]
    final = jl(C / "findings.jsonl")
    tally = json.loads((C / "tally.json").read_text()) if (C / "tally.json").is_file() else {}
    raised, aside = [], []
    try: cur = json.loads((C / "ledger.json").read_text()).get("run")
    except Exception: cur = None
    for rv in sorted((C / "reviews").glob("review-*.json")):  # this run's reviews only; earlier runs live in history/
        try: data = json.loads(rv.read_text())
        except ValueError: continue
        items = data if isinstance(data, list) else data.get("findings", []) if isinstance(data, dict) else []
        raised += [x for x in items if isinstance(x, dict)]
        if isinstance(data, dict): aside += [x for x in data.get("set_aside", []) if isinstance(x, dict)]
    refs = [r for r in jl(C / "refutations.jsonl") if cur is None or r.get("run") in (None, cur)]  # this run's verdicts only
    stages = [("retracted by the quote check", [x["finding"] for x in tally.get("retracted", [])]),
              ("failed the finding contract", [x["finding"] for x in tally.get("rejected", [])]),
              ("suppressed by an owner's false-positive ruling", [x["finding"] for x in tally.get("suppressed", [])]),
              ("dropped on votes", [x["finding"] for x in tally.get("dropped", [])]),
              ("refuted by a verifier", [r.get("finding", r) for r in refs if r.get("kind") == "refuted"]),
              ("downgraded by a verifier", [r.get("finding", r) for r in refs if r.get("kind") == "downgraded"])]
    lost = {}
    reached = keymatch.max_match({name: [i for i, r in enumerate(final) if hit(k, [r])] for name, k in key.items()})  # one finding reaches one plant, as score.py counts recall
    for name, k in key.items():
        if name in reached: continue
        where = next((st for st, rows in stages if hit(k, rows)), None)
        if not where: where = "set aside by a reviewer" if hit(k, aside) else ("raised, then lost at an unrecorded step" if hit(k, raised) else "never raised")
        lost[name] = where
    print(f"Funnel for {run_dir}: {len(key) - len(lost)} of {len(key)} planted defects reached the final findings")
    for name, where in lost.items(): print(f"  {where}: {name[:90]}")
    by = {}
    for w in lost.values(): by[w] = by.get(w, 0) + 1
    if by: print("By stage: " + ", ".join(f"{w} {n}" for w, n in sorted(by.items(), key=lambda kv: -kv[1])))
    sys.exit(0)

if "--selftest" in args:
    # Break the gate on purpose (SC-71). Each check names the exact exit code it needs, so a crash (4) is never
    # mistaken for a FAIL (1). No model needed.
    import tempfile
    def sample(rx_list):  # a phrase that one of these regexes matches
        for x in rx_list:
            for cand in [re.sub(r"\\(.)", r"\1", x)] + [re.sub(r"\\(.)", r"\1", y) for y in re.split(r"(?<!\\)\|", x.strip("()"))]:
                cand = re.sub(r"[\^\$\(\)\?\*\+\[\]]", "", cand)
                if any(re.search(z, cand, re.I) for z in rx_list): return cand
        return rx_list[0]
    def make(dirp, rows, verdict="**CONCERNS**"):
        dirp.mkdir(parents=True); (dirp / "last-review.md").write_text(f"# review\n## VERDICT\n{verdict}\n")
        (dirp / "findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return str(dirp / "last-review.md")
    def plants(suite):
        key = json.loads((HERE / ("answer_key.json" if suite == "1" else f"answer_key{suite}.json")).read_text())
        return [{"id": f"F-{i}", "file": (k.get("at") or [[k["file"] or "app.js"]])[0][0] if not k["file"] else k["file"], "line": (k.get("at") or [[None, i + 1]])[0][1], "category": "x", "impact": k.get("impact", "Medium"), "title": sample(k["any"])} for i, (n, k) in enumerate(key.items())]
    checks = []
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t); bl = t / "baseline.json"; lab = t / "labels.json"
        def go(*a, suite="1", env=None):
            return subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), *a, "--suite", suite, "--baseline", str(bl), "--labels", str(lab)],
                                  capture_output=True, text=True, env=dict(os.environ, **(env or {}))).returncode
        def label(rows, value):
            cur = json.loads(lab.read_text()) if lab.exists() else {}
            for r in rows: cur[lab_key(" ".join(str(r.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation")))] = value
            lab.write_text(json.dumps(cur))
        good = plants("1")
        g = [make(t / f"good{i}", good) for i in range(3)]
        checks.append(("baseline recorded", go(*g, "--set-baseline") == 0))
        checks.append(("equal runs PASS", go(*g, "--gate") == 0))
        checks.append(("a verifier that refutes everything FAILS", go(*[make(t / f"refuted{i}", []) for i in range(3)], "--gate") == 1))
        checks.append(("losing 2 of 16 plants in every run FAILS", go(*[make(t / f"lost{i}", good[2:]) for i in range(3)], "--gate") == 1))
        checks.append(("impact misses FAIL", go(*[make(t / f"low{i}", [dict(r, impact="Low") if r["impact"] in ("Critical", "High") else r for r in good]) for i in range(3)], "--gate") == 1))
        bogus = [{"id": f"X-{j}", "file": "app.js", "line": 900 + j, "category": "made-up", "impact": "High", "title": f"invented problem number {j}"} for j in range(20)]
        noisy = [make(t / f"noisy{i}", good + bogus) for i in range(3)]
        checks.append(("unlabelled extra findings are NOT MEASURED, never PASS", go(*noisy, "--gate") == 3))
        label(bogus, "hallucinated")
        checks.append(("labelled false alarms FAIL on precision", go(*noisy, "--gate") == 1))
        checks.append(("one run is NOT MEASURED", go(g[0], "--gate") == 3))
        checks.append(("a crash exits 4, never 1", go(*g, "--gate", env={"CRITIC_SELFTEST_CRASH": "1"}) == 4))
        d3 = json.loads((HERE / "decoys3.json").read_text()); dn, dk = next(iter(d3.items()))
        p3 = plants("3"); b3 = [make(t / f"s3good{i}", p3) for i in range(3)]
        go(*b3, "--set-baseline", suite="3")
        decoy = {"id": "D-1", "file": dk["file"] or "app.js", "line": 1, "category": sample([dk["categories"]]), "impact": "Medium", "title": sample(dk["any"]) + " " + sample([dk["categories"]])}
        checks.append(("one decoy at Medium FAILS at once (strict floor)", go(*[make(t / f"s3decoy{i}", p3 + ([decoy] if i == 0 else [])) for i in range(3)], "--gate", suite="3") == 1))
        clean = [make(t / f"clean{i}", [], verdict="**CLEAN**: nothing here rises to BLOCK.") for i in range(3)]
        def gc(*a): return subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), *a, "--clean", "1", "--baseline", str(bl), "--labels", str(lab)], capture_output=True, text=True).returncode
        gc(clean[0], "--set-baseline")
        checks.append(("a clean verdict that mentions BLOCK PASSES", gc(*clean, "--gate") == 0))
        checks.append(("a clean twin run that says BLOCK FAILS (strict floor)", gc(*[make(t / f"cblock{i}", [], verdict="**BLOCK**") for i in range(3)], "--gate") == 1))
        realf = [{"id": "R-1", "file": "app.js", "line": 3, "category": "bug", "impact": "Medium", "title": "a real unplanted bug in the clean twin"}]
        rc = [make(t / f"creal{i}", realf, verdict="**CONCERNS**") for i in range(3)]
        label(realf, "real"); gc(rc[0], "--set-baseline")
        checks.append(("a clean-twin finding labelled real does not FAIL an unchanged plugin", gc(*rc, "--gate") == 0))
        leaky = make(t / "leak", good); (t / "leak" / "answer_key.json").write_text("{}")
        checks.append(("an answer-key leak is NOT MEASURED", go(leaky, g[1], "--gate") == 3))
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
    review, rows, blocks = load(reviews[0]); cc = clean_counts(reviews[0])
    print(f"Clean twin {opt('--clean')}: {cc['chm']} Critical/High/Medium finding(s) (each is a false alarm unless it's a real unplanted bug), {cc['low']} Low; verdict BLOCK: {cc['block']}")
    for r in rows:
        if r.get("impact") in ("Critical", "High", "Medium"): print(f"  - {r.get('impact')}: {r.get('file')}:{r.get('line')} {r.get('title')}")
    labs_ = cc["labs"]
    if labs_: print(f"  labelled: real (unplanted bugs) {labs_.count('real')}, nitpick {labs_.count('nitpick')}, hallucinated {labs_.count('hallucinated')}, unlabelled {labs_.count('unlabelled')}")
    now = {"fp_clean": cc["fp"], "false_block": int(cc["block"])}
    suite_key = f"clean{opt('--clean')}"
else:
    suite = opt("--suite", "1"); res = [score_one(r, suite) for r in reviews]; r0 = res[0]
    print(f"Recall: {rate(len(r0['hits']), len(r0['key']))} planted defects found" + ("" if r0["strict"] else " (file and pattern only, as this suite's baseline was scored; re-baseline to switch)"))
    print(f"  pointing at the planted lines: {len(r0['strict_hits'])} of {len(r0['key'])}; file and pattern only: {len(r0['loose_hits'])} of {len(r0['key'])}")
    placeless = [n for n in r0["hits"] if not r0["key"][n].get("at")]
    if placeless: print(f"  {len(placeless)} credit(s) from key entries with no place to point at (matched on file and pattern only): " + ", ".join(n.split()[0] for n in placeless))
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
_key = json.loads((HERE / ("answer_key.json" if suite_key == "suite1" else f"answer_key{suite_key[5:]}.json")).read_text()) if suite_key.startswith("suite") and (HERE / ("answer_key.json" if suite_key == "suite1" else f"answer_key{suite_key[5:]}.json")).exists() else None
leaks = {r: leak(r, _key) for r in reviews}; leaks = {r: v for r, v in leaks.items() if v}
for r, v in leaks.items(): print(f"ANSWER-KEY LEAK in {r}: {', '.join(v)}")
toks = [run_tokens(r) for r in reviews]
if any(t is not None for t in toks):
    print(("Cost per run: " + ", ".join("unrecorded" if t is None else f"${t / 1e6:.2f}" for t in toks)) if "--meta-cost" in args else
          ("Tokens per run: " + ", ".join("unrecorded" if t is None else f"{t:,}" for t in toks)))
if "--set-baseline" in args:
    if leaks: print("refusing to set a baseline from a run that could see the answers"); sys.exit(3)
    entry = dict(now, stamp=st, scoring="strict")
    if "--meta-cost" in args: entry["cost_unit"] = "usd_millionths"
    if "--clean" in args and len(reviews) > 1:  # several clean-twin runs: the median false alarms and any BLOCK, not the first run alone
        cr = [clean_counts(r) for r in reviews]
        entry.update(fp_clean=statistics.median(x["fp"] for x in cr), false_block=int(any(x["block"] for x in cr)), runs=[{"fp": x["fp"], "block": x["block"]} for x in cr])
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
    if os.environ.get("CRITIC_SELFTEST_CRASH") == "1": raise RuntimeError("deliberate crash for --selftest")
    if "--clean" in args:
        runs = [clean_counts(r) for r in reviews]
        if any(x["block"] for x in runs): why.append("a clean-twin run says BLOCK (strict floor)")
        if any(x["unlabelled"] for x in runs): missing.append(f"labels for {sum(x['unlabelled'] for x in runs)} Critical/High/Medium clean-twin finding(s) (score.py --label)")
        worse = sum(1 for x in runs if x["fp"] > b.get("fp_clean", 0))
        if worse * 2 > len(runs): why.append(f"more false alarms than the baseline in {worse} of {len(runs)} runs")
    else:
        def pooled(metric):  # the baseline's counts over all its recorded runs, so the interval reflects every run
            rs = b.get("runs") or []
            if rs and all(f"{metric}_k" in r_ and f"{metric}_n" in r_ for r_ in rs): return sum(r_[f"{metric}_k"] for r_ in rs), sum(r_[f"{metric}_n"] for r_ in rs)
            k, n = b.get(f"{metric}_k"), b.get(f"{metric}_n")
            return (k, n) if k is not None and n else (None, None)
        unl = sum(x["labels"]["unlabelled"] for x in res)
        if unl: missing.append(f"labels for {unl} unmatched finding(s): precision can't be judged until they're labelled (score.py --label)")
        for metric in ("precision", "recall"):
            k, n = pooled(metric)
            if k is None: missing.append(f"baseline counts for {metric}"); continue
            lo = wilson(k, n)[0]
            val = (lambda x: x["tp"] / (x["tp"] + x["fp"]) if x["tp"] + x["fp"] else 1.0) if metric == "precision" else (lambda x: len(x["hits"]) / len(x["key"]))
            worse = sum(1 for x in res if val(x) < lo - 1e-9)
            if worse * 2 > len(res): why.append(f"{metric} below the baseline's 95% interval (lower bound {lo:.0%} from {k} of {n}) in {worse} of {len(res)} runs")
        if "impact_misses" in b:
            worse = sum(1 for x in res if len(x["impact_misses"]) > b["impact_misses"])
            if worse * 2 > len(res): why.append(f"more impact misses than the baseline in {worse} of {len(res)} runs")
        else: missing.append("baseline counts for impact_misses")
        floor = b.get("decoy_blocking")
        if floor is None and "decoy_block_rate" in b and suite == "3": floor = round(b["decoy_block_rate"] * max(1, len(json.loads((HERE / "decoys3.json").read_text()))))
        if floor is not None and any(x["decoy_blocking"] > floor for x in res): why.append(f"a run flags more decoys at Medium or above than the baseline's {floor} (strict floor)")
        if b.get("tokens") and (b.get("cost_unit") == "usd_millionths") != ("--meta-cost" in args):
            missing.append("cost in the baseline's unit (pass --meta-cost for both the baseline and the gate, or for neither)")
        elif b.get("tokens"):
            if all(t is not None for t in toks):
                better = any(x["tp"] / max(1, x["tp"] + x["fp"]) > b.get("precision", 1) + 1e-9 or x["recall"] > b.get("recall", 1) + 1e-9 for x in res)
                if statistics.median(toks) > 1.10 * b["tokens"] and not better: why.append(f"{'cost' if '--meta-cost' in args else 'tokens'} rose {statistics.median(toks) / b['tokens'] - 1:.0%} with no metric better (cost regression)")
            else: missing.append("token counts for every run (the baseline has them; the cost rule can't run)")
    if why: verdict_("FAIL", why)
    if missing: verdict_("NOT MEASURED", sorted(set(missing)) + (["re-record the baseline with --set-baseline from accepted runs"] if any(m.startswith("baseline counts") for m in missing) else []))
    verdict_("PASS", [])
lower_is_better = {"fp_clean", "false_block", "decoy_rate", "decoy_block_rate", "impact_misses", "decoy_blocking"}
drops = [k for k, v in now.items() if k in b and not k.endswith(("_k", "_n")) and isinstance(v, (int, float)) and ((v > b[k] + 1e-9) if k in lower_is_better else (v + 1e-9 < b[k]))]
if drops: print("BELOW BASELINE: " + ", ".join(f"{k} {now[k]:.2f} vs {b[k]:.2f}" for k in drops)); sys.exit(1)
print("at or above baseline" if b else "no baseline recorded yet (run with --set-baseline once the result is accepted)")
