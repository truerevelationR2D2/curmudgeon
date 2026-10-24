#!/usr/bin/env python3
"""Curmudgeon's state ledger: .critic/ledger.json (rendered to ledger.md). It keeps findings under stable ids, what
happened to each (new, known, fixed, regressed, acted on), decisions, false positives, learned dismissals, fix
claims, scores, fingerprints, rounds, restore points, gate overrides and run costs, between runs and sessions.

usage (run from the project root, or set CRITIC_ROOT):
  init | start review|full [--tier trivial|lite|full]   begin a run (round 1; records mode and tier)
  import FINDINGS.jsonl                  record merged findings by stable id: new, known (still there) or regressed
  add ID SCORE WHERE "summary" [--verified]   record one finding by hand (round 3 accepts only --verified)
  status ID open|wontfix "note"          update a finding
  claim ID targeted|no-new-defect|behaviour-unchanged "evidence id or command"   one of the three fix claims
  fixed ID "how verified" [--untested]   mark fixed: needs all three claims (or --untested, which is recorded as such)
  defer ID impossible|conflicts|worse "note"   defer, only for one of the three valid reasons
  dismiss ID false-positive|out-of-scope|redundant|intended|preference "why"
                                         the owner dismisses a finding; 3 similar dismissals with the same reason
                                         become a learned memory that NOTES look-alike findings in later reviews
  fp ID "why"                            this exact finding (by stable id) is a false positive
  memories [--retire N]                  list learned memories (retire one by number)
  examples                               print up to 5 recent false positives as few-shot examples for reviewers
  acted                                  for findings open last run: check whether the quoted code is gone (acted on)
  decision "text" [SOURCE] | override "what" "who" "why"   recorded choices; overrides can't be by "author"
  score NAME VALUE MAX | cost SECONDS [NOTE] | tokens [--all] | integrity   (tokens: what each agent role cost this run; integrity: outputs edited since the last apply)
  stamp [--add] PATH... | stale | round [--reset]   (--add keeps earlier stamps: use it for /curmudgeon:fix iterate)
  gate on|async|off                      turn the stop checks on or off (the guard blocks editing these files by hand)
  memories --hit N                       record that memory N noted a finding (keeps it from retiring)
  spotcheck [--n 3]                      pick a few random Medium+ findings and one refutation for the owner to judge
  spotcheck answer ID real|wrong|unsure  record the owner's answer; spotcheck stats shows precision from their answers
  dismiss --like N "why"                 dismiss, on purpose, every finding of the last review that memory N noted
                                         (memories never hide findings; they only note open Medium/Low ones)
  restore save [--ids ID,ID] PATH... | restore apply   (secret-looking keys are redacted in restore copies; rollback
                                         keeps the live key lines; --ids records which findings the change is for)
  show | check                           check exits 1 if a Critical/High is open"""
import hashlib, json, os, pathlib, re, shutil, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import log_run, norm_code, read_jsonl, refuse_linked_state, tokens

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT", os.getcwd())).resolve(); D = ROOT / ".critic"; F = D / "ledger.json"
SCORES = ("Critical", "High", "Medium", "Low"); STATES = ("open", "fixed", "deferred", "wontfix", "dismissed")
REASONS = ("impossible", "conflicts", "worse"); DISMISS = ("false-positive", "out-of-scope", "redundant", "intended", "preference")
CLAIMS = ("targeted", "no-new-defect", "behaviour-unchanged")
try:  # the same provider key shapes the secret scan uses, so a restore point never stores a key the scan would flag
    from scan_secrets import PROVIDERS as _P
    SECRET = re.compile("|".join((f"(?i:{x[4:]})" if x.startswith("(?i)") else f"(?:{x})") for rid, _s, x, _l in _P if rid not in ("private-key", "gcp-service-account")) + r"|\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}")
except Exception:
    SECRET = re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}")
HARD = re.compile(r"secur|xss|inject|secret|auth|data.?loss|corrupt|race|crash|money|refund|payment|privacy|leak", re.I)
BLANK = {"version": 4, "mode": "", "tier": "", "round": 0, "run": 0, "findings": {}, "decisions": [], "overrides": [], "false_positives": [],
         "dismissals": [], "memories": [], "scores": [], "costs": [], "stamps": {}, "restore": [], "spotchecks": [], "spotcheck_pending": []}
MEMORY_TTL_DAYS = 90

def die(msg, code=2): print(f"critic_ledger: {msg}", file=sys.stderr); sys.exit(code)

def load():
    if not F.exists(): return json.loads(json.dumps(BLANK))
    try: L = json.loads(F.read_text(encoding="utf-8"))
    except Exception as e: die(f"ledger is unreadable ({e}); nothing was changed. Fix or move {F}, then run init.")
    if not isinstance(L, dict): die(f"ledger has the wrong shape; nothing was changed. Move {F}, then run init.")
    for k, v in BLANK.items(): L.setdefault(k, json.loads(json.dumps(v)))
    if isinstance(L["findings"], list):  # an older or hand-made ledger: key the rows by their id
        L["findings"] = {str(x.get("id")): x for x in L["findings"] if isinstance(x, dict) and x.get("id")}
    if not isinstance(L["findings"], dict): die(f"ledger 'findings' has the wrong shape; nothing was changed. Fix or move {F}, then run init.")
    for k in ("decisions", "overrides", "false_positives", "dismissals", "memories", "scores", "costs", "restore", "spotchecks", "spotcheck_pending"):
        if not isinstance(L[k], list): die(f"ledger '{k}' has the wrong shape; nothing was changed. Fix or move {F}, then run init.")
    for i, x in list(L["findings"].items()):
        if not isinstance(x, dict): del L["findings"][i]; continue
        sc = str(x.get("score", "Medium")).title(); x["score"] = sc if sc in SCORES else "Medium"
        st = str(x.get("status", "open")).lower(); x["status"] = st if st in STATES else "open"
        for k in ("where", "summary", "quote", "category"): x.setdefault(k, "")
        x.setdefault("claims", {}); x.setdefault("history", [])
    return L

def cell(s): return str(s).replace("|", "\\|").replace("\n", " ")

def render(L):
    order = lambda kv: (["open", "regressed", "deferred", "fixed", "wontfix", "dismissed"].index(kv[1]["status"]) if kv[1]["status"] in ("open", "regressed", "deferred", "fixed", "wontfix", "dismissed") else 9, SCORES.index(kv[1]["score"]), kv[0])
    rows = [f"| {cell(i)} | {f['score']} | {f['status']}{' (regressed)' if f.get('regressed') else ''} | {cell(f['where'])} | {cell(f['summary'])} | {cell(f.get('note', ''))} |" for i, f in sorted(L["findings"].items(), key=order)]
    acted = [f for f in L["findings"].values() if "acted_on" in f]
    rate = f"{sum(1 for f in acted if f['acted_on'])} of {len(acted)} acted on" if acted else "no data yet"
    md = ["# Curmudgeon ledger", f"Updated {time.strftime('%Y-%m-%d %H:%M')}. Run {L['run']}. Mode: {L['mode'] or 'none'}. Tier: {L['tier'] or 'n/a'}. Review round: {L['round']} of 3.", "",
          "## Findings", "| ID | Impact | Status | Where | Finding | Note |", "| --- | --- | --- | --- | --- | --- |", *rows,
          "", f"## Acted-on rate: {rate}",
          "", "## Decisions to respect", *[f"- {d['text']} ({d.get('source', '')})" for d in L["decisions"]],
          "", "## Gate overrides", *[f"- {o['at']}: {o['what']} — by {o['who']}: {o['why']}" for o in L["overrides"]],
          "", "## Known false positives", *[f"- {x.get('id', x.get('rule', ''))} {x.get('where', '')}: {x['why']}" for x in L["false_positives"]],
          "", "## Spot-checks (the owner's own answers)", spot_stats(L),
          "", "## Learned memories (from dismissals; they add notes, never hide findings)", *[f"- {i + 1}. [{m['reason']}] {m['pattern']}{' (retired)' if m.get('retired') else ''} — hits {m.get('hits', 0)}" for i, m in enumerate(L["memories"])],
          "", "## Scores", *[f"- {x['at']} {x['name']}: {x['value']:g}/{x['max']:g}" for x in L["scores"]],
          "", "## Restore points", *[f"- {r['at']}: {r['dir']} ({len(r['files'])} files)" for r in L["restore"][-5:]]]
    return "\n".join(md) + "\n"

def save(L):
    md = render(L); D.mkdir(parents=True, exist_ok=True)
    for path, body in ((F, json.dumps(L, indent=1, ensure_ascii=False)), (D / "ledger.md", md)):
        tmp = path.with_name(path.name + ".tmp"); tmp.write_text(body, encoding="utf-8"); os.replace(tmp, path)

def rel(p):
    p = pathlib.Path(p).resolve()
    try: return str(p.relative_to(ROOT))
    except ValueError: die(f"{p} is outside the project root {ROOT}")

def need(rest, n, usage):
    if len(rest) < n: die("usage: " + usage)

def archive_reviews(L, label):
    """A new run or round starts with no reviews: earlier ones move to .critic/history/<label>/reviews/, and
    started_at is reset, so the tally refuses any review file written before it."""
    rv = D / "reviews"
    if rv.is_dir() and not rv.is_symlink():
        olds = [p for p in rv.iterdir() if p.is_file() and not p.is_symlink()]
        if olds:
            dest, k = D / "history" / label / "reviews", 2
            while dest.exists():  # never overwrite an earlier archive (round --reset can repeat a label)
                dest = D / "history" / f"{label}-{k}" / "reviews"; k += 1
            dest.mkdir(parents=True)
            for p in olds: os.replace(p, dest / p.name)
    L["started_at"] = time.time()

def finding(L, fid):
    if fid not in L["findings"]: die(f"no finding {fid}")
    return L["findings"][fid]

def quote_present(f):
    q = norm_code(f.get("quote")); file = (f.get("where") or "").rsplit(":", 1)[0]
    if not q or not file: return None
    if "[redacted]" in str(f.get("quote")): return None  # a masked quote is not the code: it can't show whether the code is gone
    try: return q in norm_code((ROOT / file).read_text(encoding="utf-8", errors="replace"))
    except OSError: return False

def spot_stats(L):
    f = [x for x in L.get("spotchecks", []) if x.get("kind") == "finding" and x.get("answer") in ("real", "wrong")]
    r = [x for x in L.get("spotchecks", []) if x.get("kind") == "refutation" and x.get("answer") in ("real", "wrong")]
    a = f"findings judged {len(f)}: {sum(1 for x in f if x['answer'] == 'real')} real" + (f" (precision {sum(1 for x in f if x['answer'] == 'real') / len(f):.0%})" if f else "")
    drops = [x for x in r if x.get("ref_kind") != "downgraded"]; lows = [x for x in r if x.get("ref_kind") == "downgraded"]
    b = (f"; verifier decisions judged {len(r)}: {sum(1 for x in drops if x['answer'] == 'real')} of {len(drops)} drops removed a real bug, "
         f"{sum(1 for x in lows if x['answer'] == 'real')} of {len(lows)} downgrades lowered a real bug's impact") if r else "; no verifier decisions judged yet"
    return a + b

def read_rows(p):
    try: return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError): return []

def learn(L, d):
    """3 dismissals with the same reason and overlapping words become a memory. Dismissals of Critical or High findings
    never count, so a memory can't be built from serious findings and then hide smaller ones of the same kind."""
    same = [x for x in L["dismissals"] if x["reason"] == d["reason"] and not x.get("used") and not x.get("hard")]
    group = [x for x in same if len(tokens(x["text"]) & tokens(d["text"])) >= max(2, len(tokens(d["text"])) // 3)]
    if len(group) >= 3:
        common = set.intersection(*[tokens(x["text"]) for x in group])
        if len(common) >= 2:
            files = {x["file"] for x in group}; glob = files.pop() if len(files) == 1 else "*"
            L["memories"].append({"reason": d["reason"], "pattern": " ".join(sorted(common)), "file_glob": glob, "hits": 0, "count": len(group), "made": time.strftime("%Y-%m-%d"), "last_used": time.strftime("%Y-%m-%d")})
            for x in group: x["used"] = True
            return f"learned a memory from 3 '{d['reason']}' dismissals: {' '.join(sorted(common))}"
    return None

def main(a):
    if not a or any(x in ("-h", "--help") for x in a): print(__doc__); return 0  # help never changes the ledger
    cmd, rest = a[0], a[1:]; L = load(); msg = "ok"
    if cmd not in ("show", "check", "stale", "tokens", "integrity"): refuse_linked_state(ROOT); log_run(ROOT, "script", "critic_ledger.py " + " ".join(a))
    if cmd == "init": pass
    elif cmd == "start":
        need(rest, 1, "start review|full [--tier trivial|lite|full]")
        if rest[0] not in ("review", "full"): die("start review|full")
        tier = rest[rest.index("--tier") + 1] if "--tier" in rest and rest.index("--tier") + 1 < len(rest) else ""
        if tier and tier not in ("trivial", "lite", "full"): die("tier must be trivial, lite or full")
        L["mode"], L["round"], L["tier"] = rest[0], 1, tier; L["run"] += 1
        for m in L["memories"]:  # retire memories unused for MEMORY_TTL_DAYS
            try:
                if not m.get("retired") and (time.time() - time.mktime(time.strptime(m.get("last_used", m.get("made")), "%Y-%m-%d"))) > MEMORY_TTL_DAYS * 86400: m["retired"] = True
            except Exception: pass
        archive_reviews(L, f"run-{L['run'] - 1}")
        sc = D / "scratch"  # the last run's agent scratch folders move aside too: a new run's agents start empty
        if sc.is_dir() and not sc.is_symlink() and any(sc.iterdir()):
            dest = D / "history" / f"run-{L['run'] - 1}" / "scratch"; k = 2
            while dest.exists(): dest = D / "history" / f"run-{L['run'] - 1}-{k}" / "scratch"; k += 1
            dest.parent.mkdir(parents=True, exist_ok=True); os.replace(sc, dest)
        msg = f"{rest[0]} run {L['run']} started{' (' + tier + ' tier)' if tier else ''}, round 1 of 3"
    elif cmd == "import":
        need(rest, 1, "import FINDINGS.jsonl")
        try: rows = read_jsonl(rest[0])
        except ValueError as e: die(str(e))
        new = known = regressed = held = 0
        for r in rows:
            fid = r.get("id")
            if not fid: continue
            ex = L["findings"].get(fid)
            if ex is None and L["round"] >= 3 and r.get("confidence") != "confirmed":
                held += 1; print(f"round 3 is verify-only: not recording new unconfirmed finding {fid} ({r.get('title', '')[:60]})", file=sys.stderr); continue
            base = {"score": str(r.get("impact", "Medium")).title(), "where": f"{r.get('file', '')}:{r.get('line', '')}", "summary": r.get("title", ""),
                    "quote": r.get("quote", ""), "category": r.get("category", ""), "confidence": r.get("confidence", ""), "votes": r.get("votes", 1)}
            if ex is None:
                L["findings"][fid] = dict(base, status="open", first_run=L["run"], claims={}, history=[f"run {L['run']}: new"]); new += 1
            elif ex["status"] == "fixed":
                ex.update(base, status="open", regressed=True); ex["history"].append(f"run {L['run']}: regressed"); regressed += 1
            elif ex["status"] in ("dismissed", "wontfix"):
                ex["history"].append(f"run {L['run']}: raised again while {ex['status']}")
            else:
                ex.update(base); ex["history"].append(f"run {L['run']}: still there"); known += 1
        msg = f"imported {len(rows)}: {new} new, {known} known, {regressed} regressed" + (f", {held} held back (round 3)" if held else "")
    elif cmd == "add":
        need(rest, 4, "add ID Critical|High|Medium|Low WHERE \"summary\" [--verified]")
        if L["round"] >= 3 and "--verified" not in rest: die("round 3 is verify-only: new findings need --verified (an executed failing case)")
        sc = rest[1].title()
        if sc not in SCORES: die("score must be Critical, High, Medium or Low")
        L["findings"][rest[0]] = {"score": sc, "where": rest[2], "summary": rest[3], "status": "open", "claims": {}, "history": [f"run {L['run']}: added"], "quote": "", "category": ""}
    elif cmd == "status":
        need(rest, 2, "status ID open|wontfix \"note\"")
        f = finding(L, rest[0])
        if rest[1] == "deferred": die("use: defer ID impossible|conflicts|worse \"note\"")
        if rest[1] == "fixed": die("use: fixed ID \"how verified\" (needs the three claims)")
        if rest[1] == "dismissed": die("use: dismiss ID REASON \"why\"")
        if rest[1] not in ("open", "wontfix"): die("status must be open or wontfix")
        f.update(status=rest[1], note=rest[2] if len(rest) > 2 else "")
    elif cmd == "claim":
        need(rest, 3, "claim ID targeted|no-new-defect|behaviour-unchanged \"evidence\"")
        f = finding(L, rest[0])
        if rest[1] not in CLAIMS: die("claim must be targeted, no-new-defect or behaviour-unchanged")
        if not rest[2].strip(): die("a claim needs evidence (an evidence id, a test name or the command that was run)")
        f["claims"][rest[1]] = rest[2]; msg = f"{rest[0]}: {len(f['claims'])} of 3 claims"
    elif cmd == "fixed":
        need(rest, 2, "fixed ID \"how verified\" [--untested]")
        f = finding(L, rest[0]); missing = [c for c in CLAIMS if c not in f["claims"]]
        if missing and "--untested" not in rest: die(f"not fixed yet: missing claim(s) {', '.join(missing)}. Run the checks, or pass --untested to record it as untested")
        f.update(status="fixed", note=rest[1] + (" [untested: " + ", ".join(missing) + "]" if missing else ""), fixed_run=L["run"], regressed=False)
        f["history"].append(f"run {L['run']}: fixed{' (untested)' if missing else ''}")
    elif cmd == "defer":
        need(rest, 3, "defer ID impossible|conflicts|worse \"note\"")
        f = finding(L, rest[0])
        if rest[1] not in REASONS: die("the only valid reasons are: impossible, conflicts, worse ('out of scope', 'pre-existing' and 'too complex' don't count)")
        if not rest[2].strip(): die("a deferral needs a note that shows the reason")
        f.update(status="deferred", reason=rest[1], note=f"{rest[1]}: {rest[2]}")
    elif cmd == "dismiss" and rest[:1] == ["--like"]:
        # the owner closes, on purpose, every finding of the last review that a memory noted; nothing was hidden before this
        need(rest, 3, "dismiss --like N \"why\"")
        try: n = int(rest[1]); mem = L["memories"][n - 1]
        except (ValueError, IndexError): die(f"no memory {rest[1]}; see: memories")
        done, skipped = [], []
        for row in read_rows(D / "findings.jsonl"):
            fid = row.get("id")
            if (row.get("memory_note") or {}).get("memory") != n or fid not in L["findings"]: continue
            if L["findings"][fid].get("score") not in ("Medium", "Low"): skipped.append(f"{fid} ({L['findings'][fid].get('score')})"); continue  # the ledger's own score decides, as check does
            if L["findings"][fid].get("status") != "open": skipped.append(f"{fid} ({L['findings'][fid].get('status')})"); continue  # never overwrite fixed/wontfix: regressions must still show
            L["findings"][fid].update(status="dismissed", note=f"{mem['reason']} (like memory {n}): {rest[2]}"); done.append(fid)
            L["dismissals"].append({"id": fid, "reason": mem["reason"], "why": rest[2], "file": L["findings"][fid]["where"].rsplit(":", 1)[0], "text": "", "at": time.strftime("%Y-%m-%d"), "used": True, "via_memory": n})
        mem["hits"] = mem.get("hits", 0) + len(done); mem["last_used"] = time.strftime("%Y-%m-%d")
        msg = f"dismissed {len(done)} open Medium/Low finding(s) like memory {n}: {', '.join(done) or 'none'}" + (f"; left alone (High/Critical, or not open): {', '.join(skipped)}" if skipped else "")
    elif cmd == "dismiss":
        need(rest, 3, "dismiss ID false-positive|out-of-scope|redundant|intended|preference \"why\"")
        f = finding(L, rest[0])
        if rest[1] not in DISMISS: die("reason must be one of: " + ", ".join(DISMISS))
        f.update(status="dismissed", note=f"{rest[1]}: {rest[2]}")
        d = {"id": rest[0], "reason": rest[1], "why": rest[2], "file": f["where"].rsplit(":", 1)[0], "text": f"{f.get('category', '')} {f['summary']}", "at": time.strftime("%Y-%m-%d")}
        hard = f["score"] in ("Critical", "High")
        L["dismissals"].append(dict(d, hard=bool(hard)))
        if rest[1] == "false-positive": L["false_positives"].append({"id": rest[0], "where": f["where"], "why": rest[2]})
        if not hard:
            m = learn(L, d)
            if m: msg = m
        else: msg = "dismissed (a Critical or High finding never becomes a learned memory)"
    elif cmd == "fp":
        need(rest, 2, "fp ID \"why\" (or legacy: fp RULE_ID WHERE \"why\" for a scripted row)")
        if len(rest) >= 3: L["false_positives"].append({"rule": rest[0], "where": rest[1], "why": rest[2]})
        else: L["false_positives"].append({"id": rest[0], "where": L["findings"].get(rest[0], {}).get("where", ""), "why": rest[1]})
    elif cmd == "spotcheck":
        # a few random findings (and one refutation) for the owner to judge: real accuracy from their own projects
        if rest[:1] == ["answer"]:
            need(rest, 3, "spotcheck answer ID real|wrong|unsure [\"note\"]")
            if rest[2] not in ("real", "wrong", "unsure"): die("answer must be real, wrong or unsure")
            pend = {x["id"]: x for x in L["spotcheck_pending"]}
            if rest[1] not in pend: die(f"{rest[1]} is not in the current spot-check; run: spotcheck")
            L["spotchecks"].append(dict(pend.pop(rest[1]), answer=rest[2], note=rest[3] if len(rest) > 3 else "", run=L["run"], at=time.strftime("%Y-%m-%d")))
            L["spotcheck_pending"] = list(pend.values()); msg = f"recorded {rest[1]}: {rest[2]}. " + spot_stats(L)
        elif rest[:1] == ["stats"]:
            print(spot_stats(L)); return 0
        else:
            import random
            n = 3
            if rest[:1] == ["--n"] and len(rest) > 1 and rest[1].isdigit(): n = max(1, min(10, int(rest[1])))
            rows = [r for r in read_rows(D / "findings.jsonl") if r.get("impact") in ("Critical", "High", "Medium")]
            refs = [r for r in read_rows(D / "refutations.jsonl") if isinstance(r, dict) and r.get("run") == L["run"] and r.get("kind") in ("refuted", "downgraded")]
            ref = random.choice(refs) if refs else None
            # one item per id: a downgraded finding is still in findings.jsonl, so it is never also sampled as a finding,
            # and the owner's one answer always means one thing
            rows = [r for r in rows if not ref or r.get("id") != ref.get("id")]
            pick = [{"kind": "finding", "id": r["id"], "impact": r["impact"], "where": f"{r.get('file')}:{r.get('line', '')}", "title": r.get("title", "")} for r in random.sample(rows, min(n, len(rows)))]
            if ref:
                r = ref
                pick.append({"kind": "refutation", "ref_kind": "downgraded" if r.get("kind") == "downgraded" else "refuted", "id": r["id"], "impact": r.get("impact"),
                             "where": f"{r.get('file')}:{r.get('line', '')}", "title": r.get("title", ""),
                             "why": ("downgraded " if r.get("kind") == "downgraded" else "dropped: ") + str(r.get("why", ""))})
            L["spotcheck_pending"] = pick
            md = ["# Spot-check", "", "Judge each one in a few seconds. For a finding: is it a real problem (real) or not (wrong)? For a refutation: was the",
                  "verifier wrong to drop or lower it, meaning the finding was real at its first impact (real), or right (wrong)? Unsure is fine.", ""]
            md += [f"{i}. **{x['id']}** ({x['kind']}, {x['impact']}) {x['where']}: {x['title']}" + (f"\n   Verifier's reason: {x['why'][:300]}" if x["kind"] == "refutation" else "") for i, x in enumerate(pick, 1)]
            md += ["", "Record each with: `critic_ledger.py spotcheck answer <ID> real|wrong|unsure`"]
            (D / "spotcheck.md").write_text("\n".join(md) + "\n", encoding="utf-8")
            msg = f"{len(pick)} item(s) to spot-check in .critic/spotcheck.md" if pick else "nothing to spot-check (no Medium or worse findings and no refutations this run)"
    elif cmd == "memories":
        if rest[:1] == ["--hit"]:
            need(rest, 2, "memories --hit N")
            try: m = L["memories"][int(rest[1]) - 1]; m["hits"] = m.get("hits", 0) + 1; m["last_used"] = time.strftime("%Y-%m-%d"); msg = "ok"
            except (ValueError, IndexError): die("no such memory")
        elif rest[:1] == ["--retire"]:
            need(rest, 2, "memories --retire N")
            try: L["memories"][int(rest[1]) - 1]["retired"] = True; msg = f"memory {rest[1]} retired"
            except (ValueError, IndexError): die("no such memory")
        else:
            for i, m in enumerate(L["memories"], 1): print(f"{i}. [{m['reason']}] {m['pattern']} in {m['file_glob']} — hits {m.get('hits', 0)}{' (retired)' if m.get('retired') else ''}")
            return 0
    elif cmd == "examples":
        fps = L["false_positives"][-5:]
        for x in fps: print(f"- NOT a finding: {L['findings'].get(x.get('id', ''), {}).get('summary', x.get('rule', ''))} at {x.get('where', '')} — {x['why']}")
        if not fps: print("no recorded false positives yet")
        return 0
    elif cmd == "acted":
        checked = 0
        for fid, f in L["findings"].items():
            if f.get("first_run") == L["run"]: continue  # found this run: too early to say it was ignored
            if f["status"] in ("open", "fixed") and f.get("quote"):
                p = quote_present(f)
                if p is None: continue
                f["acted_on"] = not p; checked += 1
        save(L); print(f"checked {checked} finding(s); see the acted-on rate in ledger.md"); return 0
    elif cmd == "gate":
        need(rest, 1, "gate on|async|off")
        D.mkdir(parents=True, exist_ok=True)
        if rest[0] == "on": (D / "gate").write_text(""); msg = "stop gate on"
        elif rest[0] == "async": (D / "gate-async").write_text(""); msg = "background stop check on"
        elif rest[0] == "off":
            for n_ in ("gate", "gate-async", "gate-count"): (D / n_).unlink(missing_ok=True)
            msg = "stop checks off"
        else: die("gate on|async|off")
        print(msg); return 0
    elif cmd == "decision":
        need(rest, 1, "decision \"text\" [SOURCE]"); L["decisions"].append({"text": rest[0], "source": rest[1] if len(rest) > 1 else ""})
    elif cmd == "override":
        need(rest, 3, "override \"what\" \"who\" \"why\"")
        if rest[1].strip().lower() in ("author", "claude", "critic", "curmudgeon", "self"): die("an override must come from the owner, not the author")
        L["overrides"].append({"what": rest[0], "who": rest[1], "why": rest[2], "at": time.strftime("%Y-%m-%d %H:%M")})
    elif cmd == "score":
        need(rest, 3, "score NAME VALUE MAX")
        try: v, m = float(rest[1]), float(rest[2])
        except ValueError: die("VALUE and MAX must be numbers")
        prev = [x for x in L["scores"] if x["name"] == rest[0]]
        L["scores"].append({"name": rest[0], "value": v, "max": m, "at": time.strftime("%Y-%m-%d %H:%M")})
        msg = f"{rest[0]}: " + (f"{prev[-1]['value']:g}/{prev[-1]['max']:g} → " if prev else "") + f"{v:g}/{m:g}"
    elif cmd == "integrity":  # SC-72: outputs edited since the last apply (detectable, not impossible: see write_manifest)
        from critic_findings import check_manifest
        res = check_manifest(D)
        if res is None: print("integrity: no manifest yet (it is written at the end of each critic_merge.py apply)"); return 0
        if not res: print("integrity: every output matches the hashes recorded at the last apply"); return 0
        for name, what in res: print(f"integrity: .critic/{name} {what} since the last apply")
        return 1
    elif cmd == "tokens":  # what this run's agents cost, from .critic/cost.jsonl (written by the record_cost hook)
        rows = []
        cf = D / "cost.jsonl"
        if cf.is_file() and not cf.is_symlink():
            for line in cf.read_text(encoding="utf-8", errors="replace").splitlines():
                try: r_ = json.loads(line)
                except ValueError: continue
                if rest[:1] == ["--all"] or r_.get("run") == L["run"]: rows.append(r_)
        if not rows: print("tokens: unavailable (no agent costs recorded for this run; they need Claude Code's SubagentStop transcript)"); return 0
        F = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
        by = {}
        for r_ in rows:
            b_ = by.setdefault(r_.get("role", "unknown"), dict.fromkeys(F, 0) | {"agents": 0, "requests": 0, "unavailable": 0})
            b_["agents"] += 1
            if r_.get("unavailable"): b_["unavailable"] += 1; continue
            b_["requests"] += r_.get("requests", 0)
            for k in F: b_[k] += r_.get(k, 0)
        print("| role | agents | requests | input | cache write | cache read | output |"); print("| --- | --- | --- | --- | --- | --- | --- |")
        tot = dict.fromkeys(F, 0)
        for role, b_ in sorted(by.items()):
            print(f"| {role} | {b_['agents']}" + (f" ({b_['unavailable']} unavailable)" if b_["unavailable"] else "") + f" | {b_['requests']} | " + " | ".join(f"{b_[k]:,}" for k in F) + " |")
            for k in F: tot[k] += b_[k]
        print("| total | | | " + " | ".join(f"{tot[k]:,}" for k in F) + " |")
        return 0
    elif cmd == "cost":
        need(rest, 1, "cost SECONDS [NOTE]")
        try: L["costs"].append({"run": L["run"], "seconds": float(rest[0]), "note": rest[1] if len(rest) > 1 else ""})
        except ValueError: die("SECONDS must be a number")
    elif cmd == "stamp":
        need(rest, 1, "stamp [--add] PATH...")
        add = rest[0] == "--add"; rest = rest[1:] if add else rest
        need(rest, 1, "stamp [--add] PATH...")
        new = dict(L["stamps"]) if add else {}
        for a_ in rest:
            p = pathlib.Path(a_)
            if not p.exists(): die(f"{a_} does not exist; nothing was stamped")
            files = [p] if p.is_file() else [x for x in p.rglob("*") if x.is_file() and not ({".critic", ".git", "node_modules", "__pycache__"} & set(x.parts))]
            for q in files: new[rel(q)] = hashlib.sha256(q.read_bytes()).hexdigest()[:16]
        L["stamps"] = new; msg = f"stamped {len(new)} file(s){' in total' if add else ''}"
    elif cmd == "stale":
        ch = [k for k, h in L["stamps"].items() if not (ROOT / k).exists() or hashlib.sha256((ROOT / k).read_bytes()).hexdigest()[:16] != h]
        print("\n".join(ch) if ch else ("nothing changed since the last stamp" if L["stamps"] else "nothing stamped yet")); return 1 if ch else 0
    elif cmd == "round":
        if rest[:1] == ["--reset"]: L["round"] = 0; msg = "round reset"
        else:
            archive_reviews(L, f"run-{L['run']}-round-{L['round']}")
            # convergence (SC-36, after code-improver's detectors; our own rules): escalate instead of looping
            openf = {k: v for k, v in L["findings"].items() if v.get("status") in ("open", "regressed")}
            ch = sum(1 for v in openf.values() if v.get("score") in ("Critical", "High"))
            snaps = L.setdefault("round_snapshots", {}).setdefault(str(L["run"]), [])
            snaps.append({"round": L["round"], "open": sorted(openf), "critical_high": ch})
            esc = []
            esc += [f"{k} was marked fixed twice and is open again" for k, v in openf.items() if sum("fixed" in h for h in v.get("history", [])) >= 2]
            if len(snaps) >= 3: esc += [f"{k} has stayed open for 3 rounds" for k in sorted(set.intersection(*[set(x["open"]) for x in snaps[-3:]]))]
            if len(snaps) >= 2 and snaps[-1]["critical_high"] and snaps[-1]["critical_high"] >= snaps[-2]["critical_high"]:
                esc.append(f"open Critical+High did not fall ({snaps[-2]['critical_high']} -> {snaps[-1]['critical_high']})")
            L["round"] += 1; save(L)
            for e in esc: print(f"ESCALATE to the owner: {e}")
            print(f"review round {L['round']} of 3" + (" (verify-only: no new findings without an executed case)" if L["round"] == 3 else ""))
            if esc: return 3
            return 1 if L["round"] > 3 else 0
    elif cmd == "restore":
        need(rest, 1, "restore save PATH... | restore apply")
        if rest[0] == "save":
            ids = []
            if len(rest) > 2 and rest[1] == "--ids": ids = [x for x in rest[2].split(",") if x]; rest = [rest[0]] + rest[3:]
            need(rest, 2, "restore save [--ids ID,ID] PATH...")
            # Exact copies, like git stash: a restore point that rewrites or redacts lines can't be trusted to put code back
            # (every redaction scheme we tried broke rollback in some case). The keys in them are no more exposed than
            # the live files they copy: the folder is private to the user (0700) and git-ignored, and no report reads it.
            base = D / "restore"; base.mkdir(parents=True, exist_ok=True)
            try: os.chmod(base, 0o700)
            except OSError: pass
            gi = base / ".gitignore"
            if not gi.exists(): gi.write_text("# Curmudgeon restore points: exact copies of your files, possibly with keys. Never commit.\n*\n", encoding="utf-8")
            d = base / time.strftime("%Y%m%d-%H%M%S"); files = []
            for a_ in rest[1:]:
                p = pathlib.Path(a_)
                if not p.is_file(): die(f"{a_} is not a file; nothing was saved")
                r = rel(p); (d / r).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, d / r); files.append(r)
            if any(SECRET.search((d / r).read_text(encoding="utf-8", errors="replace")) for r in files):
                print("warning: a saved file holds a secret-looking key. The restore copy is exact (so rollback is exact), private and git-ignored. Rotate the key: it has already shipped.", file=sys.stderr)
            L["restore"].append({"at": time.strftime("%Y-%m-%d %H:%M"), "dir": str(d.relative_to(ROOT)), "files": files, "ids": ids}); msg = f"saved {len(files)} file(s) to {d.relative_to(ROOT)}"
        elif rest[0] == "apply":
            if not L["restore"]: die("no restore point recorded")
            r = L["restore"][-1]; manual = []
            for f_ in r["files"]:
                src = ROOT / r["dir"] / f_
                if (r.get("redacted") or {}).get(f_):
                    manual.append(f_); continue  # an older, redacted restore point: never write a placeholder over live code
                shutil.copy2(src, ROOT / f_)
            for fid in r.get("ids", []):
                if fid in L["findings"]: L["findings"][fid].update(status="open", note="rolled back"); L["findings"][fid]["history"].append(f"run {L['run']}: rolled back")
            msg = f"restored {len(r['files']) - len(manual)} file(s) from {r['dir']}" + (f"; reopened {', '.join(r['ids'])}" if r.get("ids") else "")
            if manual: msg += f"; NOT restored (saved by an older version with keys redacted): {', '.join(manual)}. Restore these from version control."
        else: die("restore save PATH... | restore apply")
    elif cmd == "show":
        for i, f in L["findings"].items():
            if f["status"] in ("open", "deferred"): print(f"{i}\t{f['score']}\t{f['status']}\t{f['where']}\t{f['summary']}")
        return 0
    elif cmd == "check":
        bad = [i for i, f in L["findings"].items() if f["status"] == "open" and f["score"] in ("Critical", "High")]
        dfr = [i for i, f in L["findings"].items() if f["status"] == "deferred" and f["score"] in ("Critical", "High")]
        print("open Critical/High: " + (", ".join(bad) or "none") + ("; deferred: " + ", ".join(dfr) if dfr else "")); return 1 if bad else 0
    else: die(f"unknown command {cmd}; see --help")
    save(L); print(msg); return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
