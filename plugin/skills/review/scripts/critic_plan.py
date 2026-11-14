#!/usr/bin/env python3
"""The job plan (SC-69): before a run, read what is being reviewed and propose the right tools for the job (ruling
§5.6, proportionality): the tier, the agents, the lenses that apply, the checks to run, and the expected cost from this
project's own history. The user accepts or changes it; an unattended run uses it as proposed. Nothing here calls a
model or runs project code.

usage:
  critic_plan.py [--json]
        reads .critic/change-map.json (run critic_map.py first) and the files it lists; writes .critic/plan.json and
        prints the plan. critic_run.py begin runs it.

The cost figures are medians of this project's recorded runs (.critic/cost.jsonl, by role); with no history the plan
says so instead of guessing."""
import json, os, pathlib, re, statistics, sys

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or __import__("projroot").project_of(os.getcwd())).resolve(); D = ROOT / ".critic"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import scan_tests, scan_ci, scan_agentcfg, scan_migrations, scan_reqs, scan_integrity

UI = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss"}
CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".kt", ".swift", ".vue", ".svelte"}
DOCS = {".md", ".rst", ".txt", ".adoc"}

def is_document(f):
    """A file a person reads. requirements.txt, CMakeLists.txt and the like end in .txt but are build input, so a file any
    lens claims, or a .txt named like build input, is not a document."""
    p = pathlib.PurePosixPath(f.replace("\\", "/"))
    if p.suffix.lower() not in DOCS: return False
    if any(x.lower() in ("requirements", "constraints") for x in p.parts[:-1]): return False  # requirements/base.txt
    if scan_ci.wants_text(f) or scan_agentcfg.wants(f) or scan_migrations.wants(f) or scan_tests.is_test_file(f): return False
    return not re.fullmatch(r"(?i)(?:cmakelists|requirements[\w.-]*|constraints[\w.-]*|robots|llms|runtime|\.?python-version|.*\.(?:in|cmake))\.txt", p.name)

def lenses_for(files):
    out = []
    if any(scan_tests.is_test_file(f) for f in files): out.append("tests of the tests")
    if any(scan_ci.is_workflow(f) or scan_ci.wants_text(f) or f.endswith("package-lock.json") for f in files): out.append("CI and supply chain")
    if any(scan_agentcfg.wants(f) for f in files): out.append("agent and MCP configuration")
    if any(scan_migrations.wants(f) for f in files): out.append("release and rollback")
    if any(re.search(r"(?i)settings|config|alert|k8s|deploy|helm|logging", f) for f in files): out.append("operations")
    if any(scan_integrity.wants(f) for f in files): out.append("browser integrity")
    texts = []
    for f in files:
        if scan_reqs.is_doc(f):
            try: texts.append((ROOT / f).read_text(encoding="utf-8", errors="replace")[:200000])
            except OSError: pass
    if any(scan_reqs.ID.search(t) for t in texts): out.append("requirements and intent")
    return out

def history():
    p = D / "cost.jsonl"
    try: rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() and not p.is_symlink() else []
    except (OSError, ValueError): rows = []
    by = {}
    for r in rows:
        if "unavailable" in r: continue
        tot = sum(int(r.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        by.setdefault(r.get("role", "?"), []).append(tot)
    return {k: int(statistics.median(v)) for k, v in by.items() if v}

SECURITY_LENSES = ["secrets and dependencies", "CI and supply chain", "agent and MCP configuration", "browser integrity", "operations"]  # each names a lenses.md section

def focus():
    try: return json.loads((D / "focus.json").read_text(encoding="utf-8")).get("focus") if (D / "focus.json").is_file() and not (D / "focus.json").is_symlink() else None
    except (OSError, ValueError): return None

def last_choice(files):
    """The tier the owner chose the last time these exact files were reviewed (R4), from a ledger Curmudgeon wrote on
    this machine; a ledger that came with the code is never read for it."""
    import critic_findings as cf_
    if not files or cf_.ledger_shipped(ROOT): return None
    try: L = json.loads((D / "ledger.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return None
    ch = L.get("tier_choices") if isinstance(L, dict) else None
    c = ch.get(cf_.files_key(files)) if isinstance(ch, dict) else None
    return {"tier": c["tier"], "run": c.get("run")} if isinstance(c, dict) and c.get("tier") in ("trivial", "lite", "full") else None

def plan(forced=None):
    try: cm = json.loads((D / "change-map.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): sys.exit("critic_plan: no .critic/change-map.json; run critic_map.py first")
    files = [str(f) for f in cm.get("files") or []]
    exts = {pathlib.PurePosixPath(f).suffix.lower() for f in files}
    tier = forced or cm.get("tier") or "full"  # a tier the user set (--tier) is the tier in force
    docs_only = bool(files) and all(is_document(f) for f in files)
    ui = bool(exts & UI)
    if docs_only and tier == "full" and not forced: tier = "lite"  # a document doesn't need three reviewers and the code sweep (ruling §5.6)
    reviewers = 3 if tier == "full" else 1
    p = {"tier": tier, "files": len(files), "lines": cm.get("lines"), "sensitive": [f for f, v in (cm.get("sensitive") or {}).items() if v][:10],
         "kind": "document or plan" if docs_only else ("interface" if ui else ("code" if exts & CODE else "other")),
         "reviewers": reviewers, "verification": {"full": "every surviving finding", "lite": "Critical, High and contested findings", "trivial": "contested findings only"}[tier] if tier in ("full", "lite", "trivial") else "every surviving finding",
         "lenses": [] if docs_only else lenses_for(files),
         "checks": ["claims, numbers and consistency"] if docs_only else ["scripted checks (secrets, structure, safety, rule files)"] + (["page checks in a browser (pass --page)"] if ui else []),
         "variant_hunt": tier == "full" and not docs_only,
         "outside_reviewer": "ask once, default no" if tier == "full" else "not offered at this tier"}
    h = history()
    if h:
        est = h.get("reviewer", 0) * reviewers + h.get("verifier", 0) * (2 if tier == "full" else 1) + h.get("dedup", 0) * (1 if reviewers > 1 else 0)
        p["expected_tokens"] = est; p["expected_basis"] = "medians of this project's recorded runs, by role"
    else: p["expected_tokens"] = None; p["expected_basis"] = "no recorded runs yet: the first run's cost is measured, not guessed"
    sg = cm.get("suggest") if isinstance(cm.get("suggest"), dict) else None
    if sg and tier != "full" and not docs_only and not forced: p["suggest"] = {"tier": "full", "why": [str(w) for w in sg.get("why") or []][:4]}  # 03 §5.57 item 39: suggested in one line, never switched to by itself
    if docs_only: p["note"] = "a document doesn't need the full code sweep: one reviewer and the claims check"
    last = last_choice(files)
    if last and not forced and last["tier"] != tier: p["last_choice"] = last  # R4: shown beside the proposal, never applied by itself
    if focus() == "security":  # the security scan mode (5.2): same panel size as the tier, security lenses and focus only
        p["focus"] = "security"; p["lenses"] = (["tests of the tests"] if "tests of the tests" in p["lenses"] else []) + SECURITY_LENSES
        p["checks"] = ["scripted security checks (critic_scan.py --focus security)", "the security feed: status, and an update when switched on and due"]
        p.pop("note", None)
    return p

def main(a):
    if a[:1] in (["-h"], ["--help"]): print(__doc__); return 0
    forced = a[a.index("--tier") + 1] if "--tier" in a and a.index("--tier") + 1 < len(a) and a[a.index("--tier") + 1] in ("trivial", "lite", "full") else None
    p = plan(forced)
    from critic_findings import refuse_linked_state
    refuse_linked_state(ROOT)
    (D / "plan.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
    if "--json" in a: print(json.dumps(p, indent=1)); return 0
    print(f"plan: {'security scan, ' if p.get('focus') == 'security' else ''}{p['tier']} tier for {p['files']} file(s) ({p['kind']}); {p['reviewers']} blind reviewer(s); verify {p['verification']}")
    if p["lenses"]: print("  lenses: " + ", ".join(p["lenses"]))
    print("  checks: " + "; ".join(p["checks"]) + ("; variant hunt" if p["variant_hunt"] else ""))
    print("  expected cost: " + (f"about {p['expected_tokens']:,} tokens ({p['expected_basis']})" if p["expected_tokens"] else p["expected_basis"]))
    if p.get("suggest"): print(f"  suggested: the full tier ({'; '.join(p['suggest']['why'])}): three blind reviewers, every finding verified, the variant hunt; say so to use it (begin --tier full)")
    if p.get("note"): print("  " + p["note"])
    if p.get("last_choice"): print(f"  last time: you chose the {p['last_choice']['tier']} tier for these same files (run {p['last_choice'].get('run')})")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
