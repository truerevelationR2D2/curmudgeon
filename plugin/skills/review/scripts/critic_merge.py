#!/usr/bin/env python3
"""Triple-blind merge for Curmudgeon. The counting is done here, in code, never by a model.

usage (from the project root, or set CRITIC_ROOT):
  critic_merge.py tally REVIEW_FILE... [--scan .critic/scan/report.json | --no-scan] [--groups GROUPS.json] [--outside FILE]
                                            blind reviews (JSON, JSONL, or markdown with ```json blocks); --scan adds
                                            the detector's FAIL rows as evidence-backed findings (they are never votes);
                                            --outside adds an outside reviewer's findings (critic_outside.py load): one
                                            extra vote where it agrees with ours, and every finding only it raised is
                                            sent to blind verification, whatever its impact
  critic_merge.py apply VERDICT_FILE...     the blind verifiers' verdicts

Deduplication: two reviewers rarely word the same issue alike, and word overlap can't tell "same issue" from "another
issue in the same file". So tally also writes .critic/dedup-candidates.json: every finding not already merged, listed by file
(no reviewer names, no votes). A dedup agent marks which are the same issue and returns
{"groups": [[raw_id, raw_id, ...], ...]}; run tally again with --groups to count votes on the merged issues.
  critic_merge.py show                      print the current merged findings

tally:
  1. Contract check on every finding (impact, category, file, evidence, failing case, verified tag; a quote of at
     least 12 characters with a name, and a line number, when there is a quote). Failures are rejected with the
     reason, not silently dropped.
  2. Quote check: the quote must start on the cited line or one either side, case and quote marks as written
     (03 §5.56). Otherwise the finding is retracted.
  3. Ledger: a finding the owner marked a false positive (by its stable id) is suppressed, whatever its impact: that
     is an explicit ruling on that exact finding. Not when git tracks .critic/ledger.json: a cloned repository could
     ship rulings, so they are listed in counts.md and hide nothing. Learned memories (patterns from repeated dismissals) never suppress a
     Critical or High finding of any kind.
  4. Cluster the same issue across reviewers; votes = how many reviewers raised it. One reviewer's two findings are
     never one cluster. When the members disagree on the impact (the scan's rule counts), the finding is filed at
     the highest and always verified (impact_split); the verifier may lower it.
     Kept: votes >= 2 of 3, or a single vote with an executed failing case.
     Contested: a single vote at Critical/High that was traced, not executed. It goes to verification.
     Dropped: other single votes. Listed with reasons so drops can be audited.
  5. Writes .critic/verify/<id>.json, one blind packet per finding (the claim and the code only: no teardown, no votes,
     no reviewer names), and .critic/tally.json.
apply:
  Verdicts are confirmed | refuted | downgrade | unclear. A refutation must be concrete: at least 60 characters and
  a file:line that exists (the guard, or the line relying on a platform rule), a run or trace, and no hedging
  (critic_findings.refutation_problem, the same rule the verifier's stop check uses); otherwise it counts as unclear
  and the finding stays. Refuting a Critical also needs the verifier to have run or traced it. A verifier may
  lower an impact, never raise it. Writes .critic/findings.jsonl, .critic/findings.sarif and .critic/counts.md, and
  records every kept finding in the ledger (new, known or regressed)."""
import hashlib, json, math, os, pathlib, re, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import verdict_required, NIT, IMPACTS, extract_findings, norm_code, relocate_quote, fingerprint, quote_check, read_jsonl, refutation_problem, confirmation_problem, security_refutation_problem, similar, log_run, append_line, refuse_linked_state, to_sarif, validate, write_jsonl, tokens, scrub, redact_finding_text, write_manifest, strip_workspace_path, _cites_real_line

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"

# Browser results that are measurements (the same page gives the same number) skip verification. Everything else the
# detector reports, such as console errors or controls that seem dead, can come from the test setup, so it is verified.
MEASURED = re.compile(r"^(axe-(?!incomplete)|no-focus-style|not-focusable|focus-obscured|sideways|sr-unnamed|tab-reach|budget-)")

def die(m): print(f"critic_merge: {m}", file=sys.stderr); sys.exit(2)

def norm_path(p):
    p = strip_workspace_path(str(p or "").strip()).replace("\\", "/")
    try:
        q = pathlib.Path(p)
        if q.is_absolute(): p = str(q.resolve().relative_to(ROOT))
    except (ValueError, OSError): pass
    while p.startswith("./"): p = p[2:]
    return p

def load_review(path):
    p = pathlib.Path(path)
    if not p.exists(): die(f"{path} does not exist")
    text = p.read_text(encoding="utf-8", errors="replace")  # a damaged file is read, never a crash (§5.56 round 3)
    try:
        v = json.loads(text)
        rows = v if isinstance(v, list) else (v.get("findings", [v]) if isinstance(v, dict) else [])  # null, a number or a string holds no findings
        if not isinstance(rows, list): rows = []
    except json.JSONDecodeError:
        rows = extract_findings(text)
        if not rows:
            try: rows = read_jsonl(p)
            except ValueError: rows = []
    return [dict(r, source=r.get("source") or p.stem) for r in rows if isinstance(r, dict)]

def inside_root(rel):
    """Findings may only point inside the project: an absolute path, .. or a link out is never read or verified."""
    if not rel: return True
    if pathlib.PurePath(rel).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", rel): return False
    if ".critic" in pathlib.PurePath(rel).parts: return False  # our own state: a verifier sent there would read the reviews, and the review would stop being blind
    try: (ROOT / rel).resolve().relative_to(ROOT); return True
    except (ValueError, OSError): return False

def cell_(t): return str(t).replace("|", "/").replace("\n", " ")

def coverage_report(cov):
    """Not reviewed, computed by script: payload files (from the change map) that no reviewer reports reading, plus any
    file a reviewer says it didn't reach. Unknown when reviewers report nothing."""
    try: payload = [str(x) for x in json.loads((D / "change-map.json").read_text()).get("files", [])]
    except (OSError, ValueError): payload = []
    if not cov["read"] and not cov["not_reached"]: return {"known": False, "payload": len(payload)}
    missing = sorted((set(payload) - cov["read"]) | (cov["not_reached"] - cov["read"]))
    return {"known": True, "payload": len(payload), "read": len(cov["read"]), "not_reviewed": missing}

def ledger():
    try: return json.loads((D / "ledger.json").read_text())
    except Exception: return {}

def ledger_committed():
    """True when git tracks .critic/ledger.json: a cloned repository can ship one whose rulings would hide findings,
    so its false-positive rulings never hide anything (they are listed in counts.md instead)."""
    from critic_findings import ledger_shipped
    return ledger_shipped(ROOT)

MEMORY_HITS = []
def suppressed_by_ledger(f, L):
    """Only the owner's explicit ruling on this exact finding (fp <id>) hides it, and it is still listed under
    "Hidden by your rulings" in counts.md. Learned memories never hide anything: see memory_note."""
    for x in L.get("false_positives", []):
        xid = x.get("id")
        if not xid: continue
        old = (L.get("findings") or {}).get(xid) or {}
        if old.get("score") and IMP_RANK.get(str(f.get("impact", "")).title(), 2) < IMP_RANK.get(old["score"], 2): continue  # never hide a finding more serious than the one ruled on
        if xid == f.get("id"): return f"known false positive (owner's ruling on this exact finding): {x.get('why', '')}"  # the exact id only: an alias could carry the ruling onto another finding (03 §5.56 item 14)
    return None

def ruling_like(f, L):
    """An owner's false-positive ruling on the same quoted code under another category: shown next to the finding,
    never hiding it (03 §5.56 item 14: an XSS ruling once hid a performance finding on the same line)."""
    from critic_findings import fingerprint2
    mine = fingerprint2(f)
    if not mine: return None
    for x in L.get("false_positives", []):
        old = (L.get("findings") or {}).get(x.get("id")) or {}
        if x.get("id") and mine == fingerprint2({"file": str(old.get("where", "")).rsplit(":", 1)[0], "quote": old.get("quote")}):
            return {"ruling": x.get("id"), "why": str(x.get("why", ""))[:200]}
    return None

def memory_note(f, L):
    """Learned memories ANNOTATE, never hide: a finding that looks like ones the owner dismissed before stays in the
    findings and the counts, with a note naming the earlier reason, so the owner decides in seconds (critic_ledger.py
    dismiss --like N closes them on purpose). No notes on Critical or High findings: a note must never nudge anyone past one.
    The verifier never sees notes; its packet is built from a fixed field list."""
    if f.get("impact") in ("Critical", "High"): return None  # memories come only from Medium/Low dismissals, and only note those
    for i, m in enumerate(L.get("memories", [])):
        if m.get("retired"): continue
        if m.get("file_glob") and not pathlib.PurePath(f.get("file") or "").match(m["file_glob"]): continue
        ft, mt = tokens(f"{f.get('category')} {f.get('title')}"), tokens(m.get("pattern", ""))
        if mt and len(ft & mt) / max(1, len(mt)) >= 0.6:
            MEMORY_HITS.append(i + 1); return {"memory": i + 1, "reason": m.get("reason"), "pattern": m.get("pattern"), "dismissed": m.get("count", 3)}
    return None

IMP_RANK = {k: i for i, k in enumerate(IMPACTS + (NIT,))}  # a verifier may lower a Low to a Nit (SC-79)

# A scripted FAIL's impact by rule (it used to be High for every rule). A live credential is Critical; code that runs
# input, or a page that throws, is High; an accessibility or layout failure is Medium unless it locks people out.
SCAN_IMPACT = {"eval": "High", "py-eval": "High", "console-error": "High", "click-error": "High", "not-focusable": "High",
               "no-focus-style": "Medium", "focus-obscured": "Medium", "zoom-off": "Medium", "html-nested-interactive": "Medium", "sideways": "Medium",
               "test-const-assert": "Medium", "test-duplicate-name": "Medium",
               "ci-pwn-request": "Critical", "ci-if-always-true": "Medium", "agent-literal-credential": "Critical"}  # a test that can't fail hides bugs; it isn't one itself
def scan_impact(rule):
    try:
        import scan_secrets
        secret = {rid for rid, sev, *_ in scan_secrets.PROVIDERS if sev == "FAIL"} | {"private-key", "db-url-password"}
    except Exception: secret = set()
    base = rule[len("secret-"):] if rule.startswith("secret-") else rule  # the secret scan reports its rules as secret-<id>
    return "Critical" if rule.startswith("secret-") and base in secret else SCAN_IMPACT.get(rule, "High")

def scan_rows(path):
    try: rep = json.loads(pathlib.Path(path).read_text())
    except Exception as e: die(f"can't read scan report {path}: {e}")
    out = []
    for r in rep.get("findings", []):
        if r.get("sev") != "FAIL": continue
        m = re.match(r"(.+?):(\d+)$", r.get("where", ""))
        out.append({"category": r["rule"], "impact": scan_impact(r["rule"]), "file": m.group(1) if m else r.get("where", ""), "line": int(m.group(2)) if m else 0,
                    "quote": "", "title": r["what"], "evidence": f"scripted row {r.get('id')} ({r.get('rule')})", "failing_case": r.get("evidence") or r["what"],
                    "verified": "executed" if r.get("level") == "runtime" else "traced", "remediation": "", "source": "scan", "scan_id": r.get("id")})
    return out

def split_same_reviewer(mem, outside_ri=None):
    """A cluster holding two findings from one reviewer (or two scanner rows) is two issues joined through a third
    finding (A1~B and A2~B), never one: split it. A reviewer's repeated finding (same id: file, category and quote) is
    one finding, not two. Each of the busiest reviewer's findings seeds a group; every other member joins the group it
    is most like (a member similar() to it first, then the same file and the closest line) among those with nothing yet
    from its reviewer. Outside rows only add a vote (they can't merge or split our findings): they never seed a group,
    and join the group they are most like. mem is a list of (raw id, reviewer index or None for the scan, finding)."""
    key = lambda ri: "scan" if ri is None else ri
    ours = lambda x: outside_ri is None or x[1] != outside_ri
    seen, kinds = set(), {}
    for x in mem:
        if ours(x):
            k = (key(x[1]), x[2].get("id"))
            if k not in seen: seen.add(k); kinds[key(x[1])] = kinds.get(key(x[1]), 0) + 1
    if all(v == 1 for v in kinds.values()): return [mem]
    most = max(kinds, key=lambda k: (kinds[k], str(k)))
    groups, first = [], {}
    for x in mem:
        if ours(x) and key(x[1]) == most:
            fid = x[2].get("id")
            if fid in first: first[fid].append(x)  # the same finding written twice: one group
            else: first[fid] = [x]; groups.append(first[fid])
    def fit(x, g):
        return (0 if any(similar(x[2], y[2]) for y in g) else 1,
                min((0 if y[2]["file"] == x[2]["file"] else 1, abs(int(y[2].get("line") or 0) - int(x[2].get("line") or 0))) for y in g))
    for x in sorted((x for x in mem if not (ours(x) and key(x[1]) == most)), key=lambda x: (str(x[2]["file"]), int(x[2].get("line") or 0))):
        same_id = [g for g in groups if any(ours(y) and key(y[1]) == key(x[1]) and y[2].get("id") == x[2].get("id") for y in g)] if ours(x) else []
        if same_id: same_id[0].append(x); continue  # this reviewer's repeat of a finding already placed
        free = groups if not ours(x) else [g for g in groups if key(x[1]) not in {key(y[1]) for y in g if ours(y)}]
        best_ = min(free, key=lambda g: fit(x, g)) if free else None
        if best_ is not None and (fit(x, best_)[0] == 0 or not ours(x) or x[1] is None): best_.append(x)  # outside rows and scan rows go to the nearest group
        else: groups.append([x])  # like none of the groups it may join: its own finding, never folded into another (§5.56 round 3)
    return groups

def matched_votes(rows):
    """The most reviewers joined by similar() alone among one group's members: the agreement the script itself saw,
    without the dedup agent's groups (an agreed Low skips verification only on this, §5.56)."""
    par = list(range(len(rows)))
    def f_(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if rows[i][0] != rows[j][0] and similar(rows[i][1], rows[j][1]): par[f_(i)] = f_(j)
    comp = {}
    for i, (ri, _) in enumerate(rows): comp.setdefault(f_(i), set()).add(ri)
    return max((len(v) for v in comp.values()), default=0)

def tally(paths):
    scan = groups = None
    if "--groups" in paths:
        i = paths.index("--groups"); gp = paths[i + 1] if i + 1 < len(paths) else die("--groups needs a file"); paths = paths[:i] + paths[i + 2:]
        try: groups = json.loads(pathlib.Path(gp).read_text()).get("groups", [])
        except Exception as e: die(f"can't read groups {gp}: {e}")
    outside = None
    if "--outside" in paths:
        i = paths.index("--outside"); outside = paths[i + 1] if i + 1 < len(paths) else die("--outside needs a file"); paths = paths[:i] + paths[i + 2:]
    if "--scan" in paths:
        i = paths.index("--scan"); scan = paths[i + 1] if i + 1 < len(paths) else die("--scan needs a report path"); paths = paths[:i] + paths[i + 2:]
    no_scan = "--no-scan" in paths; paths = [x for x in paths if x != "--no-scan"]
    degraded = ["the scripted checks did not run (the tally went on without them)"] if no_scan else []
    if scan:
        try: blocked = json.loads(pathlib.Path(scan).read_text()).get("degraded") or []
        except (OSError, ValueError, AttributeError): blocked = []
        if blocked: degraded.append("these scripted checks could not run: " + ", ".join(map(str, blocked)))  # SKILL.md rule 8: blocked or unavailable checks make the review DEGRADED
    if not paths: die("tally needs the blind review files (for example .critic/reviews/review-*.json); refusing to count scan rows alone")
    started = ledger().get("started_at")
    if started:  # a review file older than this run is left over from an earlier one: counting it would invent votes
        stale = [p for p in paths if pathlib.Path(p).resolve().parent == (D / "reviews").resolve() and pathlib.Path(p).exists()
                 and pathlib.Path(p).stat().st_mtime < started - 2]
        if stale: die(f"refusing to count {', '.join(stale)}: written before this run started, so it is from an earlier run. Remove it, or have a fresh reviewer write it again")
    reviews = [load_review(p) for p in paths]
    blind = set()  # 03 §5.56 item 15: reviews whose agent the stop hook saw working in its private copy
    for st_ in (D / "stops").glob("*.json") if (D / "stops").is_dir() and not (D / "stops").is_symlink() else []:  # written by the stop hook; agents can't write there
        try:
            j_ = json.loads(st_.read_text())
            if j_.get("workspace") and (not started or float(j_.get("at") or 0) >= started - 2): blind.add(j_.get("review"))
        except (OSError, ValueError, AttributeError, TypeError): pass
    unproven = [pathlib.Path(p).name for p in paths if pathlib.Path(p).resolve().parent == (D / "reviews").resolve() and pathlib.Path(p).name not in blind]
    if unproven: degraded.append(f"blindness not shown for {', '.join(unproven)} (no record that its agent worked in a private copy: the hooks may not have run)")
    coverage = {"read": set(), "not_reached": set()}  # files the reviewers say they read, and the ones they didn't reach (SC-46)
    sandbox = []  # sandbox scenario lines: numbered SB1, SB2 ... here, so the teardown's SANDBOX LEDGER has a source (SC: self-review D C6)
    set_aside = []  # candidates a reviewer dropped, with the guard it relied on: logged so the eval can measure self-filtering, never counted
    for p in paths:
        try: v = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        except (ValueError, OSError): continue
        cov = v.get("coverage") if isinstance(v, dict) else None
        if isinstance(cov, dict):
            for k_ in ("read", "not_reached"):
                if isinstance(cov.get(k_), list): coverage[k_] |= {norm_path(str(x)) for x in cov[k_] if isinstance(x, str)}
        aside = v.get("set_aside") if isinstance(v, dict) else None
        if isinstance(aside, list):  # anything else (null, a number) is ignored: the list is only a log
            set_aside += [dict(scrub(x), reviewer=pathlib.Path(p).stem) for x in aside if isinstance(x, dict)]
        sb = v.get("sandbox") if isinstance(v, dict) else None
        if isinstance(sb, list):
            for x in sb[:40]:
                if not isinstance(x, dict) or not str(x.get("scenario") or "").strip(): continue
                x = {k: redact_finding_text(str(x.get(k) or "")) for k in ("scenario", "happens", "result", "how")}  # a key typed into a scenario is masked like any finding text
                sandbox.append({"id": f"SB{len(sandbox) + 1}", "reviewer": pathlib.Path(p).stem[-1:], "scenario": str(x.get("scenario"))[:200],
                                "happens": str(x.get("happens") or "")[:300], "result": str(x.get("result") or "")[:120],
                                "how": "driven" if str(x.get("how") or "").lower() == "driven" else "traced"})
    n = len(reviews); need = 1 if n == 1 else math.ceil(2 * n / 3)
    # an outside run we can't see never counts as executed: verification decides
    outside_rows = [dict(r, source="outside", verified=r.get("verified") if r.get("verified") == "inferred" else "traced") for r in load_review(outside)] if outside else []
    L = ledger(); out = {"tier": L.get("tier") or "full", "degraded": degraded, "reviewers": n, "votes_needed": need, "outside": None, "kept": [], "contested": [], "dropped": [], "retracted": [], "rejected": [], "suppressed": [], "ruling_committed": [], "set_aside": set_aside, "sandbox": sandbox, "nits": [], "coverage": coverage_report(coverage)}
    scanned = scan_rows(scan) if scan else []
    accepted = []  # (raw_id, reviewer_index or None for scan, finding)
    OUTSIDE_RI = len(reviews) + 1
    for ri, rows in list(enumerate(reviews)) + ([(len(reviews), scanned)] if scanned else []) + ([(OUTSIDE_RI, outside_rows)] if outside else []):
        is_scan = bool(scanned) and ri == len(reviews)
        for k, f in enumerate(rows):
            for k_ in ("impact", "category", "title", "file", "evidence", "failing_case", "verified", "remediation", "quote"):
                if f.get(k_) is not None and not isinstance(f[k_], str): f[k_] = json.dumps(f[k_], ensure_ascii=False)  # a pasted or malformed value never crashes a later step
            if f.get("quote") is None: f["quote"] = ""  # "quote": null is no quote, not a crash
            f["impact"] = str(f.get("impact", "")).title(); f["file"] = norm_path(f.get("file"))
            if not inside_root(f["file"]):
                out["rejected"].append({"finding": f, "why": ["names a file outside the project: never read, never sent to a verifier"]}); continue
            try: f["line"] = int(re.match(r"\s*(\d+)", str(f.get("line") or "0")).group(1))
            except AttributeError: f["line"] = 0
            f["id"] = fingerprint(f); f["raw"] = "x" + hashlib.sha1(f"{ri}|{k}|{f['id']}".encode()).hexdigest()[:7]  # opaque: the dedup agent can't tell reviewers apart
            errs = validate(f)
            if errs: out["rejected"].append({"finding": f, "why": errs}); continue
            if f["verified"] == "executed" and not f.get("quote") and not is_scan:
                f["verified"] = "traced"  # an 'executed' claim needs a quote the script can check; without one it counts as traced
            q = quote_check(f, ROOT)
            if q is False and ri == OUTSIDE_RI:  # another model's viewer may number lines differently: a long quote found on exactly one line is moved there
                moved = relocate_quote(f, ROOT)
                if moved: f["line_cited"], f["line"] = f["line"], moved; f["id"] = fingerprint(f); q = True
            if q is False:  # retracted all the same; the tally only notes when the exact quote is elsewhere in that file (a wrong line number, often from cat -n over several files)
                elsewhere = relocate_quote(f, ROOT) if ri != OUTSIDE_RI else None
                out["retracted"].append({"finding": f, "why": "quoted code is not at the cited file:line" + (f" (the exact quote is at line {elsewhere}: a wrong line number, still retracted)" if elsewhere else "")}); continue
            f["quote_checked"] = q is True
            req = f.get("requirement") if isinstance(f.get("requirement"), dict) else None
            if req and req.get("basis") == "stated" and not _cites_real_line(req.get("where"), ROOT):
                req["basis"] = "inferred"; req["why"] = f"cited {req.get('where')}, which is not a real line"; f["requirement"] = req
            if req and req.get("basis") == "inferred" and f["impact"] in ("Critical", "High"):  # SC-55: inferred is not stated
                f["impact_capped_from"] = f["impact"]; f["impact"] = "Medium"
            s_ = suppressed_by_ledger(f, L)
            if s_ and ledger_committed():  # a ledger the repository ships could be anyone's: its rulings are shown, never applied
                out["ruling_committed"].append({"finding": f, "why": s_}); s_ = None
            if s_: out["suppressed"].append({"finding": f, "why": s_}); continue
            rl = ruling_like(f, L) if not ledger_committed() else None
            if rl: f["ruling_like"] = rl
            if f["impact"] == NIT:  # SC-79: listed under Nits, never counted, never voted on, never verified
                if not any(similar(f, x) for x in out["nits"]): out["nits"].append(f)
                continue
            note = memory_note(f, L)
            if note: f["memory_note"] = note
            accepted.append((f["raw"], None if is_scan else ri, f))
    out_raised = sum(1 for _, ri, _ in accepted if ri == OUTSIDE_RI)
    parent = {r: r for r, _, _ in accepted}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        if a in parent and b in parent: parent[find(a)] = find(b)
    for i in range(len(accepted)):
        for j in range(i + 1, len(accepted)):
            ra, ia, a = accepted[i]; rb, ib, b = accepted[j]
            if ia == ib and ia != OUTSIDE_RI and a.get("id") == b.get("id"): union(ra, rb); continue  # one source's repeat of one finding (same file, category and quote) is one finding, never two votes or two packets (§5.56 round 3)
            if ia == ib or OUTSIDE_RI in (ia, ib): continue  # outside findings are attached below, one cluster each: they never join two of ours  # never merge two findings from the same reviewer (or two scanner rows: two keys on one line are two leaks)
            if similar(a, b): union(ra, rb)
    is_doc = {r: bool(re.search(r"\.(md|mdx|markdown|rst|txt|adoc)$|(^|/)(readme|changelog|license|contributing)$", f["file"] or "", re.I)) for r, _, f in accepted}  # by file type, never by a name inside a code path
    outside_raw = {r for r, ri, _ in accepted if ri == OUTSIDE_RI}
    for g in groups or []:
        g = [x for x in g if x in parent and x not in outside_raw]
        for kind in (True, False):  # a false claim in the docs and the code that makes it false are fixed in different places: never merged
            part = [x for x in g if is_doc[x] == kind]
            for x in part[1:]: union(part[0], x)
    # Attach each outside finding to at most ONE of our clusters (similar wording, or grouped with it by the dedup
    # agent), the nearest by file and line. It adds a vote there and nothing else: it can't merge two of our findings,
    # and it never sets the impact (see below).
    ours = [(r, f) for r, ri, f in accepted if ri != OUTSIDE_RI]
    grouped = {}
    for g in groups or []:
        for x in g: grouped.setdefault(x, set()).update(g)
    for r, ri, f in accepted:
        if ri != OUTSIDE_RI: continue
        fq = dict(f, quote=f.get("quote") if len(norm_code(f.get("quote"))) >= 12 else "")  # a one-letter quote matches anything: never enough to attach
        cands = [(0 if o["file"] == f["file"] else 1, abs(int(o.get("line") or 0) - int(f.get("line") or 0)), ro) for ro, o in ours
                 if similar(fq, dict(o, quote=o.get("quote") if len(norm_code(o.get("quote"))) >= 12 else "")) or ro in grouped.get(r, ()) and is_doc[ro] == is_doc[r]]
        if cands: parent[r] = find(min(cands)[2])
    # The dedup agent gets every finding not already merged, listed by file (pairs by line distance missed real
    # duplicates cited at distant lines or in another file). No reviewer names or votes; ids are opaque.
    by_root = {}
    for r, ri, f in accepted: by_root.setdefault(find(r), []).append((r, ri, f))
    parts = [p_ for mem in by_root.values() for p_ in split_same_reviewer(mem, OUTSIDE_RI)]  # §5.56: grouping is transitive; one reviewer's two findings stay two
    by_file = {}
    for mem in parts:
        r, _, f = mem[0]
        by_file.setdefault(f["file"] or "(no file)", []).append({"id": r, "also": [x for x, _, _ in mem[1:]], "line": f["line"], "title": f["title"], "quote": f.get("quote", "")[:200]})
    cands = sum(len(v) for v in by_file.values()) if len(parts) > 1 else 0
    (D).mkdir(parents=True, exist_ok=True)
    (D / "dedup-candidates.json").write_text(json.dumps({"instructions": "Group findings that describe the same underlying issue (same cause, one fix resolves both), within a file or across files. Return {\"groups\": [[id, ...], ...]} listing only merged sets; use the 'id' values.", "findings_by_file": scrub(by_file)}, indent=1, ensure_ascii=False))
    clusters = []
    for mem in parts:
        c = {"members": [], "reviewers": set(), "scan": False, "outside": False}
        for r, ri, f in mem:
            c["members"].append(f)
            if ri is None: c["scan"] = True
            elif ri == OUTSIDE_RI: c["outside"] = True
            else: c["reviewers"].add(ri)
        c["votes_matched"] = matched_votes([(ri, f) for _, ri, f in mem if ri is not None and ri != OUTSIDE_RI])  # reviewers the script itself matched within this group, without the dedup agent
        clusters.append(c)
    of = n + (1 if outside else 0)
    if outside:
        out["outside"] = {"file": str(outside), "raised": len(outside_rows), "accepted": out_raised,
                          "lines_corrected": sum(1 for _, ri, f in accepted if ri == OUTSIDE_RI and f.get("line_cited")),
                          "matched_ours": sum(1 for c in clusters if c["outside"] and (c["reviewers"] or c["scan"])),
                          "only_outside": sum(1 for c in clusters if c["outside"] and not c["reviewers"] and not c["scan"])}
    for c in clusters:
        m = c["members"]; votes = len(c["reviewers"]) + (1 if c["outside"] else 0)
        if c["outside"] and not c["reviewers"] and not c["scan"]:  # only the outside reviewer saw it: always verified blind
            best = sorted(m, key=lambda x: IMP_RANK[x["impact"]])[0]
            out["contested"].append(dict(best, votes=1, of=of, outside_only=True, scan_confirmed=False, locations=[f"{best['file']}:{best.get('line', '')}"], raised_by=["outside"])); continue
        if votes == 0 and c.get("scan"):  # found only by the detector: kept on its evidence, verified like any other
            f = dict(m[0], votes=0, of=of, locations=[f"{m[0]['file']}:{m[0].get('line', '')}"], raised_by=["scan"], scan_confirmed=True, **({"measured": True} if m[0].get("verified") == "executed" and MEASURED.match(str(m[0].get("category"))) else {}))
            out["kept"].append(f); continue
        # impact, wording and evidence come from our own reviewers (or the scan); an outside finding only adds its vote
        human = [x for x in m if x.get("source") not in ("scan", "outside")] or [x for x in m if x.get("source") != "outside"] or m
        best = sorted(human, key=lambda x: (["executed", "traced", "inferred"].index(x["verified"]), IMP_RANK[x["impact"]]))[0]
        theirs = [x["impact"] for x in m if x.get("source") == "outside"]
        rated = sorted({x["impact"] for x in human + [y for y in m if y.get("source") == "scan"] if x["impact"] in IMP_RANK and x["impact"] != NIT}, key=lambda k: IMP_RANK[k])  # the scan's rule is a rating too: a scripted High that reviewers call Low is a disagreement
        f = dict(best, votes=votes, votes_ours=len(c["reviewers"]), votes_matched=c["votes_matched"], of=of, impact=rated[0] if rated else "Low", scan_confirmed=bool(c.get("scan")),
                 locations=sorted({f"{x['file']}:{x.get('line', '')}" for x in m}), raised_by=sorted({x["source"] for x in m}))
        if any(x.get("source") == "scan" and x.get("verified") == "executed" and MEASURED.match(str(x.get("category"))) for x in m): f["measured"] = True  # a scripted runtime measurement is in this cluster
        if len(rated) > 1: f["impact_split"] = rated  # §5.56: reviewers disagreed on the impact; it is filed at the highest and always verified, and the verifier may lower it
        else: f.pop("impact_split", None)
        if theirs: f["outside_impact"] = theirs[0]  # shown, never used: the outside reviewer's own rating
        if c.get("scan") and best.get("source") != "scan":  # a reviewer restated a scripted row: keep the script's evidence too
            f["scan_evidence"] = [x["evidence"] for x in m if x.get("source") == "scan"]
        mn = next((x["memory_note"] for x in m if x.get("memory_note")), None)
        if mn and f["impact"] in ("Medium", "Low"): f["memory_note"] = mn
        else: f.pop("memory_note", None)
        executed = any(x["verified"] == "executed" for x in m) or bool(c.get("scan"))
        unanchored = not any(x.get("quote_checked") for x in m if x.get("source") != "outside") and not c.get("scan")
        if unanchored and not executed and len(c["reviewers"]) < 2 and f["impact"] in ("Critical", "High", "Medium"): out["contested"].append(f)  # an outside vote never stands in for a check  # nothing the script could check: verify it, even on one reviewer
        elif votes >= need or executed: out["kept"].append(f)
        elif f["impact"] in ("Critical", "High"): out["contested"].append(f)
        else: out["dropped"].append({"finding": f, "why": f"raised by {votes} of {n} reviewers, not executed"})
    vd = D / "verify"; vd.mkdir(parents=True, exist_ok=True)
    for old in vd.glob("*.json"): old.unlink()
    for f in out["kept"] + out["contested"]:
        if f["impact"] == "Low" and not f.get("impact_split") and f.get("votes_matched", 0) >= need and not f.get("outside_only"): continue  # agreed Lows skip verification: only when every reviewer said Low and the script itself matched enough of them (a dedup group or an outside vote alone never skips it, §5.56)
        if f.get("raised_by") == ["scan"] and f.get("verified") == "executed" and MEASURED.match(str(f.get("category"))): continue  # a measurement, not an interpretation: nothing to reproduce
        packet = {k: f.get(k) for k in ("id", "category", "impact", "file", "line", "quote", "title", "failing_case", "preconditions", "root_cause") if k in f}
        (vd / f"{f['id']}.json").write_text(json.dumps(scrub(packet), indent=1, ensure_ascii=False))
    (D / "tally.json").write_text(json.dumps(scrub(out), indent=1, ensure_ascii=False))
    if MEMORY_HITS and (D / "ledger.json").exists():  # keep memories that are in use from retiring
        led = pathlib.Path(__file__).resolve().parent / "critic_ledger.py"
        for n_ in sorted(set(MEMORY_HITS)): subprocess.run([sys.executable, str(led), "memories", "--hit", str(n_)], cwd=ROOT, env=dict(os.environ, CRITIC_ROOT=str(ROOT)), capture_output=True)
    print(f"{n} review(s), {sum(len(r) for r in reviews)} raw findings → kept {len(out['kept'])}, contested {len(out['contested'])}, "
          f"dropped {len(out['dropped'])}, retracted {len(out['retracted'])}, rejected {len(out['rejected'])}, hidden by your rulings {len(out['suppressed'])}, "
          f"noted as like past dismissals {sum(1 for f in out['kept'] + out['contested'] if f.get('memory_note'))}")
    print(f"verification packets: {len(list(vd.glob('*.json')))} in {vd.relative_to(ROOT)}")
    if out["outside"]: print("outside reviewer: {raised} raised, {accepted} passed the contract and quote checks ({lines_corrected} at a corrected line), {matched_ours} matched ours, {only_outside} only theirs (all sent to verification)".format(**out["outside"]))
    if not groups and cands: print(f"dedup: {cands} finding(s) listed in .critic/dedup-candidates.json; have a dedup agent group them, then rerun tally with --groups")
    return 0

VERIFIER_LOG = []
def write_verifier_log():
    """Every refutation and downgrade is kept in .critic/refutations.jsonl, so a verifier that talks the review out of
    real bugs can be caught: the spot-check (critic_ledger.py spotcheck) and the eval kit sample these."""
    if not VERIFIER_LOG: return
    try: run_no = json.loads((D / "ledger.json").read_text()).get("run", 0)
    except Exception: run_no = 0
    seen = set()
    try: old = (D / "refutations.jsonl").read_text(encoding="utf-8", errors="replace").splitlines() if (D / "refutations.jsonl").exists() else []
    except OSError: old = []
    for line in old:
        try: x = json.loads(line); seen.add((x.get("run"), x.get("id"), x.get("kind")))
        except (ValueError, AttributeError, TypeError): continue  # a damaged line never stops apply
    for kind, f, why, rep in VERIFIER_LOG:
        if (run_no, f.get("id"), kind) in seen: continue  # apply run twice on the same verdicts logs each drop once
        append_line(D / "refutations.jsonl", json.dumps(scrub({"run": run_no, "at": time.strftime("%Y-%m-%d %H:%M"), "kind": kind, "id": f.get("id"), "impact": f.get("impact"),
                             "file": f.get("file"), "line": f.get("line"), "title": f.get("title"), "failing_case": f.get("failing_case"),
                             "why": redact_finding_text(why), "reproduced": rep, "votes": f.get("votes"), "of": f.get("of")}), ensure_ascii=False) + "\n")

def revision_stamp(final):
    """What these findings were reviewed against (SC-38): the git commit, whether the working tree had uncommitted
    changes, and a sha256 of the cited files' contents."""
    def git(*a):
        try: return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired): return ""
    h = hashlib.sha256()
    for f in sorted({str(x.get("file") or "") for x in final}):
        p = ROOT / f
        if f and inside_root(f) and p.is_file(): h.update(f.encode() + b"\0" + p.read_bytes() + b"\0")
    return {"sha": git("rev-parse", "--short=12", "HEAD") or None, "dirty": bool(git("status", "--porcelain", "--", ".", ":(exclude).critic")), "payload_sha256": h.hexdigest(),
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}

def mark_origin(final):
    """In a review of a change (critic_map.py from a git diff), mark each finding introduced or pre-existing (SC-43),
    by script: introduced when its line, or any file:line its evidence, failing case or locations cite, falls in a
    changed hunk, or its file is new. A new caller reaching an old sink therefore counts as introduced. Both kinds are
    counted; pre-existing ones get their own section."""
    try: cm = json.loads((D / "change-map.json").read_text())
    except (OSError, ValueError): return
    if cm.get("mode") != "diff": return
    hk, new = cm.get("hunks") or {}, set(cm.get("new_files") or [])
    def touched(file, line):
        return file in new or any(a <= line < a + max(c, 1) for a, c in hk.get(file, []))
    for f in final:
        locs = [(str(f.get("file") or ""), safe_line(f.get("line")))]
        for text in (f.get("evidence"), f.get("failing_case"), " ".join(f.get("locations") or [])):
            locs += [(m.group(1), int(m.group(2))) for m in re.finditer(r"([\w./-]+\.\w+):(\d+)", str(text or ""))]
        f["origin"] = "introduced" if any(touched(fl, ln) for fl, ln in locs if fl) else "pre-existing"

def safe_line(v):
    try: return int(v or 0)
    except (TypeError, ValueError): return 0

def fix_status(f):
    """Whether a finding's remediation can be offered as a fix: usable, partial (it says so), or not offerable (empty,
    the same as the quoted code, or with unbalanced brackets or quotes in its code)."""
    rem = str(f.get("remediation") or "").strip()
    if not rem: return "none"
    code = re.findall(r"`([^`]+)`", rem) or ([rem] if re.search(r"[(){}\[\];=]", rem) else [])
    if any(norm_code(c) and norm_code(c) == norm_code(f.get("quote")) for c in code) or norm_code(rem) == norm_code(f.get("quote")): return "not offerable: the fix is the same as the code"
    for c in code:
        if any(c.count(a) != c.count(b) for a, b in ("()", "[]", "{}")) or c.count('"') % 2 or c.count("'") % 2 and not re.search(r"\w'\w", c):
            return "not offerable: unbalanced brackets or quotes"
    return "partial" if re.search(r"(?i)\bpartial(ly)?\b|\bonly part\b|\bstop-?gap\b|\bworkaround\b", rem) else "usable"

def apply(paths):
    try: T = json.loads((D / "tally.json").read_text())
    except Exception as e: die(f"run tally first ({e})")
    verdicts = {}; stale = []
    t_mtime = (D / "tally.json").stat().st_mtime
    for p in paths:
        if pathlib.Path(p).exists() and pathlib.Path(p).resolve().parent in ((D / "verdicts").resolve(), (D / "verdicts-variants").resolve()) and pathlib.Path(p).stat().st_mtime < t_mtime:
            stale.append(pathlib.Path(p).name); continue  # a verdict on an earlier tally's packet (an earlier round): never applied to this one (§5.56 round 2)
        for v in load_review(p): verdicts[v.get("id")] = v
    final, refuted, notes, unverified, missing = [], [], [], [], []
    if stale: notes.append(f"not applied, older than this tally: {', '.join(stale[:8])}{' ...' if len(stale) > 8 else ''}")
    tier = T.get("tier") or ledger().get("tier") or "full"; contested = {f.get("id") for f in T["contested"]}
    for f in T["kept"] + T["contested"]:
        v = verdicts.get(f["id"])
        if v is None:
            if f.get("outside_only"):  # nothing of ours checked it and no verifier did: it is not a finding yet
                unverified.append(f); notes.append(f"{f['id']}: outside-only finding with no verdict; left out of the findings until a verifier judges it")
                if (D / "verify" / f"{f['id']}.json").exists(): missing.append(f["id"])  # every tier verifies these (verdict_required): its absence marks the run DEGRADED
                continue
            if (D / "verify" / f"{f['id']}.json").exists():
                if verdict_required(tier, f, f["id"] in contested):  # §5.56: the tier needed this verdict, and it never came
                    notes.append(f"{f['id']}: no verdict returned, and the {tier} tier verifies this finding; kept, confidence lowered"); f["verifier"] = "missing"; missing.append(f["id"])
                else: f["verifier"] = "not-in-tier"  # the tier doesn't verify this one (lite: Medium and Low): a design choice, not a failure
            final.append(f); continue
        kind = str(v.get("verdict", "unclear")).lower(); raw = str(v.get("refutation") or v.get("reason") or "")
        why = redact_finding_text(raw)  # a refutation can quote a secret: it is checked raw, stored masked
        if kind == "confirmed":
            cp = confirmation_problem(v, root=ROOT)
            if cp: kind = "unclear"; notes.append(f"{f['id']}: confirmation without evidence counted as unclear ({cp})")
        if kind == "refuted":
            prob = refutation_problem(raw, f["impact"], v.get("reproduced"), root=ROOT) or security_refutation_problem(v, f)
            if not prob:
                refuted.append({"finding": f, "why": why}); VERIFIER_LOG.append(("refuted", f, why, v.get("reproduced"))); continue
            kind = "unclear"; notes.append(f"{f['id']}: refutation not concrete enough to drop it ({prob}); kept")
        if kind == "downgrade":
            new = str(v.get("impact_after", "")).title()
            if new in IMP_RANK and IMP_RANK[new] > IMP_RANK[f["impact"]]:
                VERIFIER_LOG.append(("downgraded", dict(f), f"{f['impact']} to {new}: {v.get('note') or why}", v.get("reproduced")))
                f["impact_before"] = f["impact"]; f["impact"] = new
            else: notes.append(f"{f['id']}: downgrade ignored (a verifier may lower, never raise)"); kind = "unclear"
        if f.get("outside_only") and kind not in ("confirmed", "downgrade"):  # nobody of ours saw it and no verifier confirmed it
            unverified.append(f); notes.append(f"{f['id']}: outside-only finding the verifier couldn't confirm ({kind}); left out of the findings"); continue
        f["verifier"] = kind
        if v.get("reproduced") in ("executed", "traced"): f["verifier_reproduced"] = v["reproduced"]
        final.append(f)
    for f in final:  # §5.56: a reviewer's own "executed" is a claim; only a verifier that reproduced it, or confirmed it, makes it "confirmed"
        mine = f.get("verified") == "executed"; theirs = f.get("verifier_reproduced") == "executed" or bool(f.get("measured")); ok = f.get("verifier") == "confirmed"  # a scripted check that ran is a measurement, not a claim
        f["confidence"] = "confirmed" if theirs or ok and (mine or f.get("votes", 1) >= 2) else "likely" if ok or mine or f.get("votes", 1) >= 2 else "possible"
        if f.get("verifier") == "unclear" and f["confidence"] == "confirmed" and not f.get("measured"): f["confidence"] = "likely"  # never above what the verifier could say (a measurement is not the verifier's to say)
    final.sort(key=lambda f: (IMP_RANK[f["impact"]], {"confirmed": 0, "likely": 1, "possible": 2}[f["confidence"]], f["file"], int(f.get("line") or 0)))
    for f in final: f["fix"] = fix_status(f)  # SC-37: never offer an empty fix, a no-op fix, or one with unbalanced brackets
    mark_origin(final)
    final = scrub(final); unverified = scrub(unverified)  # a verifier's note can quote a secret too: mask before anything is written
    lowered = [f for f in final if f["impact"] == NIT]  # a verifier lowered a Low to a Nit: it leaves the counted findings
    final = [f for f in final if f["impact"] != NIT]
    nits = list(T.get("nits") or []) + lowered
    write_jsonl(D / "nits.jsonl", nits)  # SC-79: listed, never counted; the eval still credits a planted bug found here (as an impact miss)
    write_jsonl(D / "findings.jsonl", final)
    write_verifier_log()
    (D / "findings.sarif").write_text(json.dumps(to_sarif(final), indent=1))
    cnt = {k: sum(1 for f in final if f["impact"] == k) for k in IMPACTS}
    why_degraded = list(T.get("degraded") or []) + ([f"{len(missing)} verdict(s) the {tier} tier requires never came back ({', '.join(missing[:8])}{' ...' if len(missing) > 8 else ''})"] if missing else [])
    md = ["# Curmudgeon merged findings", ""] + ([f"DEGRADED: {'; '.join(why_degraded)}", "(Copy that line as the teardown's first line, before the verdict.)", ""] if why_degraded else []) + [
          f"Reviewers: {T['reviewers']} (votes needed: {T['votes_needed']}; {tier} tier).",
          "Counts for the VERDICT (copy exactly): " + " · ".join(f"{k} {v}" for k, v in cnt.items()) + f" · total {len(final)}", "",
          "| ID | Impact | Confidence | Votes | Verifier | Where | Title |", "| --- | --- | --- | --- | --- | --- | --- |"]
    def where_(f):  # every place the merged reviewers cited, first the one the finding is filed under: a reader (and the teardown) sees them all
        first = f"{f['file']}:{f.get('line', '')}"; more = [x for x in (f.get("locations") or []) if x != first]
        return first + (" (also at " + ", ".join(more[:6]) + (" ..." if len(more) > 6 else "") + ")" if more else "")
    md += [f"| {f['id']} | {f['impact']} | {f['confidence']} | {f.get('votes', 1)}/{f.get('of', 1)} | {f.get('verifier', '-')} | {where_(f)} | {f['title'].replace('|', '/')} |" for f in final]
    cov = T.get("coverage") or {}
    md += ["", "Not reviewed (computed from the reviewers' coverage reports): " + (", ".join(cov.get("not_reviewed") or []) or "nothing") if cov.get("known")
           else "", "Not reviewed: unknown (no reviewer reported coverage); say so in the teardown." if not cov.get("known") else ""]
    if nits: md += ["", f"## Nits ({len(nits)}; listed, not counted, not verified, never blocking)"] + [f"- {cell_(f.get('file'))}:{f.get('line', '')} {cell_(f.get('title'))}" for f in nits[:30]] + ([f"- and {len(nits) - 30} more in .critic/nits.jsonl"] if len(nits) > 30 else [])
    sbx = T.get("sandbox") or []
    md += ["", "## Sandbox ledger (copy these lines; cite them as SB ids)", "| SB | Reviewer | Scenario | What happens | Result | How |", "| --- | --- | --- | --- | --- | --- |"] + \
          [f"| {x['id']} | {x['reviewer']} | {cell_(x['scenario'])} | {cell_(x['happens'])} | {cell_(x['result'])} | {x['how']} |" for x in sbx] if sbx else \
          ["", "## Sandbox ledger", "No reviewer recorded a sandbox line: write \"none recorded\" in the teardown, never invent one."]
    pre = [f for f in final if f.get("origin") == "pre-existing"]
    if pre: md += ["", f"## Pre-existing (already there before this change; still counted above): {len(pre)}"] + [f"- {f['id']} {f['impact']} {f['file']}:{f.get('line', '')}" for f in pre]
    nofix = [f for f in final if str(f.get("fix", "")).startswith(("none", "not offerable"))]
    if nofix: md += ["", "## Fixes not to offer (describe the problem; don't present these remediations as fixes)"] + [f"- {f['id']}: {f['fix']}" for f in nofix]
    try: stuck = [json.loads(x) for x in (D / "stuck.jsonl").read_text().splitlines() if x.strip()] if (D / "stuck.jsonl").is_file() and not (D / "stuck.jsonl").is_symlink() else []
    except (OSError, ValueError): stuck = []
    run_now = ledger().get("run"); stuck = [x for x in stuck if x.get("run") == run_now]
    if stuck: md += ["", "## Stuck (typed; never hidden: say in the teardown what couldn't be checked and why)"] + [f"- {x.get('role')} {x.get('agent_id', '')[:8]}: {x.get('type')} on {x.get('tool')} (round {x.get('round')})" for x in stuck]
    capped = [f for f in final if f.get("impact_capped_from")]
    if capped: md += ["", "## Capped at Medium (they rest on an inferred requirement, not a stated one; say so in the teardown)"] + [f"- {f['id']}: raised as {f['impact_capped_from']}; inferred from {str((f.get('requirement') or {}).get('why', ''))[:120]}" for f in capped]
    part = [f for f in final if f.get("fix") == "partial"]
    if part: md += ["", "## Partial fixes (label them partial in the teardown)"] + [f"- {f['id']}" for f in part]
    misnum = [r for r in T["retracted"] if "a wrong line number" in str(r.get("why"))]
    if misnum: md += ["", f"## Line numbers to check: {len(misnum)} retracted finding(s) quote code that is in the file, at another line",
                      "Still retracted (the quote check holds a quote to its cited line). Say so in the teardown's Not checked line: a reviewer read with numbering that was off."]
    for name, rows in (("Refuted by verification", refuted), ("Dropped (single vote, not executed)", T["dropped"]), ("Retracted (quote not found)", T["retracted"]),
                       ("Rejected (broke the contract)", T["rejected"]), ("Hidden by your rulings (fp on this exact finding)", T["suppressed"])):
        if rows: md += ["", f"## {name}"] + [f"- {r['finding'].get('id')} {r['finding'].get('file')}:{r['finding'].get('line', '')} {r['finding'].get('title')}: {r['why'] if isinstance(r['why'], str) else '; '.join(r['why'])}" for r in rows]
    if T.get("outside"):
        o = T["outside"]; theirs = [f for f in final if "outside" in (f.get("raised_by") or [])]
        md += ["", "## Outside reviewer", f"- {o['raised']} raised; {o['accepted']} passed the contract and quote checks ({o.get('lines_corrected', 0)} at a corrected line); {o['matched_ours']} matched our reviewers; "
               f"{o['only_outside']} only theirs, each verified blind. In the final list: " + (", ".join(f"{f['id']} {f['impact']}" for f in theirs) or "none") + "."]
    if T.get("ruling_committed"):
        md += ["", "## Not hidden: rulings from a ledger the repository tracks (.critic/ledger.json is committed, so its rulings could be anyone's; these findings stay in the counts above)"]
        md += [f"- {r['finding'].get('id')} {r['finding'].get('file')}:{r['finding'].get('line', '')} {r['finding'].get('title')}: {r['why']}" for r in T["ruling_committed"]]
        md += ["To apply your own rulings, stop tracking the ledger (your copy stays): git rm --cached .critic/ledger.json"]
    alike = [f for f in final if f.get("ruling_like")]
    if alike:
        md += ["", "## Same code as a finding you ruled a false positive (still counted above; your ruling covered another kind of finding)"]
        md += [f"- {f['id']} {f['impact']} {f['file']}:{f.get('line', '')} {f['title']}: like your ruling on {f['ruling_like']['ruling']} ({f['ruling_like']['why']}). Rule on this one with critic_ledger.py fp {f['id']} \"<why>\" if it is wrong too." for f in alike]
    looks = [f for f in final if f.get("memory_note")]
    if looks:
        md += ["", "## Looks like your past dismissals (still counted above; nothing is hidden)"]
        md += [f"- {f['id']} {f['impact']} {f['file']}:{f.get('line', '')} {f['title']}: like memory {f['memory_note']['memory']} "
               f"({f['memory_note']['dismissed']} earlier dismissals, reason: {f['memory_note']['reason']}). Close them on purpose with "
               f"`critic_ledger.py dismiss --like {f['memory_note']['memory']} \"<why>\"`, or keep them." for f in looks]
    if unverified: md += ["", "## Outside findings not verified (not counted above; run the verifier on their packets, then apply again)"] + \
                        [f"- {f['id']} {f['impact']} {f['file']}:{f.get('line', '')} {f['title'].replace('|', '/')}" for f in unverified]
    if notes: md += ["", "## Notes"] + [f"- {x}" for x in notes]
    (D / "counts.md").write_text("\n".join(redact_finding_text(x) for x in md) + "\n")
    led = pathlib.Path(__file__).resolve().parent / "critic_ledger.py"
    if (D / "ledger.json").exists():
        tmp = D / "findings-import.jsonl"; write_jsonl(tmp, final)
        env = dict(os.environ, CRITIC_ROOT=str(ROOT))
        imp = subprocess.run([sys.executable, str(led), "import", str(tmp)], cwd=ROOT, env=env)
        if imp.returncode != 0:
            print("critic_merge: the findings were written, but recording them in the ledger FAILED (see the message above); stable ids and history are not updated", file=sys.stderr)
            return 1
        try: known = json.loads((D / "ledger.json").read_text()).get("findings", {})
        except Exception: known = {}
        for r in refuted:
            fid = r["finding"].get("id")
            if fid in known and known[fid].get("status") == "open":
                subprocess.run([sys.executable, str(led), "status", fid, "refuted", "refuted by verification: " + r["why"][:200]], cwd=ROOT, env=env, capture_output=True)  # not the owner's wontfix: it opens again if a later run raises it
    print(f"final: {len(final)} finding(s) — " + ", ".join(f"{k} {v}" for k, v in cnt.items()) + f"; refuted {len(refuted)}")
    rev = revision_stamp(final)
    (D / "revision.json").write_text(json.dumps(rev, indent=1) + "\n")
    with open(D / "counts.md", "a", encoding="utf-8") as fh:
        fh.write(f"\nRevision reviewed: {rev['sha'] or 'not a git repository'}{' (with uncommitted changes)' if rev['dirty'] else ''}; cited files sha256 {rev['payload_sha256'][:16]}.\n")
    write_manifest(D)  # a sha256 of every output, so a later hand edit shows (critic_ledger.py integrity)
    print(f"wrote {D/'findings.jsonl'}, {D/'findings.sarif'}, {D/'counts.md'} (hashes in {D/'manifest.json'})")
    return 0

def show():
    for f in read_jsonl(D / "findings.jsonl"): print(f"{f['id']}\t{f['impact']}\t{f['confidence']}\t{f['file']}:{f.get('line', '')}\t{f['title']}")
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or any(x in ("-h", "--help") for x in a): print(__doc__); sys.exit(0)
    refuse_linked_state(ROOT)
    log_run(ROOT, "script", "critic_merge.py " + " ".join(a))
    if a[0] == "tally" and len(a) > 1: sys.exit(tally(a[1:]))
    if a[0] == "apply" and len(a) > 1: sys.exit(apply(a[1:]))
    if a[0] == "show": sys.exit(show())
    die("usage: tally REVIEW... | apply VERDICT... | show")
