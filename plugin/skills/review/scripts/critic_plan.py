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

ROOT = pathlib.Path(os.environ.get("CRITIC_ROOT") or re.sub(r"[\\/]\.critic[\\/]scratch(?:[\\/].*)?$", "", os.getcwd()) or os.getcwd()).resolve(); D = ROOT / ".critic"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scan_tests, scan_ci, scan_agentcfg, scan_migrations, scan_reqs

UI = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss"}
CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".kt", ".swift", ".vue", ".svelte"}
DOCS = {".md", ".rst", ".txt", ".adoc"}

def is_document(f):
    """A file a person reads. requirements.txt, CMakeLists.txt and the like end in .txt but are build input, so a file any
    lens claims, or a .txt named like build input, is not a document."""
    p = pathlib.PurePosixPath(f.replace("\\", "/"))
    if p.suffix.lower() not in DOCS: return False
    if scan_ci.wants_text(f) or scan_agentcfg.wants(f) or scan_migrations.wants(f) or scan_tests.is_test_file(f): return False
    return not re.fullmatch(r"(?i)(?:cmakelists|requirements[\w.-]*|constraints[\w.-]*|robots|llms|runtime|\.?python-version|.*\.(?:in|cmake))\.txt", p.name)

def lenses_for(files):
    out = []
    if any(scan_tests.is_test_file(f) for f in files): out.append("tests of the tests")
    if any(scan_ci.is_workflow(f) or scan_ci.wants_text(f) or f.endswith("package-lock.json") for f in files): out.append("CI and supply chain")
    if any(scan_agentcfg.wants(f) for f in files): out.append("agent and MCP configuration")
    if any(scan_migrations.wants(f) for f in files): out.append("release and rollback")
    if any(re.search(r"(?i)settings|config|alert|k8s|deploy|helm|logging", f) for f in files): out.append("operations")
    texts = []
    for f in files:
        if scan_reqs.is_doc(f):
            try: texts.append((ROOT / f).read_text(encoding="utf-8", errors="replace")[:200000])
            except OSError: pass
    if any(scan_reqs.ID.search(t) for t in texts): out.append("requirements and intent")
    return out

def history():
    p = D / "cost.jsonl"
    try: rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.is_file() and not p.is_symlink() else []
    except (OSError, ValueError): rows = []
    by = {}
    for r in rows:
        if "unavailable" in r: continue
        tot = sum(int(r.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        by.setdefault(r.get("role", "?"), []).append(tot)
    return {k: int(statistics.median(v)) for k, v in by.items() if v}

def plan():
    try: cm = json.loads((D / "change-map.json").read_text())
    except (OSError, ValueError): sys.exit("critic_plan: no .critic/change-map.json; run critic_map.py first")
    files = [str(f) for f in cm.get("files") or []]
    exts = {pathlib.PurePosixPath(f).suffix.lower() for f in files}
    tier = cm.get("tier") or "full"
    docs_only = bool(files) and all(is_document(f) for f in files)
    ui = bool(exts & UI)
    if docs_only and tier == "full": tier = "lite"  # a document doesn't need three reviewers and the code sweep (ruling §5.6)
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
    if docs_only: p["note"] = "a document doesn't need the full code sweep: one reviewer and the claims check"
    return p

def main(a):
    if a[:1] in (["-h"], ["--help"]): print(__doc__); return 0
    p = plan()
    if not D.is_symlink(): (D / "plan.json").write_text(json.dumps(p, indent=1))
    if "--json" in a: print(json.dumps(p, indent=1)); return 0
    print(f"plan: {p['tier']} tier for {p['files']} file(s) ({p['kind']}); {p['reviewers']} blind reviewer(s); verify {p['verification']}")
    if p["lenses"]: print("  lenses: " + ", ".join(p["lenses"]))
    print("  checks: " + "; ".join(p["checks"]) + ("; variant hunt" if p["variant_hunt"] else ""))
    print("  expected cost: " + (f"about {p['expected_tokens']:,} tokens ({p['expected_basis']})" if p["expected_tokens"] else p["expected_basis"]))
    if p.get("note"): print("  " + p["note"])
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
