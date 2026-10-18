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
                                         become a learned memory (never applied to Critical/High security or correctness)
  fp ID "why"                            this exact finding (by stable id) is a false positive
  memories [--retire N]                  list learned memories (retire one by number)
  examples                               print up to 5 recent false positives as few-shot examples for reviewers
  acted                                  for findings open last run: check whether the quoted code is gone (acted on)
  decision "text" [SOURCE] | override "what" "who" "why"   recorded choices; overrides can't be by "author"
  score NAME VALUE MAX | cost SECONDS [NOTE]
  stamp [--add] PATH... | stale | round [--reset]   (--add keeps earlier stamps: use it for /curmudgeon:iterate)
  gate on|async|off                      turn the stop checks on or off (the guard blocks editing these files by hand)
  memories --hit N                       record that memory N suppressed a finding (keeps it from retiring)
  restore save [--ids ID,ID] PATH... | restore apply   (secret-looking keys are redacted in restore copies; rollback
                                         keeps the live key lines; --ids records which findings the change is for)
  show | check                           check exits 1 if a Critical/High is open"""
import hashlib, json, os, pathlib, re, shutil, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic_findings import norm_code, read_jsonl, tokens

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
         "dismissals": [], "memories": [], "scores": [], "costs": [], "stamps": {}, "restore": []}
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
    for k in ("decisions", "overrides", "false_positives", "dismissals", "memories", "scores", "costs", "restore"):
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
          "", "## Learned memories (from dismissals)", *[f"- {i + 1}. [{m['reason']}] {m['pattern']}{' (retired)' if m.get('retired') else ''} — hits {m.get('hits', 0)}" for i, m in enumerate(L["memories"])],
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

def finding(L, fid):
    if fid not in L["findings"]: die(f"no finding {fid}")
    return L["findings"][fid]

def quote_present(f):
    q = norm_code(f.get("quote")); file = (f.get("where") or "").rsplit(":", 1)[0]
    if not q or not file: return None
    try: return q in norm_code((ROOT / file).read_text(encoding="utf-8", errors="replace"))
    except OSError: return False

def learn(L, d):
    """3 dismissals with the same reason and overlapping words become a memory. Dismissals of Critical or High findings
    never count, so a memory can't be built from serious findings and then hide smaller ones of the same kind."""
    same = [x for x in L["dismissals"] if x["reason"] == d["reason"] and not x.get("used") and not x.get("hard")]
    group = [x for x in same if len(tokens(x["text"]) & tokens(d["text"])) >= max(2, len(tokens(d["text"])) // 3)]
    if len(group) >= 3:
        common = set.intersection(*[tokens(x["text"]) for x in group])
        if len(common) >= 2:
            files = {x["file"] for x in group}; glob = files.pop() if len(files) == 1 else "*"
            L["memories"].append({"reason": d["reason"], "pattern": " ".join(sorted(common)), "file_glob": glob, "hits": 0, "made": time.strftime("%Y-%m-%d"), "last_used": time.strftime("%Y-%m-%d")})
            for x in group: x["used"] = True
            return f"learned a memory from 3 '{d['reason']}' dismissals: {' '.join(sorted(common))}"
    return None

def main(a):
    if not a or any(x in ("-h", "--help") for x in a): print(__doc__); return 0  # help never changes the ledger
    cmd, rest = a[0], a[1:]; L = load(); msg = "ok"
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
        if rest[1].strip().lower() in ("author", "claude", "critic", "self"): die("an override must come from the owner, not the author")
        L["overrides"].append({"what": rest[0], "who": rest[1], "why": rest[2], "at": time.strftime("%Y-%m-%d %H:%M")})
    elif cmd == "score":
        need(rest, 3, "score NAME VALUE MAX")
        try: v, m = float(rest[1]), float(rest[2])
        except ValueError: die("VALUE and MAX must be numbers")
        prev = [x for x in L["scores"] if x["name"] == rest[0]]
        L["scores"].append({"name": rest[0], "value": v, "max": m, "at": time.strftime("%Y-%m-%d %H:%M")})
        msg = f"{rest[0]}: " + (f"{prev[-1]['value']:g}/{prev[-1]['max']:g} → " if prev else "") + f"{v:g}/{m:g}"
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
            L["round"] += 1; save(L)
            print(f"review round {L['round']} of 3" + (" (verify-only: no new findings without an executed case)" if L["round"] == 3 else ""))
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
