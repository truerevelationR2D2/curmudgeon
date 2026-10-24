#!/usr/bin/env python3
"""Tests for Curmudgeon's scripts. No test framework needed: python3 tests/run_tests.py (exit 1 on any failure).
Each test builds its own scratch project in a temp folder and runs the real scripts against it."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent.parent
S = HERE / "skills" / "review" / "scripts"; H = HERE / "hooks"
RESULTS = []

def run(script, *a, cwd, stdin=None, env=None):
    e = dict(os.environ, CRITIC_ROOT=str(cwd), **(env or {}))
    return subprocess.run([sys.executable, str(script), *a], cwd=cwd, capture_output=True, text=True, input=stdin, env=e, timeout=300)

def test(name):
    def deco(fn):
        d = pathlib.Path(tempfile.mkdtemp(prefix="critic-test-"))
        try: fn(d); RESULTS.append((name, True, "")); print("PASS", name)
        except AssertionError as e: RESULTS.append((name, False, str(e))); print("FAIL", name, "—", e)
        except Exception as e: RESULTS.append((name, False, repr(e))); print("FAIL", name, "—", repr(e))
        finally: shutil.rmtree(d, ignore_errors=True)
        return fn
    return deco

# Fake credentials for the scanner tests. They are assembled at run time from obviously fake parts (EXAMPLE), so no
# credential-shaped text ships in this file; @NAME@ tokens in test strings are replaced by write() and T().
FAKE = {
    "@LIVE@": "sk" + "_live_" + "EXAMPLE" * 3 + "0001",
    "@LIVE2@": "sk" + "_live_" + "EXAMPLE" * 3 + "0002",
    "@TEST@": "sk" + "_test_" + "EXAMPLE" * 2,
    "@AWS@": "AK" + "IA" + "EXAMPLEEXAMPLE00",
    "@PROJ@": "sk" + "-proj-" + "EXAMPLE" * 5,
    "@GOOG@": "AI" + "za" + "EXAMPLE" * 5,
    "@ANT@": "sk" + "-ant-api03-" + "EXAMPLE" * 13,
    "@PW@": "Zq9x" + "&pw!" + "EXAMPLE",  # a placeholder-looking start would (rightly) be skipped by the scan
    "@DBPW@": "EXAMPLE" + "pw" + "55",
    "@PEM@": "-----BEGIN RSA " + "PRIVATE KEY-----" + "EXAMPLEbody" * 8,
}
def T(text):
    for k, v in FAKE.items(): text = text.replace(k, v)
    return text
def write(d, rel, text): p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(T(text)); return p

APP = 'function render(n) {\n  list.innerHTML = `<li>${n.title}</li>`;\n}\nconst price = total * 1.0825;\n'
def finding(**k):
    base = {"category": "xss", "impact": "Critical", "file": "src/app.js", "line": 2, "quote": "list.innerHTML = `<li>${n.title}</li>`;", "title": "Title rendered as HTML",
            "evidence": "src/app.js:2", "failing_case": "a title with <img onerror> runs script", "verified": "traced", "remediation": "textContent"}
    base.update(k); return base

@test("merge: 2 of 3 votes kept, single traced Medium dropped, contract breaches rejected, bad quotes retracted")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(), finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")]))
    write(d, "b.json", json.dumps([finding(impact="High", quote="${n.title}"), finding(title="no case", category="other", failing_case="", evidence="")]))
    write(d, "c.json", json.dumps([finding(title="eval of input", category="eval", quote="eval(x)", line=3)]))
    r = run(S / "critic_merge.py", "tally", "a.json", "b.json", "c.json", cwd=d); assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text())
    assert [f["title"] for f in t["kept"]] == ["Title rendered as HTML"] and t["kept"][0]["votes"] == 2, t["kept"]
    assert any(x["finding"]["title"] == "Tax rule in render code" for x in t["dropped"])
    assert any(x["finding"]["title"] == "eval of input" for x in t["retracted"])
    assert any(x["finding"]["title"] == "no case" for x in t["rejected"])

@test("merge: a verifier can lower but never raise an impact, and a vague refutation doesn't drop a finding")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="High")])); write(d, "b.json", json.dumps([finding(impact="High")]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "downgrade", "impact_after": "Critical"}])); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert json.loads((d / ".critic/findings.jsonl").read_text().splitlines()[0])["impact"] == "High"
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "refutation": "not real"}])); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert (d / ".critic/findings.jsonl").read_text().strip(), "a vague refutation dropped the finding"
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "reproduced": "traced", "refutation": "render() receives titles only from the escaped constant at src/app.js:4, so no user text ever reaches this line."}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert not (d / ".critic/findings.jsonl").read_text().strip(), "a concrete refutation should drop it"

@test("merge: counts in counts.md match findings.jsonl, and SARIF is valid JSON")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(verified="executed"), finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule", verified="executed")]))
    run(S / "critic_merge.py", "tally", "a.json", cwd=d); run(S / "critic_merge.py", "apply", "a.json", cwd=d)
    rows = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines()]
    assert "Critical 1 · High 0 · Medium 1 · Low 0 · total 2" in (d / ".critic/counts.md").read_text()
    assert json.loads((d / ".critic/findings.sarif").read_text())["runs"][0]["results"], "empty SARIF"
    assert len(rows) == 2

@test("ledger: fixed needs all three claims; round 3 refuses unverified findings; author overrides refused")
def _(d):
    L = S / "critic_ledger.py"; run(L, "start", "full", cwd=d); run(L, "add", "C1", "High", "a.js:1", "x", cwd=d)
    assert run(L, "fixed", "C1", "done", cwd=d).returncode == 2
    for c in ("targeted", "no-new-defect", "behaviour-unchanged"): run(L, "claim", "C1", c, "test", cwd=d)
    assert run(L, "fixed", "C1", "done", cwd=d).returncode == 0
    run(L, "round", cwd=d); run(L, "round", cwd=d)
    assert run(L, "add", "C2", "High", "a.js:2", "y", cwd=d).returncode == 2
    assert run(L, "add", "C2", "High", "a.js:2", "y", "--verified", cwd=d).returncode == 0
    assert run(L, "override", "gate", "author", "why", cwd=d).returncode == 2

@test("ledger: three similar dismissals become a memory, but a Critical security finding never does")
def _(d):
    L = S / "critic_ledger.py"; run(L, "start", "full", cwd=d)
    for i in range(3): run(L, "add", f"X{i}", "Low", f"b{i}.css:1", "hover colour too subtle", cwd=d); run(L, "dismiss", f"X{i}", "preference", "we like it", cwd=d)
    j = json.loads((d / ".critic/ledger.json").read_text()); assert len(j["memories"]) == 1, j["memories"]
    for i in range(3): run(L, "add", f"S{i}", "Critical", f"a{i}.js:1", "XSS in title", cwd=d); run(L, "dismiss", f"S{i}", "false-positive", "sanitised", cwd=d)
    j = json.loads((d / ".critic/ledger.json").read_text()); assert len(j["memories"]) == 1, "a security finding became a memory"

@test("ledger: a restore copy is exact, private (0700) and git-ignored")
def _(d):
    L = S / "critic_ledger.py"; src = 'const K = "@LIVE@";\nconst a = 1;\n'; write(d, "api.js", src)
    run(L, "restore", "save", "api.js", cwd=d)
    assert next((d / ".critic/restore").rglob("api.js")).read_text() == T(src)
    assert (d / ".critic/restore/.gitignore").read_text().strip().endswith("*")
    assert oct((d / ".critic/restore").stat().st_mode & 0o777) == "0o700"
    write(d, "api.js", '// test key @TEST@\nconst a = 2;\n'); run(L, "restore", "apply", cwd=d)
    assert (d / "api.js").read_text() == T(src)

@test("scan: secrets in config files, HTML validity, structure, WCAG 2.2 static rules")
def _(d):
    write(d, ".env", "STRIPE=@LIVE@\n")
    write(d, "index.html", '<!doctype html><html><head><title>t</title></head><body><a href="#"><button>x</button></a><p id="a"></p><p id="a"></p><input name="otp" autocomplete="off" type="password" onpaste="return false"></body></html>')
    write(d, "ui/view.js", 'import { price } from "../domain/price.js";\nexport function show() { return price(); }\n')
    write(d, "domain/price.js", 'import { show } from "../ui/view.js";\nexport function price() { return 1; }\n')
    r = run(S / "critic_scan.py", ".", "--out", "o", cwd=d); assert r.returncode == 0, r.stderr
    rules = {x["rule"] for x in json.loads((d / "o/report.json").read_text())["findings"]}
    for want in ("secret-stripe-key", "html-nested-interactive", "html-duplicate-id", "paste-blocked", "autocomplete-off-auth", "boundary", "import-cycle"):
        assert want in rules, f"missing {want}: {sorted(rules)}"

@test("scan: a check that never reports is blocked (fail closed), and a missing source exits 2")
def _(d):
    write(d, "a.js", "let x = 1;\n")
    r = run(S / "critic_scan.py", "nope", cwd=d); assert r.returncode == 2
    r = run(S / "critic_scan.py", ".", "--out", "o", cwd=d)
    ch = json.loads((d / "o/report.json").read_text())["checks"]
    assert all(k in ch for k in ("static", "structure", "deps", "ci", "page")), ch.keys()
    assert ch["page"]["state"] == "blocked"

@test("hooks: the guard denies direct edits to the ledger and allows review files")
def _(d):
    deny = run(H / "guard_state.py", cwd=d, stdin=json.dumps({"tool_input": {"file_path": str(d / ".critic/ledger.json")}})).stdout
    allow = run(H / "guard_state.py", cwd=d, stdin=json.dumps({"tool_input": {"file_path": str(d / ".critic/reviews/review-A.json")}})).stdout
    assert "deny" in deny and not allow.strip()

@test("hooks: stop gate blocks edits after a review, stops after 3 blocks, honours stop_hook_active")
def _(d):
    write(d, "src/a.js", "x"); (d / ".critic").mkdir(exist_ok=True); (d / ".critic/gate").write_text("")
    blocks = [run(H / "stop_gate.py", cwd=d, stdin=json.dumps({"cwd": str(d)})).stdout for _ in range(4)]
    assert all('"block"' in b for b in blocks[:3]) and '"block"' not in blocks[3], blocks
    assert not run(H / "stop_gate.py", cwd=d, stdin=json.dumps({"cwd": str(d), "stop_hook_active": True})).stdout.strip()

@test("hooks: contract check blocks a malformed review and passes other agents")
def _(d):
    write(d, ".critic/reviews/review-A.json", '[{"title": "x"}]')
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "cwd": str(d)})).stdout
    assert '"block"' in out
    assert not run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "general-purpose", "cwd": str(d)})).stdout.strip()

@test("map: a refund change is the full tier; a two-line note is trivial")
def _(d):
    write(d, "api.js", "export function refund(id) { return fetch('/api/refund', {method:'POST'}); }\n"); write(d, "app.js", "import { refund } from './api.js';\nrefund(1);\n")
    r = run(S / "critic_map.py", "--files", "api.js", "app.js", cwd=d); assert json.loads(r.stdout)["tier"] == "full", r.stdout
    write(d, "notes.txt", "hello\n"); write(d, "b.css", "a{}\n")
    r = run(S / "critic_map.py", "--files", "b.css", cwd=d); assert json.loads(r.stdout)["tier"] == "trivial", r.stdout

@test("fix F-00afe05a: rollback keeps the live key line instead of writing the redacted copy over it")
def _(d):
    L = S / "critic_ledger.py"; write(d, "api.js", 'const K = "@LIVE@";\nconst a = 1;\n')
    run(L, "restore", "save", "api.js", cwd=d); write(d, "api.js", 'const K = "@LIVE@";\nconst a = 2;\n')
    run(L, "restore", "apply", cwd=d); t = (d / "api.js").read_text()
    assert "REDACTED" not in t and "const a = 1" in t, t

@test("fix F-a902aa72: a killed mutation run is recovered from its backup on the next run")
def _(d):
    sys.path.insert(0, str(S)); import scan_mutation
    write(d, "lib.py", "def f(a, b):\n    return a <= b\n"); write(d, "lib.py.critic-mutation-backup", "def f(a, b):\n    return a < b\n")
    rows = []; scan_mutation.recover(d, lambda *a: rows.append(a))
    assert (d / "lib.py").read_text().endswith("a < b\n") and not (d / "lib.py.critic-mutation-backup").exists() and rows

@test("fix F-dadeba3d: a refutation with no pointer to the guard doesn't drop a finding; one with a pointer does")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="High")])); write(d, "b.json", json.dumps([finding(impact="High")]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d); fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "refutation": "I do not think this is a problem because it seems fine to me overall here."}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d); assert (d / ".critic/findings.jsonl").read_text().strip()
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "reproduced": "traced", "refutation": "Titles reach render() only through escapeTitle() at src/app.js:1, so no markup survives."}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d); assert not (d / ".critic/findings.jsonl").read_text().strip()

@test("fix F-e9e9ff4c / F-c2912a1b: learned memories never hide a High finding, and Critical/High dismissals never build one")
def _(d):
    L = S / "critic_ledger.py"; write(d, "src/app.js", APP); run(L, "start", "full", cwd=d)
    j = json.loads((d / ".critic/ledger.json").read_text())
    j["memories"] = [{"reason": "intended", "pattern": "title rendered html", "file_glob": "*", "hits": 0, "made": "2026-10-18", "last_used": "2026-10-18"}]
    (d / ".critic/ledger.json").write_text(json.dumps(j))
    write(d, "a.json", json.dumps([finding(impact="High", category="correctness", verified="executed")]))
    run(S / "critic_merge.py", "tally", "a.json", cwd=d); t = json.loads((d / ".critic/tally.json").read_text())
    assert t["kept"] and not t["suppressed"], t["suppressed"]
    for i in range(3): run(L, "add", f"H{i}", "High", f"x{i}.js:1", "xss in title render", cwd=d); run(L, "dismiss", f"H{i}", "intended", "fine", cwd=d)
    assert len(json.loads((d / ".critic/ledger.json").read_text())["memories"]) == 1

@test("fix F-e83ca836 / F-4d1e90b0: the same file written three ways is one issue; a line like '2-3' doesn't crash")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    for k, path in zip("abc", ("src/app.js", "./src/app.js", str(d / "src/app.js"))):
        write(d, f"{k}.json", json.dumps([finding(file=path, impact="Medium", line="2-3")]))
    r = run(S / "critic_merge.py", "tally", "a.json", "b.json", "c.json", cwd=d); assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text()); assert len(t["kept"]) == 1 and t["kept"][0]["votes"] == 3, t["kept"]

@test("fix F-2d5e7bfa: a line-level finding with no quote is rejected")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(quote="", verified="executed", line=99)]))
    run(S / "critic_merge.py", "tally", "a.json", cwd=d); t = json.loads((d / ".critic/tally.json").read_text())
    assert not t["kept"] and t["rejected"]

@test("fix F-577d55b0 / F-d8d732a2: keys on very long lines are found, and no report contains the secret")
def _(d):
    write(d, "bundle.min.js", "x" * 30000 + 'k="@LIVE@";'); write(d, ".env", "DB=postgres://admin:@DBPW@@db.example.com/app\n")
    run(S / "critic_scan.py", ".", "--out", "o", cwd=d)
    rep = (d / "o/report.json").read_text() + (d / "o/report.md").read_text()
    assert "secret-stripe-key" in rep and "secret-db-url-password" in rep
    assert FAKE["@LIVE@"][8:] not in rep and FAKE["@DBPW@"] not in rep

@test("fix F-a82f5662: the guard resolves '..' before checking")
def _(d):
    out = run(H / "guard_state.py", cwd=d, stdin=json.dumps({"cwd": str(d), "tool_input": {"file_path": str(d / ".critic/reviews/../ledger.json")}})).stdout
    assert "deny" in out

@test("fix F-9989c1bb / F-27bf1c9c: the gate stays released for the same batch, and a new unstamped file counts")
def _(d):
    L = S / "critic_ledger.py"; write(d, "src/a.js", "x"); run(L, "stamp", "src/a.js", cwd=d); run(L, "gate", "on", cwd=d)
    write(d, ".critic/last-review.md", "r"); import time; time.sleep(1.1); write(d, "src/new.js", "eval(userInput)")
    outs = [run(H / "stop_gate.py", cwd=d, stdin=json.dumps({"cwd": str(d)})).stdout for _ in range(6)]
    assert '"block"' in outs[0], "a new file after the review must count"
    assert all('"block"' not in o for o in outs[4:]), outs

@test("fix F-0e7b1749: the contract check validates the stopping reviewer's own named file")
def _(d):
    write(d, ".critic/reviews/review-B.json", '[{"title": "x"}]'); write(d, ".critic/reviews/review-A.json", "[]")
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-reviewer", "cwd": str(d), "last_assistant_message": "Wrote .critic/reviews/review-B.json"})).stdout
    assert '"block"' in out, out

@test("fix F-79ef1146 / F-4785936a / F-6e26d6cf: 'author' isn't 'auth', and main() doesn't link unrelated files")
def _(d):
    write(d, "a.css", "/* by author */\na{}\n")
    assert json.loads(run(S / "critic_map.py", "--files", "a.css", cwd=d).stdout)["tier"] == "trivial"
    write(d, "x.py", "def main():\n    pass\nmain()\n"); write(d, "y.py", "def main():\n    pass\nmain()\n")
    assert json.loads(run(S / "critic_map.py", "--files", "x.py", cwd=d).stdout)["radius"] == 0

@test("fix (test wave): a tally with no review files refuses instead of keeping scan rows on zero votes")
def _(d):
    write(d, ".critic/scan/report.json", json.dumps({"rows": []}))
    r = run(S / "critic_merge.py", "tally", "--scan", ".critic/scan/report.json", cwd=d)
    assert r.returncode == 2 and "refusing" in (r.stdout + r.stderr), r.stdout + r.stderr

@test("fix (test wave): dedup lists duplicates cited 40+ lines apart, and a group merges their votes")
def _(d):
    src = "".join(f"const v{i} = {i};\n" for i in range(60))
    write(d, "src/a.js", src)
    a = finding(category="logic", impact="Medium", file="src/a.js", line=2, quote="const v1 = 1;", title="Counter starts at the wrong value", verified="traced")
    b = finding(category="state", impact="Medium", file="src/a.js", line=50, quote="const v49 = 49;", title="Off-by-one in the initial index", verified="traced")
    write(d, ".critic/reviews/review-A.json", json.dumps([a])); write(d, ".critic/reviews/review-B.json", json.dumps([b]))
    write(d, ".critic/reviews/review-C.json", json.dumps([]))
    revs = [".critic/reviews/review-A.json", ".critic/reviews/review-B.json", ".critic/reviews/review-C.json"]
    r = run(S / "critic_merge.py", "tally", *revs, cwd=d); assert r.returncode == 0, r.stdout + r.stderr
    listed = json.loads((d / ".critic/dedup-candidates.json").read_text())["findings_by_file"]["src/a.js"]
    assert len(listed) == 2, listed
    t = json.loads((d / ".critic/tally.json").read_text()); assert len(t["kept"]) == 0, t["kept"]
    write(d, ".critic/groups.json", json.dumps({"groups": [[x["id"] for x in listed]]}))
    run(S / "critic_merge.py", "tally", *revs, "--groups", ".critic/groups.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text()); assert len(t["kept"]) == 1 and t["kept"][0]["votes"] == 2, t

@test("round 2 N1: detector FAIL rows (a live key, eval) survive the tally without a quote")
def _(d):
    write(d, "src/k.js", 'const k = "@LIVE@";\n'); write(d, "src/a.js", "x = 1;\neval(input);\n")
    run(S / "critic_scan.py", "src", "--root", ".", cwd=d)
    write(d, ".critic/reviews/review-A.json", "[]")
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", "--scan", ".critic/scan/report.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert any("stripe" in str(k.get("category")) for k in t["kept"]), (r.stdout, t["rejected"])
    assert FAKE["@LIVE@"] not in (d / ".critic/tally.json").read_text()

@test("round 2 N2: rollback matches redacted lines by content, and an added key-like line can't displace the real one")
def _(d):
    write(d, "src/api.js", 'const K = "@LIVE@";\nconst a = 1;\n')
    run(S / "critic_ledger.py", "init", cwd=d); run(S / "critic_ledger.py", "restore", "save", "src/api.js", cwd=d)
    write(d, "src/api.js", '// example key for tests: @TEST@\nconst K = "@LIVE@";\nconst a = 2;\n')
    run(S / "critic_ledger.py", "restore", "apply", cwd=d)
    t = (d / "src/api.js").read_text()
    assert t.startswith(T('const K = "@LIVE@";')) and "const a = 1;" in t and "REDACTED" not in t, t

@test("round 2 N3: every secret on a line is masked in the reports, and a private key's body never appears")
def _(d):
    write(d, ".env", "STRIPE_KEY=@LIVE@ AWS_KEY=@AWS@\n")
    write(d, "cfg.js", 'const c = { password: "@PW@", stripe: "@LIVE@" };\n')
    write(d, "k.pem", "@PEM@\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = (d / ".critic/scan/report.md").read_text() + (d / ".critic/scan/report.json").read_text()
    for s_ in (FAKE["@LIVE@"][8:], FAKE["@AWS@"], FAKE["@PW@"], FAKE["@PEM@"][31:60]): assert s_ not in rep, s_

@test("round 2 N4: rules.md commands run only with --project-checks")
def _(d):
    write(d, ".critic/rules.md", "## Scripted checks\n- marker: touch ran.txt\n"); write(d, "a.py", "x = 1\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d); assert not (d / "ran.txt").exists()
    run(S / "critic_scan.py", ".", "--root", ".", "--project-checks", cwd=d); assert (d / "ran.txt").exists()

@test("round 2 N5: token, role and security code is the full tier")
def _(d):
    write(d, "jwt.js", "export function verify(token) { return jwt.verify(token, KEY) }\n"); write(d, "roles.py", 'return user.role == "owner"\n')
    for f_ in ("jwt.js", "roles.py"):
        assert json.loads(run(S / "critic_map.py", "--files", f_, cwd=d).stdout)["tier"] == "full", f_

@test("round 2 N6 / F-dadeba3d / round 4 N2: a refutation needs an existing file:line, a run or trace, and no hedging")
def _(d):
    sys.path.insert(0, str(S)); from critic_findings import refutation_problem
    write(d, "src/List.jsx", "\n".join(f"line {i}" for i in range(1, 30)))
    ok = "React escapes text children, and src/List.jsx:14 renders the title as a child, so it is never parsed as HTML."
    assert refutation_problem(ok, "High", "traced", root=d) is None
    assert refutation_problem(ok.replace(":14", ":99"), "High", "traced", root=d), "a line that doesn't exist"
    assert refutation_problem("`render()` is completely fine and nothing about this path can fail in practice for any input at all.", "Critical", "traced", root=d)
    assert refutation_problem("I don't think this is a real bug; it probably seems fine, see src/List.jsx:14 maybe, in my view.", "Critical", "traced", root=d)
    assert refutation_problem(ok, "Medium", "no", root=d), "needs a run or a trace"

@test("round 2 F-2d5e7bfa: a one-review Critical with no line and no quote is contested, not kept")
def _(d):
    write(d, "src/app.js", APP)
    write(d, ".critic/reviews/review-A.json", json.dumps([finding(line=None, quote="", verified="traced")]))
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text()); assert not t["kept"] and len(t["contested"]) == 1, t

@test("round 3 R1: the verifier stop check blocks a bare refutation and passes a concrete one")
def _(d):
    msg = lambda why: "```json\n" + json.dumps([{"id": "F-1", "verdict": "refuted", "reproduced": "executed", "refutation": why}]) + "\n```"
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-verifier", "cwd": str(d), "last_assistant_message": msg("not real")})).stdout
    assert '"block"' in out, out
    write(d, "src/app.js", "\n".join(f"line {i}" for i in range(1, 20)))
    ok = "The title is assigned with textContent at src/app.js:14, so markup in it is shown as text and never parsed."
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-verifier", "cwd": str(d), "last_assistant_message": msg(ok)})).stdout
    assert '"block"' not in out, out

@test("round 3 R2 (redesigned): restore copies with keys stay private and git-ignored, and no report reads them")
def _(d):
    keys = [FAKE["@PROJ@"], FAKE["@GOOG@"]]
    write(d, "cfg.js", "".join(f'const k{i} = "{k}";\n' for i, k in enumerate(keys)))
    run(S / "critic_ledger.py", "init", cwd=d); run(S / "critic_ledger.py", "restore", "save", "cfg.js", cwd=d)
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = "".join(p.read_text() for p in (d / ".critic/scan").glob("report.*"))
    assert not any(k in rep for k in keys) and "restore/" not in rep, "a report read the restore copies"
    assert (d / ".critic/restore/.gitignore").exists()

@test("round 3 R3/R5 and scan rows: code named like docs merges; identical key lines restore; two keys on a line stay two")
def _(d):
    write(d, "src/readmeParser.js", "".join(f"const v{i} = {i};\n" for i in range(10)))
    a = finding(category="logic", impact="Medium", file="src/readmeParser.js", line=2, quote="const v1 = 1;", title="Parser drops the first heading", verified="traced")
    b = finding(category="state", impact="Medium", file="src/readmeParser.js", line=8, quote="const v7 = 7;", title="First section is skipped", verified="traced")
    write(d, ".critic/reviews/review-A.json", json.dumps([a])); write(d, ".critic/reviews/review-B.json", json.dumps([b])); write(d, ".critic/reviews/review-C.json", "[]")
    revs = [f".critic/reviews/review-{x}.json" for x in "ABC"]
    run(S / "critic_merge.py", "tally", *revs, cwd=d)
    ids = [x["id"] for x in json.loads((d / ".critic/dedup-candidates.json").read_text())["findings_by_file"]["src/readmeParser.js"]]
    write(d, ".critic/groups.json", json.dumps({"groups": [ids]})); run(S / "critic_merge.py", "tally", *revs, "--groups", ".critic/groups.json", cwd=d)
    assert len(json.loads((d / ".critic/tally.json").read_text())["kept"]) == 1
    k = 'const K = "@LIVE@";'
    write(d, "src/two.js", f"{k}\n{k}\nconst a = 1;\n"); run(S / "critic_ledger.py", "init", cwd=d); run(S / "critic_ledger.py", "restore", "save", "src/two.js", cwd=d)
    write(d, "src/two.js", f"{k}\n{k}\nconst a = 2;\n"); run(S / "critic_ledger.py", "restore", "apply", cwd=d)
    assert (d / "src/two.js").read_text() == T(f"{k}\n{k}\nconst a = 1;\n"), (d / "src/two.js").read_text()
    write(d, ".env", "STRIPE_KEY=@LIVE@ AWS_KEY=@AWS@\n")
    run(S / "critic_scan.py", ".env", "--root", ".", cwd=d)
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-C.json", "--scan", ".critic/scan/report.json", cwd=d)
    cats = {x["category"] for x in json.loads((d / ".critic/tally.json").read_text())["kept"]}
    assert {"secret-stripe-key", "secret-aws-access-key"} <= cats, cats

@test("round 3 R4 / F-dadeba3d: a located refutation may say 'might'; a bare `name` is no pointer; a lone unquoted Medium is contested")
def _(d):
    sys.path.insert(0, str(S)); from critic_findings import refutation_problem
    assert refutation_problem("The guard at src/app.js:14 returns early when the list is empty, so the loop that might crash never runs.", "High", "traced") is None
    assert refutation_problem("`render` is completely fine and nothing about this path can fail in practice for any input.", "Critical", "traced")
    write(d, "src/app.js", APP)
    write(d, ".critic/reviews/review-A.json", json.dumps([finding(impact="Medium", line=None, quote="", verified="traced")]))
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text()); assert not t["kept"] and len(t["contested"]) == 1, t

@test("round 4 N4 and s2 fixer reports: one key is one finding; --help changes nothing; scanner rules don't flag correct code")
def _(d):
    write(d, "k.js", 'const a = "@ANT@";\n')
    write(d, "s.css", "a:hover, a:focus-visible { color: red }\n")
    write(d, "q.js", "export function load(params) { return fetch(`/api?${params}`).then(r => r.json()); }\nload(new URLSearchParams());\n")
    write(d, "u.js", "const $ = (id) => document.getElementById(id);\n$('x');\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    rules = [r["rule"] for r in rows]
    assert rules.count("secret-anthropic-key") == 1 and "secret-openai-key" not in rules, rules
    assert not any(r["rule"] == "hover-only" for r in rows), rules
    assert not any(r["rule"] == "url-unencoded" for r in rows), rules
    assert not any(r["rule"] == "dead-function" and "u.js" in r["where"] for r in rows), rules
    run(S / "critic_ledger.py", "init", cwd=d); before = (d / ".critic/ledger.json").read_text()
    run(S / "critic_ledger.py", "decision", "--help", cwd=d); run(S / "critic_ledger.py", "round", "--help", cwd=d)
    assert (d / ".critic/ledger.json").read_text() == before

@test("final check R5-1..R5-7: doubt words, paths outside the project, url params, help message, refusals, deps, ids")
def _(d):
    sys.path.insert(0, str(S)); from critic_findings import refutation_problem
    write(d, "src/app.js", "\n".join(f"line {i}" for i in range(1, 20)))
    for w in ("Presumably the caller escapes the title first; src/app.js:4 is where that happens for every value.",
              "I don\u2019t think so: the caller escapes the title first at src/app.js:4 for every value it renders here."):
        assert refutation_problem(w, "High", "executed", root=d), w
    good = "The caller escapes the title at src/app.js:4 before render runs, so every value reaching this line is plain text."
    assert refutation_problem(good, "High", "traced", root=d) is None
    assert refutation_problem(good, "Critical", "traced", root=d), "a Critical needs a run"
    assert refutation_problem(good, "Critical", "executed", root=d) is None
    write(d, ".critic/tally.json", "{}")
    for loc in (".critic/tally.json:1", "../etc/passwd:1", "/etc/passwd:1"):
        assert refutation_problem(good.replace("src/app.js:4", loc), "High", "traced", root=d), loc
    write(d, "q.js", "export function load(params) { return fetch(`/api/u?id=${params.id}`); }\nload({});\n")
    write(d, "package.json", json.dumps({"dependencies": {"left-pad": "*"}}))
    write(d, "keys.js", 'const a = "@LIVE@";\nconst b = "@LIVE2@";\n')
    run(S / "critic_ledger.py", "init", cwd=d); run(S / "critic_ledger.py", "restore", "save", "package.json", "src/app.js", cwd=d)
    write(d, "src/app.js", "REDACTED-BY-CRITIC is just text here\n"); run(S / "critic_ledger.py", "restore", "save", "src/app.js", cwd=d)
    write(d, "src/app.js", "changed\n"); out = run(S / "critic_ledger.py", "restore", "apply", cwd=d).stdout
    assert (d / "src/app.js").read_text().startswith("REDACTED-BY-CRITIC"), out
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    assert any(r["rule"] == "url-unencoded" for r in rows), "params.id must still be flagged"
    assert not any(".critic" in r["where"] for r in rows), [r["where"] for r in rows if ".critic" in r["where"]]
    write(d, ".critic/reviews/review-A.json", "[]")
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", "--scan", ".critic/scan/report.json", cwd=d)
    ids = [k["id"] for k in json.loads((d / ".critic/tally.json").read_text())["kept"] if k["category"] == "secret-stripe-key"]
    assert len(ids) == 2 and len(set(ids)) == 2, ids

@test("4.1 memory redesign: a memory notes a look-alike finding but never hides it, never notes a Critical, and dismiss --like closes on purpose")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    j = json.loads((d / ".critic/ledger.json").read_text())
    j["memories"] = [{"reason": "intended", "pattern": "rendered title html", "file_glob": "*", "hits": 0, "count": 3, "made": "2026-10-18", "last_used": "2026-10-18"}]
    (d / ".critic/ledger.json").write_text(json.dumps(j))
    med = finding(impact="Medium", verified="executed"); crit = finding(category="xss2", impact="Critical", verified="executed", line=2)
    write(d, "a.json", json.dumps([med, crit])); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert not t["suppressed"] and len(t["kept"]) == 2, t
    notes = {k["impact"]: bool(k.get("memory_note")) for k in t["kept"]}
    assert notes == {"Medium": True, "Critical": False}, notes
    assert not any("memory" in x for x in json.loads(next((d / ".critic/verify").glob("*.json")).read_text())), "the verifier must stay blind to notes"
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "Looks like your past dismissals" in (d / ".critic/counts.md").read_text()
    assert "total 2" in (d / ".critic/counts.md").read_text(), "a noted finding still counts"
    out = run(S / "critic_ledger.py", "dismiss", "--like", "1", "reviewed: intended pattern", cwd=d).stdout
    st = {k: v["status"] for k, v in json.loads((d / ".critic/ledger.json").read_text())["findings"].items()}
    assert sorted(st.values()) == ["dismissed", "open"], (out, st)

@test("4.1 Python parser rules: real calls are found; strings, comments and constant shell commands are not")
def _(d):
    write(d, "t.py", 'import subprocess, yaml, requests\nmsg = "never call eval(x) here"  # eval( in a string\n'
                     'subprocess.run("ls -l", shell=True)\nsubprocess.run("ls " + user, shell=True)\neval(user)\n'
                     'yaml.load(s, Loader=yaml.SafeLoader)\nyaml.load(s)\nrequests.get(u, verify=False)\n')
    write(d, "old.py", 'print "python 2"\neval(x)\n')  # doesn't parse: the text rules still run
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    got = sorted((r["rule"], r["where"]) for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"].startswith("py-"))
    assert got == [("py-eval", "old.py:2"), ("py-eval", "t.py:5"), ("py-shell-true", "t.py:4"), ("py-verify-false", "t.py:8"), ("py-yaml-load", "t.py:7")], got

@test("4.1 licences: a strong copyleft dependency warns, a missing licence is noted, the owner's own private package is fine")
def _(d):
    write(d, "package.json", json.dumps({"name": "x", "private": True, "dependencies": {"a": "1.0.0"}}))
    write(d, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/gpl-thing": {"version": "1.0.0", "license": "GPL-3.0"},
        "node_modules/lgpl-thing": {"version": "1.0.0", "license": "LGPL-2.1"}, "node_modules/nolic": {"version": "1.0.0"}, "node_modules/ok": {"version": "1.0.0", "license": "MIT"}}}))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = {r["rule"]: r for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"].startswith("licence")}
    assert rows["licence-copyleft"]["sev"] == "WARN" and "gpl-thing" in rows["licence-copyleft"]["what"] and "lgpl" not in rows["licence-copyleft"]["what"], rows
    assert "nolic" in rows["licence-missing"]["what"] and "licence-missing-own" not in rows and "licence-weak-copyleft" in rows, rows

@test("4.1 rule files: built-in rules run, a project rule runs in its own process, a bad rule is reported and skipped")
def _(d):
    write(d, "a.js", "debugger;\nvar x = 1;\n")
    write(d, ".critic/rules/mine.json", json.dumps([{"id": "my-var", "severity": "NOTE", "area": "perf", "pattern": "\\bvar\\b", "message": "var used", "files": ["*.js"]},
                                                     {"id": "Bad Id", "severity": "NOTE", "area": "perf", "pattern": "x", "message": "m"}]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rules = [r["rule"] for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"]]
    assert "rule-debugger-left" in rules and "rule-my-var" in rules and "rule-file-invalid" in rules, rules
    run(S / "critic_scan.py", ".", "--root", ".", "--no-project-rules", cwd=d)
    rules = [r["rule"] for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"]]
    assert "rule-my-var" not in rules and "rule-debugger-left" in rules, rules

@test("4.1 run log, refutation log and spot-check")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="High", verified="executed"), finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule", verified="executed")]))
    run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    ids = [k["id"] for k in json.loads((d / ".critic/tally.json").read_text())["kept"]]
    why = "The price is never shown: src/app.js:4 is dead code with no caller anywhere in the project, so the rule never applies."
    write(d, "v.json", json.dumps([{"id": ids[1], "verdict": "refuted", "reproduced": "traced", "refutation": why}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    log = (d / ".critic/runlog.jsonl").read_text(); assert "critic_merge.py tally" in log and "critic_ledger.py start" in log, log
    refs = [json.loads(x) for x in (d / ".critic/refutations.jsonl").read_text().splitlines()]
    assert len(refs) == 1 and refs[0]["id"] == ids[1] and refs[0]["kind"] == "refuted", refs
    out = run(S / "critic_ledger.py", "spotcheck", cwd=d).stdout; assert "2 item(s)" in out, out
    pend = json.loads((d / ".critic/ledger.json").read_text())["spotcheck_pending"]
    for x in pend: run(S / "critic_ledger.py", "spotcheck", "answer", x["id"], "real", cwd=d)
    st = run(S / "critic_ledger.py", "spotcheck", "stats", cwd=d).stdout
    assert "findings judged 1: 1 real" in st and "verifier decisions judged 1: 1 of 1 drops removed a real bug" in st, st

@test("4.1 self-review: session.verify = False is found; dismiss --like closes only open Medium/Low; the audit logs are guarded")
def _(d):
    write(d, "a.py", "import requests\ns = requests.Session()\ns.verify = False\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert any(r["rule"] == "py-verify-false" and r["where"] == "a.py:3" for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"])
    for name in ("refutations.jsonl", "runlog.jsonl", "spotcheck.md"):
        out = run(H / "guard_state.py", cwd=d, stdin=json.dumps({"cwd": str(d), "tool_input": {"file_path": str(d / ".critic" / name)}})).stdout
        assert "deny" in out, (name, out)
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    j = json.loads((d / ".critic/ledger.json").read_text())
    j["memories"] = [{"reason": "intended", "pattern": "rendered title html", "file_glob": "*", "hits": 0, "count": 3, "made": "2026-10-18", "last_used": "2026-10-18"}]
    (d / ".critic/ledger.json").write_text(json.dumps(j))
    rows = [finding(impact="High", verified="executed"), finding(category="xss3", impact="Medium", verified="executed", line=2), finding(category="xss4", impact="Low", verified="executed", line=2)]
    write(d, "a.json", json.dumps(rows)); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    noted = {k["impact"]: bool(k.get("memory_note")) for k in json.loads((d / ".critic/tally.json").read_text())["kept"]}
    assert noted == {"High": False, "Medium": True, "Low": True}, noted
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    L = json.loads((d / ".critic/ledger.json").read_text())
    low = next(k for k, v in L["findings"].items() if v["score"] == "Low"); L["findings"][low]["status"] = "fixed"; (d / ".critic/ledger.json").write_text(json.dumps(L))
    out = run(S / "critic_ledger.py", "dismiss", "--like", "1", "same as before", cwd=d).stdout
    st = {v["score"]: v["status"] for v in json.loads((d / ".critic/ledger.json").read_text())["findings"].values()}
    assert st == {"High": "open", "Medium": "dismissed", "Low": "fixed"}, (out, st)

@test("4.1 self-review: rule files are hardened (string files, non-list, links, output cap, rule- prefix) and the runner is logged")
def _(d):
    write(d, "app.py", "import os\n"); write(d, "a.js", "\n".join(["var x = 1;"] * 300) + "\n")
    write(d, ".critic/rules/a.json", json.dumps([{"id": "py-only", "severity": "NOTE", "area": "perf", "pattern": "import", "message": "m", "files": "*.js"},
                                                  {"id": "status-unchecked", "severity": "FAIL", "area": "perf", "pattern": ".", "message": "every line", "files": ["*.js"]}]))
    write(d, ".critic/rules/b.json", json.dumps({"id": "lonely", "severity": "NOTE", "area": "perf", "pattern": "x", "message": "m"}))
    os.symlink("/dev/zero", d / ".critic/rules/evil.json")
    r = run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert r.returncode == 2 and "refusing" in r.stderr, "a link inside .critic must stop the scan"
    (d / ".critic/rules/evil.json").unlink()
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    bad = " ".join(r["what"] for r in rows if r["rule"] == "rule-file-invalid")
    assert "files must be a list" in bad and "must hold a JSON list" in bad, bad
    hits = [r for r in rows if r["rule"] == "rule-status-unchecked"]
    assert len(hits) == 50 and not any(r["rule"] == "status-unchecked" and r["sev"] == "FAIL" for r in rows), len(hits)
    assert any(r["rule"] == "rule-file-truncated" for r in rows)
    assert "rule_runner.py" in (d / ".critic/runlog.jsonl").read_text()

@test("4.1 self-review: licences read SPDX OR/AND; workspace links are skipped; apply twice logs a refutation once; the map ignores .critic")
def _(d):
    sys.path.insert(0, str(S)); import scan_deps
    assert [scan_deps.spdx_kind(x) for x in ("MIT OR GPL-3.0", "(LGPL-2.1 AND GPL-3.0)", "LGPL-2.1", "GPL-2.0")] == ["permissive", "strong", "weak", "strong"]
    write(d, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/mylib": {"link": True, "resolved": "packages/mylib"}, "packages/mylib": {"version": "1.0.0"}}}))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert not any(r["rule"] == "licence-missing" for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"])
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="Medium", verified="executed")])); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    why = "The title is assigned with textContent at src/app.js:2 in the shipped build, so markup is never parsed by the page."
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "reproduced": "executed", "refutation": why}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert len((d / ".critic/refutations.jsonl").read_text().splitlines()) == 1
    subprocess.run(["git", "init", "-q"], cwd=d); subprocess.run(["git", "add", "src"], cwd=d)
    out = json.loads(run(S / "critic_map.py", cwd=d).stdout)
    cm = (d / ".critic/change-map.md").read_text()
    assert "src/app.js" in cm and "runlog" not in cm and "refutations" not in cm, cm

@test("4.1 recheck: links in .critic stop every script; a bad refutation line can't crash apply; verify names, SPDX parentheses, old fp rulings, file- ids")
def _(d):
    outside = d.parent / (d.name + "-outside.txt"); outside.write_text("keep me\n" * 5)
    (d / ".critic").mkdir(); os.symlink(outside, d / ".critic/runlog.jsonl")
    for script, args in (("critic_scan.py", [".", "--root", "."]), ("critic_ledger.py", ["init"]), ("critic_map.py", ["--files", "x"]), ("critic_merge.py", ["show"])):
        r = run(S / script, *args, cwd=d); assert r.returncode == 2 and "refusing" in r.stderr, (script, r.stderr)
    assert outside.read_text() == "keep me\n" * 5; outside.unlink(); (d / ".critic/runlog.jsonl").unlink()
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, ".critic/refutations.jsonl", '{"run": 1, "id": "F-x", "kind": "refuted"}\n{"run": 1, "id": "F-y", "kin')
    write(d, "a.json", json.dumps([finding(impact="Medium", verified="executed")])); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    why = "The title is assigned with textContent at src/app.js:2 in the shipped build, so markup is never parsed by the page."
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "reproduced": "executed", "refutation": why}]))
    r = run(S / "critic_merge.py", "apply", "v.json", cwd=d); assert r.returncode == 0 and (d / ".critic/counts.md").exists(), r.stderr
    write(d, "v.py", "skip_verify = False\nneeds_reverify = False\nssl_verify = False\n")
    sys.path.insert(0, str(S)); import scan_deps
    assert scan_deps.spdx_kind("GPL-3.0 AND (MIT OR Apache-2.0)") == "strong" and scan_deps.spdx_kind("(MIT OR GPL-3.0)") == "permissive"
    assert scan_deps.spdx_kind("(" * 4000 + "GPL-3.0" + ")" * 4000) == "strong", "absurd nesting falls back to the strictest name"
    write(d, "b.js", "debugger;\n")
    write(d, ".critic/rules/r.json", json.dumps([{"id": "file-timeout", "severity": "FAIL", "area": "perf", "pattern": "x", "message": "fake"}]))
    j = json.loads((d / ".critic/ledger.json").read_text()); j["false_positives"].append({"rule": "debugger-left", "where": "b.js:1", "why": "on purpose"})
    (d / ".critic/ledger.json").write_text(json.dumps(j))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    py = [r["where"] for r in rows if r["rule"] == "py-verify-false"]
    assert py == ["v.py:3"], py
    assert not any(r["rule"] == "rule-debugger-left" for r in rows), "an fp ruling saved under the old id must still apply"
    assert not any(r["rule"] == "rule-file-timeout" for r in rows) and "reserved" in " ".join(r["what"] for r in rows if r["rule"] == "rule-file-invalid")

@test("ChatGPT double-blind fixes: project rules can't fail, aggregate rule limits, spot-check downgrades, yaml loaders, import aliases")
def _(d):
    write(d, "a.js", "\n".join(f"line {i}" for i in range(10)) + "\n")
    write(d, ".critic/rules/r.json", json.dumps([{"id": "everything", "severity": "FAIL", "area": "safety", "pattern": ".*", "message": "fake"}]))
    for i in range(60): write(d, f".critic/rules/x{i:02d}.json", json.dumps([{"id": f"r{i:02d}", "severity": "NOTE", "area": "perf", "pattern": "zzz", "message": "m"}]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    assert all(r["sev"] != "FAIL" for r in rows if r["rule"] == "rule-everything") and any(r["rule"] == "rule-everything" for r in rows)
    assert "over the limit of 50 files" in " ".join(r["what"] for r in rows if r["rule"] == "rule-file-limit")
    write(d, "y.py", "import yaml, evil\nimport subprocess as sp\nfrom subprocess import run as r\nfrom yaml import SafeLoader\n"
                     "yaml.load(s, Loader=evil.SafeLoader)\nyaml.load(s, Loader=SafeLoader)\nsp.run(u, shell=True)\nr(u, shell=True)\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    got = sorted((x["rule"], x["where"]) for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["rule"].startswith("py-"))
    assert got == [("py-shell-true", "y.py:7"), ("py-shell-true", "y.py:8"), ("py-yaml-load", "y.py:5")], got
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="High", verified="executed")])); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "downgrade", "impact_after": "Low", "reproduced": "traced", "note": "minor"}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    out = run(S / "critic_ledger.py", "spotcheck", cwd=d).stdout; assert "1 item(s)" in out, out
    assert "downgraded" in (d / ".critic/spotcheck.md").read_text()

@test("ChatGPT double-blind fixes: unknown licences noted, v1 lockfiles flagged, run log masks secrets and trims from the tail")
def _(d):
    sys.path.insert(0, str(S)); import scan_deps, critic_findings
    assert [scan_deps.spdx_kind(x) for x in ("UNLICENSED", "LicenseRef-Commercial", "MIT", "MIT OR UNLICENSED", "GPL-3.0")] == ["unknown", "unknown", "permissive", "permissive", "strong"]
    write(d, "package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/p": {"version": "1", "license": "UNLICENSED"}}}))
    write(d, "old/package-lock.json", json.dumps({"lockfileVersion": 1, "dependencies": {"q": {"version": "1"}}}))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rules = [r["rule"] for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"]]
    assert "licence-unknown" in rules and "licence-not-checked" in rules, rules
    tok = "Bearer " + "EXAMPLEtoken123"
    critic_findings.log_run(d, "command", f'curl -H "Authorization: {tok}" https://u:pw' + "EXAMPLE@h.example/x")
    log = (d / ".critic/runlog.jsonl").read_text(); assert "EXAMPLEtoken123" not in log and "pwEXAMPLE" not in log, log
    assert "runlog.jsonl" in (d / ".critic/.gitignore").read_text()
    (d / ".critic/runlog.jsonl").write_text(("x" * 200 + "\n") * 10000)
    critic_findings.log_run(d, "script", "after trim")
    assert (d / ".critic/runlog.jsonl").stat().st_size < 600_000 and "after trim" in (d / ".critic/runlog.jsonl").read_text()

@test("4.1.1 recheck: PyYAML submodule loaders, a note when the rule limit hits mid-file, wider secret masking")
def _(d):
    write(d, "y.py", "import yaml\nfrom yaml.loader import SafeLoader\nyaml.load(s, Loader=SafeLoader)\n"
                     "yaml.load(s, Loader=yaml.cyaml.CSafeLoader)\nyaml.load(s, Loader=yaml.loader.FullLoader)\n")
    for i in range(11): write(d, f".critic/rules/b{i:02d}.json", json.dumps([{"id": f"b{i:02d}-{j}", "severity": "NOTE", "area": "perf", "pattern": "zzz", "message": "m"} for j in range(190)]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    assert sorted(r["where"] for r in rows if r["rule"] == "py-yaml-load") == ["y.py:5"], rows
    assert "stopped partway through b10.json" in " ".join(r["what"] for r in rows if r["rule"] == "rule-file-limit")
    sys.path.insert(0, str(S)); import critic_findings
    v = "EXAMPLE" + "value9"
    for line in (f"AWS_SECRET_ACCESS_KEY={v}", f'SECRET_KEY="{v}"', f'--password "{v} 2"', f"mysql -p{v}", f"curl -u bob:{v} x",
                 f"Cookie: sid={v}", f"--api-key={v}"):
        assert v not in critic_findings.redact_secrets(line), line
    for line in ('pytest -k "token and not slow"', "npx serve -p 3000"):
        assert critic_findings.redact_secrets(line) == line, line

@test("outside reviewer: blind brief without credentials, pasted answer repaired, one extra vote, outside-only findings always verified")
def _(d):
    write(d, "src/app.js", APP)
    g = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True)
    g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("add", "-A"); g("commit", "-qm", "add render")
    g("remote", "add", "origin", "https://bob:" + "EXAMPLEpw77" + "@github.com/o/r.git")
    run(S / "critic_map.py", "--files", "src/app.js", cwd=d); run(S / "critic_ledger.py", "start", "review", cwd=d)
    write(d, ".critic/reviews/review-A.json", json.dumps([finding()]))
    r = run(S / "critic_outside.py", "brief", cwd=d); assert r.returncode == 0, r.stderr
    b = (d / ".critic/outside/brief.md").read_text(); head = g("rev-parse", "HEAD").stdout.strip()
    assert "EXAMPLEpw77" not in b and "bob" not in b and f"raw.githubusercontent.com/o/r/{head}/src/app.js" in b, b
    assert "innerHTML" not in b and "review-A" not in b and "isn't pushed" in b  # blind: none of our findings, and the push warning
    ours = finding(impact="High", verified="reproduced")
    other = finding(category="domain", impact="Low", line=4, quote="const price = total * 1.0825;", title="Tax rate hard-coded", verified="reproduced")
    wrong = finding(category="perf", impact="Medium", line=1, quote="this line is not in the file", title="Made up")
    ans = "A. ...\n```json\n" + json.dumps([dict(x, id=f"N{i}", evidence="see code \u3010turn1view0\u3011") for i, x in enumerate((ours, other, wrong), 1)]).replace('"N1"', "\u201cN1\u201d") + "\n```\nD. prose"
    write(d, ".critic/outside/answer.txt", ans)
    r = run(S / "critic_outside.py", "load", ".critic/outside/answer.txt", cwd=d); assert r.returncode == 0 and "3 finding(s)" in r.stdout, r.stdout + r.stderr
    rows = json.loads((d / ".critic/outside/outside-review.json").read_text())
    assert all(x["verified"] == "traced" and x["claimed_verified"] in ("reproduced", "traced") and "\u3010" not in x["evidence"] for x in rows), rows
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", "--outside", ".critic/outside/outside-review.json", cwd=d); assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text())
    assert t["outside"] == {"file": ".critic/outside/outside-review.json", "raised": 3, "accepted": 2, "lines_corrected": 0, "matched_ours": 1, "only_outside": 1}, t["outside"]
    agreed = [f for f in t["kept"] if f["title"] == "Title rendered as HTML"]; assert agreed and agreed[0]["votes"] == 2 and agreed[0]["of"] == 2, t["kept"]
    solo = [f for f in t["contested"] if f.get("outside_only")]; assert len(solo) == 1 and solo[0]["impact"] == "Low", t["contested"]
    assert (d / ".critic/verify" / f"{solo[0]['id']}.json").exists() and "outside" not in (d / ".critic/verify" / f"{solo[0]['id']}.json").read_text()
    assert any("Made up" in x["finding"]["title"] for x in t["retracted"])
    write(d, "v.json", json.dumps([{"id": solo[0]["id"], "verdict": "confirmed", "reproduced": "traced"}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    c = (d / ".critic/counts.md").read_text(); assert "## Outside reviewer" in c and solo[0]["id"] in c, c
    assert run(S / "critic_outside.py", "load", "missing.txt", cwd=d).returncode != 0
    write(d, "empty.txt", "```json\n[]\n```"); assert "0 finding(s)" in run(S / "critic_outside.py", "load", "empty.txt", cwd=d).stdout

@test("outside reviewer hardening: can't lower our impact, can't merge two of ours, can't point outside the project, survives real pastes")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    a1, a2 = finding(), finding(line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    write(d, ".critic/reviews/review-A.json", json.dumps([a1, a2])); write(d, ".critic/reviews/review-B.json", "[]"); write(d, ".critic/reviews/review-C.json", "[]")
    low = dict(finding(impact="Low"), id="N1")                                    # agrees with our Critical, rates it Low
    bridge = dict(finding(impact="Low", line=3, quote="e", title="x"), id="N2")  # a one-letter quote that matches both of ours
    away = dict(finding(file="/etc/passwd", line=1, quote="root"), id="N3")
    away2 = dict(finding(file="../outside.js", line=1, quote="x"), id="N4")
    odd = dict(finding(category="perf", impact="Medium", line=1, quote="function render(n) {", title=["not", "text"]), id="N5")
    tmpl = {"id": "N1", "impact": "Critical | High | Medium | Low", "category": "short category", "file": "path/to/file", "line": 123, "quote": "", "title": "t"}
    ans = ("Here is the brief I was given:\n```json\n" + json.dumps([tmpl]) + "\n```\nA. Inspection record\n" + json.dumps({"files_read": []}) +
           "\nB. Recheck\n" + json.dumps([{"id": "G1", "status": "fixed", "file": "src/app.js"}]) + "\nC. New findings\n" + json.dumps([low, bridge]) +
           "\nmore findings:\n```JSON\n" + json.dumps([away, away2, odd]) + "\n```\n")
    write(d, ".critic/outside/answer.txt", ans)
    r = run(S / "critic_outside.py", "load", ".critic/outside/answer.txt", cwd=d); assert r.returncode == 0, r.stderr
    assert "3 finding(s)" in r.stdout and "outside this project" in r.stdout and "not Critical, High, Medium or Low" in r.stdout, r.stdout
    rows = json.loads((d / ".critic/outside/outside-review.json").read_text())
    assert [x["outside_id"] for x in rows] == ["N1", "N2", "N5"] and rows[2]["title"] == '["not", "text"]', rows
    rows.append(dict(away, source="outside", verified="traced")); write(d, ".critic/outside/outside-review.json", json.dumps(rows))  # tally refuses it even if load were bypassed
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", ".critic/reviews/review-B.json", ".critic/reviews/review-C.json", "--outside", ".critic/outside/outside-review.json", cwd=d)
    assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text()); allf = t["kept"] + t["contested"]
    xss = [f for f in allf if f["title"] == "Title rendered as HTML"]; tax = [f for f in allf if f["title"] == "Tax rule in render code"]
    assert xss and xss[0]["impact"] == "Critical" and (d / ".critic/verify" / f"{xss[0]['id']}.json").exists(), allf
    assert tax, "an outside finding merged two of our findings and one disappeared"
    assert any("outside the project" in " ".join(x["why"]) for x in t["rejected"]), t["rejected"]
    assert not any("passwd" in v.read_text() for v in (d / ".critic/verify").glob("*.json"))
    r = run(S / "critic_merge.py", "apply", str(write(d, "v.json", "[]")), cwd=d)
    assert r.returncode == 0 and (d / ".critic/counts.md").exists(), r.stderr

@test("outside brief: unstaged edits to the first file warned, subfolder links and odd names encoded, .critic exposure warned")
def _(d):
    g = lambda *a, cwd=d: subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    write(d, "web/a b#1.js", "let x = 1;\n"); write(d, "web/z.js", "let y = 2;\n")
    g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("add", "-A"); g("commit", "-qm", "one")
    g("remote", "add", "origin", "git@github.com:o/r.git")
    write(d, "web/a b#1.js", "let x = 3;\n")  # unstaged edit to the first file in the change
    w = d / "web"
    run(S / "critic_map.py", "--files", "a b#1.js", "z.js", cwd=w)
    r = run(S / "critic_outside.py", "brief", cwd=w); assert r.returncode == 0, r.stderr
    b = (w / ".critic/outside/brief.md").read_text(); head = g("rev-parse", "HEAD").stdout.strip()
    assert "edits that aren't committed" in b, b
    assert f"https://raw.githubusercontent.com/o/r/{head}/web/a%20b%231.js" in b and f"/{head}/web/z.js" in b, b
    assert "leave .critic/ out" in b, b

@test("4.1.1 double-blind fixes: one spot-check item per id, downgrades counted apart, masking, tracked log, scope-safe aliases, limit notes")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    write(d, "a.json", json.dumps([finding(impact="High", verified="executed")])); run(S / "critic_merge.py", "tally", "a.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "downgrade", "impact_after": "Medium", "reproduced": "traced", "note": "bounded"}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    for _ in range(5):  # the downgraded finding is still Medium: it must never be listed twice
        run(S / "critic_ledger.py", "spotcheck", cwd=d)
        pend = json.loads((d / ".critic/ledger.json").read_text())["spotcheck_pending"]
        assert len({x["id"] for x in pend}) == len(pend), pend
    out = run(S / "critic_ledger.py", "spotcheck", "answer", fid, "real", cwd=d).stdout
    assert "0 of 0 drops removed a real bug, 1 of 1 downgrades lowered a real bug" in out, out
    sys.path.insert(0, str(S)); import critic_findings
    v = "EXAMPLE" + "value9"
    for line in (f"Cookie: a=1; sid={v}", f"DB_PASS={v} npm test", f'{{"password":"{v}"}}', f"sshpass -p {v} ssh h", f"redis-cli -a {v} ping",
                 f"https://{v}ghtoken@github.com/x", f"https://b.example/k?X-Amz-Signature={v}&X-Amz-Date=1", f"--password {v}", f"Authorization: token {v}",
                 f"PGPASSWORD={v} psql", f"dbPassword={v}", f"accessToken={v}", f"clientSecret={v}", f"//registry.npmjs.org/:_authToken={v}", f"pass=a,{v}"):
        assert v not in critic_findings.redact_secrets(line), line
    for line in ('pytest -k "token production path"', "gcc -pthread x.c", "git log --author=bob", "critic_scan.py . --session-dir /tmp/x", "find . -path ./x -prune",
                 "docker run --sig-proxy=false x", "--signature-check=yes", "git clone ssh://deployuser@host/r", "bypass=1"):
        assert critic_findings.redact_secrets(line) == line, line
    t0 = time.time(); critic_findings.redact_secrets("a-" * 4000); assert time.time() - t0 < 1
    e = d / "e"; e.mkdir(); write(e, ".critic/.gitignore", "scan/\n")
    critic_findings.log_run(e, "script", "x"); gi = (e / ".critic/.gitignore").read_text()
    assert "scan/" in gi and "runlog.jsonl" in gi and "restore/" in gi, gi
    g = lambda *a: subprocess.run(["git", *a], cwd=e, capture_output=True, text=True)
    g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("add", "-f", ".critic/runlog.jsonl"); g("commit", "-qm", "tracked log")
    before = (e / ".critic/runlog.jsonl").read_text()
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(S)!r}); import critic_findings as c; c.log_run({str(e)!r}, 'script', 'secret run')"], capture_output=True, text=True)
    assert (e / ".critic/runlog.jsonl").read_text() == before and "tracked by git" in r.stderr, r.stderr
    write(d, "y.py", "import subprocess as sp\ndef helper():\n    import os as sp\ndef go(c):\n    sp.run(c, shell=True)\n"
                     "import yaml\ntry:\n    from yaml import CLoader as L\nexcept ImportError:\n    from yaml import SafeLoader as L\nyaml.load(s, Loader=L)\n"
                     "from builtins import eval\neval(x)\nfrom tempfile import *\np = mktemp()\n")
    write(d, "z.py", "from yaml import *\nimport yaml\nyaml.load(s, Loader=SafeLoader)\n")
    write(d, ".critic/rules/aaa.json", json.dumps([{"id": f"bad{i}"} for i in range(25)]))
    write(d, ".critic/rules/project rule trick.json", json.dumps([{"id": f"bad{i}"} for i in range(25)]))
    for i in range(55): write(d, f".critic/rules/x{i:02d}.json", json.dumps([{"id": f"r{i:02d}", "severity": "NOTE", "area": "perf", "pattern": "zzz", "message": "m"}]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    got = sorted((r["rule"], r["where"]) for r in rows if r["rule"].startswith("py-") and r["where"].startswith("y.py"))
    assert got == [("py-eval", "y.py:13"), ("py-mktemp", "y.py:15"), ("py-shell-true", "y.py:5"), ("py-yaml-load", "y.py:11")], got
    assert any(r["rule"] == "rule-file-limit" and "50 files" in r["what"] for r in rows), [r for r in rows if r["rule"].startswith("rule-file")]
    assert all(r["rule"] != "rule-file-limit" or "trick" not in r["what"] for r in rows) and not any(r["where"].startswith("z.py") for r in rows if r["rule"] == "py-yaml-load")

@test("outside reviewer: a long quote cited at the wrong line is moved to its one real line; a repeated or short one is not")
def _(d):
    write(d, "src/app.js", APP + "\n" * 30 + "list.innerHTML = `<li>${n.title}</li>`;\n"); run(S / "critic_ledger.py", "start", "review", cwd=d)
    write(d, "r.json", "[]")
    far = dict(finding(category="domain", impact="Medium", line=30, quote="const price = total * 1.0825;", title="Tax rate"), source="outside", outside_id="N1")
    twice = dict(finding(impact="Medium", line=18, title="dup"), source="outside", outside_id="N2")  # the innerHTML line is in the file twice
    write(d, "o.json", json.dumps([far, twice]))
    run(S / "critic_merge.py", "tally", "r.json", "--outside", "o.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    moved = [f for f in t["contested"] if f["title"] == "Tax rate"]
    assert moved and moved[0]["line"] == 4 and moved[0]["line_cited"] == 30, t["contested"]
    assert any(x["finding"]["title"] == "dup" for x in t["retracted"]) and t["outside"]["lines_corrected"] == 1, t

@test("outside reviewer round 3: subfolder edits warned with the default map, curly answers after a template, short quotes never attach, outside-only agreement still verified")
def _(d):
    g = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True)
    write(d, "web/src/app.js", APP)
    g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("add", "-A"); g("commit", "-qm", "one")
    write(d, "web/src/app.js", APP + "// more\n"); g("add", "-A"); g("commit", "-qm", "two"); write(d, "web/src/app.js", APP + "// more\n// unstaged\n")
    w = d / "web"; run(S / "critic_map.py", cwd=w)  # the default change map: paths from the repository top
    run(S / "critic_outside.py", "brief", cwd=w); b = (w / ".critic/outside/brief.md").read_text()
    assert "edits that aren't committed" in b, b
    write(w, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=w)
    tmpl = {"id": "N1", "impact": "Critical | High | Medium | Low", "category": "c", "file": "path/to/file", "line": 1, "quote": "", "title": "t"}
    real = json.dumps([dict(finding(impact="High"), id="N1")]).replace('"', "\u201c", 1)  # one curly quote breaks straight parsing
    write(w, "ans.txt", "```json\n" + json.dumps([tmpl]) + "\n```\n" + real.replace('"', "\u201d"))
    r = run(S / "critic_outside.py", "load", "ans.txt", cwd=w); assert "1 finding(s)" in r.stdout, r.stdout + r.stderr
    ours = finding(category="domain", impact="Low", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    write(w, "a.json", json.dumps([ours])); write(w, "b.json", "[]"); write(w, "c.json", "[]")
    unrelated = dict(finding(category="domain", impact="High", line=4, quote="n", title="Price shown without a currency symbol"), source="outside", outside_id="N9")
    agrees = dict(finding(category="domain", impact="Low", line=4, quote="const price = total * 1.0825;", title="Hard-coded tax rule"), source="outside", outside_id="N8")
    write(w, "o.json", json.dumps([unrelated])); run(S / "critic_merge.py", "tally", "a.json", "b.json", "c.json", "--outside", "o.json", cwd=w)
    t = json.loads((w / ".critic/tally.json").read_text())
    assert any(f.get("outside_only") and f["impact"] == "High" for f in t["contested"]), t  # the one-letter quote did not attach it to ours
    write(w, "o.json", json.dumps([agrees])); run(S / "critic_merge.py", "tally", "a.json", "b.json", "c.json", "--outside", "o.json", cwd=w)
    t = json.loads((w / ".critic/tally.json").read_text()); k = [f for f in t["kept"] if f["title"] == "Tax rule in render code"]
    assert k and k[0]["votes"] == 2 and k[0]["votes_ours"] == 1 and (w / ".critic/verify" / f"{k[0]['id']}.json").exists(), t

@test("4.2.0 self-review fixes: unverified outside-only findings held back, .critic paths rejected, deep pastes, ssh remotes, tracked .gitignore, masking")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=d)
    write(d, ".critic/reviews/review-A.json", json.dumps([finding(impact="Low", verified="traced", category="domain", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")]))
    write(d, ".critic/reviews/review-B.json", "[]"); write(d, ".critic/reviews/review-C.json", "[]")
    inv = dict(finding(impact="High", title="Invented by the outside AI", category="perf"), source="outside", outside_id="N1")
    peek = dict(finding(impact="High", file=".critic/reviews/review-A.json", line=1, quote='"verified": "traced"', title="peek"), source="outside", outside_id="N2")
    write(d, "o.json", json.dumps([inv, peek]))
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", ".critic/reviews/review-B.json", ".critic/reviews/review-C.json", "--outside", "o.json", cwd=d); assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text())
    assert any(".critic" in " ".join(x["why"]) or "outside the project" in " ".join(x["why"]) for x in t["rejected"]), t["rejected"]
    assert not any("review-A" in v.read_text() for v in (d / ".critic/verify").glob("*.json"))
    run(S / "critic_merge.py", "apply", str(write(d, "v.json", "[]")), cwd=d)  # no verdicts came back
    final = [json.loads(l) for l in (d / ".critic/findings.jsonl").read_text().splitlines()]
    assert not any(f["title"] == "Invented by the outside AI" for f in final), final
    assert "Outside findings not verified" in (d / ".critic/counts.md").read_text()
    write(d, "deep.txt", "[" * 3000 + "\n" + json.dumps([dict(finding(), id="N1")]))
    r = run(S / "critic_outside.py", "load", "deep.txt", cwd=d); assert r.returncode == 0 and "1 finding(s)" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr
    many = [dict(finding(line=2, title=f"t{i}"), id=f"N{i}") for i in range(150)]
    write(d, "many.txt", json.dumps(many) + "\n\u201cstray\u201d"); r = run(S / "critic_outside.py", "load", "many.txt", cwd=d)
    assert "150 finding(s)" in r.stdout and "over the limit" not in r.stdout, r.stdout
    sys.path.insert(0, str(S)); import critic_outside, critic_findings
    assert critic_outside.public_url("ssh://git@github.com:443/o/r.git") == "https://github.com/o/r" and critic_outside.public_url("https://github.com/o/r/") == "https://github.com/o/r"
    assert critic_outside.is_github("https://github.com/o/r") and not critic_outside.is_github("https://evil.example/github.com/o")
    v = "EXAMPLE" + "value9"
    for line in (f'curl --cookie "sid={v}" https://a', f"curl -b sid={v} x", f"SESSION={v}", f"--token {v}", f"accessToken={v}"):
        assert v not in critic_findings.redact_secrets(line), line
    for line in ("pytest --auth-type basic", "node run.js --max-tokens 4096", "--tokenizer gpt2", "docker login --password-stdin < pw.txt", "--token-count 5"):
        assert critic_findings.redact_secrets(line) == line, line
    e = d / "e"; write(e, ".critic/.gitignore", "scan/\n"); write(e, "x.txt", "x")
    g = lambda *a: subprocess.run(["git", *a], cwd=e, capture_output=True, text=True)
    g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("add", "-A"); g("commit", "-qm", "tracked ignore")
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(S)!r}); import critic_findings as c; c.log_run({str(e)!r}, 'script', 'x')"], capture_output=True, text=True)
    assert (e / ".critic/.gitignore").read_text() == "scan/\n" and "left alone" in r.stderr, r.stderr

@test("4.2.2 R-1: --mutate never runs a test command from a cloned repo's rules.md without --project-checks")
def _(d):
    marker = d / "RAN_FROM_RULES_MD"
    write(d, "m.js", "function f(a, b) { return a < b; }\nmodule.exports = f;\n")
    write(d, ".critic/rules.md", f"# Rules\nTest command: touch {marker}\n")
    run(S / "critic_scan.py", ".", "--root", ".", "--mutate", "m.js", cwd=d)
    assert not marker.exists(), "the rules.md test command ran without consent"
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert rep["checks"]["mutation"]["state"] == "blocked" and "--project-checks" in rep["checks"]["mutation"]["note"], rep["checks"]["mutation"]
    run(S / "critic_scan.py", ".", "--root", ".", "--mutate", "m.js", "--project-checks", cwd=d)
    assert marker.exists(), "with --project-checks (the user approved rules.md) the command should run"
    marker.unlink(); write(d, ".critic/rules.md", "# Rules\n")
    run(S / "critic_scan.py", ".", "--root", ".", "--mutate", "m.js", "--test-cmd", f"touch {marker}", cwd=d)
    assert marker.exists(), "a command the user typed with --test-cmd should run"

@test("4.2.2 N-1: reviews left over from an earlier run are never counted as votes")
def _(d):
    write(d, "src/app.js", APP)
    f = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([f]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    assert json.loads((d / ".critic/tally.json").read_text())["kept"][0]["votes"] == 3
    run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    left = sorted(p.name for p in (d / ".critic/reviews").glob("review-*.json")) if (d / ".critic/reviews").exists() else []
    assert left == [], f"start left the last run's reviews in place: {left}"
    assert sorted(p.name for p in (d / ".critic/history").rglob("review-*.json")) == ["review-A.json", "review-B.json", "review-C.json"]
    write(d, ".critic/reviews/review-A.json", "[]")
    write(d, ".critic/reviews/review-B.json", json.dumps([f])); old = time.time() - 3600; os.utime(d / ".critic/reviews/review-B.json", (old, old))
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", ".critic/reviews/review-B.json", cwd=d)
    assert r.returncode != 0 and "earlier run" in (r.stdout + r.stderr), r.stdout + r.stderr
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d)
    assert json.loads((d / ".critic/tally.json").read_text())["kept"] == []

@test("4.2.2 N-4: a secret a reviewer quotes is redacted everywhere Curmudgeon writes it, and raw files are git-ignored")
def _(d):
    key = FAKE["@LIVE@"]
    write(d, "app.py", f'import os\nSTRIPE_KEY = "{key}"\n')
    f = finding(category="secret", impact="Critical", file="app.py", line=2, quote=f'STRIPE_KEY = "{key}"', title=f"Live key {key} in source",
                evidence=f"app.py:2 holds {key}", failing_case=f"anyone with the repo can charge cards with {key}", remediation="move to env, rotate")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([f]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert [x["title"].startswith("Live key") for x in t["kept"]] == [True], "the quote check must still pass on the raw quote"
    fid = t["kept"][0]["id"]
    sys.path.insert(0, str(S)); import critic_findings
    assert fid == critic_findings.fingerprint(dict(f, line=2)), "ids are computed from the raw quote, so they stay stable across versions"
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "confirmed", "reproduced": "traced", "note": f"traced: {key} is live"}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    leaks = [str(p.relative_to(d)) for p in (d / ".critic").rglob("*") if p.is_file() and not p.is_relative_to(d / ".critic/reviews")
             and key in p.read_text(errors="replace")]
    assert leaks == [], f"secret written unredacted to {leaks}"
    gi = (d / ".critic/.gitignore").read_text().split()
    for must in ("reviews/", "history/", "outside/", "verify/", "tally.json", "dedup-candidates.json", "findings-import.jsonl"):
        assert must in gi, f"{must} is not git-ignored: {gi}"
    L_ = json.loads((d / ".critic/ledger.json").read_text())["findings"][fid]
    assert "[redacted]" in L_["quote"]
    r = run(S / "critic_ledger.py", "acted", cwd=d)
    assert "acted_on" not in json.loads((d / ".critic/ledger.json").read_text())["findings"][fid], "a redacted quote can't prove the code is gone"

@test("4.2.2 N-13: a live URL can't pass as local through user@host, and IPv6 loopback is accepted")
def _(d):
    write(d, "index.html", "<!doctype html><title>t</title>")
    def page_note(url):
        run(S / "critic_scan.py", ".", "--root", ".", "--page", url, cwd=d)
        return json.loads((d / ".critic/scan/report.json").read_text())["checks"]["page"]["note"]
    for bad in ("http://127.0.0.1:80@evil.example/", "http://localhost@evil.example/x", "http://user:pw@127.0.0.1.evil.example/"):
        assert "live URL refused" in page_note(bad), bad
    for ok in ("http://[::1]:8000/", "http://LOCALHOST:8000/", "http://127.0.0.1:8000/"):
        assert "live URL refused" not in page_note(ok), ok

@test("4.2.2 small fixes: no stale critic names, all four hooks listed, honest benchmark, grammar, override list")
def _(d):
    import re as re_
    for p in list((HERE / "agents").glob("*.md")) + [HERE / "skills/review/references/output-contract.md"]:
        t = p.read_text()
        assert not re_.search(r"(?i)\bthe critic skill\b|\(critic skill|[\s\"`(]/critic[\s`)]", t), p.name
    readme = (HERE / "README.md").read_text(); top = (HERE.parent / "README.md").read_text()
    assert readme == top, "the two README copies differ"
    assert "stop_async" in readme or "background re-scan" in readme.lower(), "the fourth hook (background re-scan) is missing"
    assert "Each review used three blind reviewers" not in readme
    assert "30%" in readme and "contract" in readme.lower()
    assert "The scripted checks measures" not in (HERE / "skills/review/references/sandbox.md").read_text()
    assert "Playwright MCP" not in (HERE / "skills/review/references/sandbox.md").read_text()
    run(S / "critic_ledger.py", "start", "review", cwd=d)
    r = run(S / "critic_ledger.py", "override", "gate", "Curmudgeon", "skip", cwd=d)
    assert r.returncode != 0 and "owner" in r.stderr, r.stdout + r.stderr

if __name__ == "__main__":
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} passed"); sys.exit(1 if bad else 0)
