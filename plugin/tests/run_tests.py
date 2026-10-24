#!/usr/bin/env python3
"""Tests for Curmudgeon's scripts. No test framework needed: python3 tests/run_tests.py (exit 1 on any failure).
Each test builds its own scratch project in a temp folder and runs the real scripts against it."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent.parent
S = HERE / "skills" / "review" / "scripts"; H = HERE / "hooks"
RESULTS = []
TMP = tempfile.mkdtemp(prefix="critic-tmp-")  # the hooks' TMPDIR, so agent workspaces made by tests are removed with it

def run(script, *a, cwd, stdin=None, env=None):
    e = dict(os.environ, CRITIC_ROOT=str(cwd), TMPDIR=TMP); e.update(env or {})
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
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "refutation": "not real"}])); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert (d / ".critic/findings.jsonl").read_text().strip(), "a vague refutation dropped the finding"
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "traced", "refutation": "render() receives titles only from the escaped constant at src/app.js:4, so no user text ever reaches this line."}]))
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
    assert ch["page"]["state"] == "n/a"  # no --page given: nothing to look at (5.0 SC-8; it was "blocked")

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
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "refutation": "I do not think this is a problem because it seems fine to me overall here."}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d); assert (d / ".critic/findings.jsonl").read_text().strip()
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "traced", "refutation": "Titles reach render() only through escapeTitle() at src/app.js:1, so no markup survives."}]))
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
    msg = lambda why: "```json\n" + json.dumps([{"id": "F-1", "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "executed", "refutation": why}]) + "\n```"
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
    write(d, "v.json", json.dumps([{"id": ids[1], "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "traced", "refutation": why}]))
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
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "executed", "refutation": why}]))
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
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "executed", "refutation": why}]))
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

@test("4.2.2 review round 1: refutations are masked in counts.md and the ledger, code isn't mangled, round 2 never counts round 1")
def _(d):
    key = FAKE["@LIVE@"]
    write(d, "app.py", f'import os\nSTRIPE_KEY = "{key}"\nif os.environ.get("CI"): STRIPE_KEY = None\n')
    f = finding(category="secret", impact="High", file="app.py", line=2, quote=f'STRIPE_KEY = "{key}"', title="Live key in source")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([f]))
    reviews = [f".critic/reviews/review-{L}.json" for L in "ABC"]
    run(S / "critic_merge.py", "tally", *reviews, cwd=d); fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v1.json", json.dumps([{"id": fid, "verdict": "confirmed", "reproduced": "traced", "note": "traced"}])); run(S / "critic_merge.py", "apply", "v1.json", cwd=d)
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([f]))
    run(S / "critic_merge.py", "tally", *reviews, cwd=d)
    write(d, "v2.json", json.dumps([{"id": fid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "executed",
          "refutation": f"The value {key} at app.py:2 is replaced by None at app.py:3 in every CI build, so it never ships."}]))
    run(S / "critic_merge.py", "apply", "v2.json", cwd=d)
    leaks = [str(p.relative_to(d)) for p in (d / ".critic").rglob("*") if p.is_file() and not (p.is_relative_to(d / ".critic/reviews") or p.is_relative_to(d / ".critic/history"))
             and key in p.read_text(errors="replace")]
    assert leaks == [], f"refutation text leaked the secret to {leaks}"
    sys.path.insert(0, str(S)); import importlib, critic_findings; importlib.reload(critic_findings)
    for code in ('if (session.token == req.headers.authorization) { return true; }', 'session_id = uuid4().hex', 'password = request.form.get("password")',
                 'api_key: str = Field(default=None)', 'see plugin/skills/review/scripts/critic_merge.py:339'):
        assert critic_findings.redact_finding_text(code) == code, f"ordinary code was masked: {critic_findings.redact_finding_text(code)}"
    hexkey = "a8f5f167" + "f44f4964e6c998dee827110c"
    assert hexkey not in critic_findings.redact_finding_text(f"Hard-coded key {hexkey} in config"), "an unnamed high-randomness key in prose must be masked"
    e = d / "r2"; write(e, "src/app.js", APP)
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    for L in "ABC": write(e, f".critic/reviews/review-{L}.json", json.dumps([g]))
    run(S / "critic_ledger.py", "round", cwd=e)
    left = sorted(p.name for p in (e / ".critic/reviews").glob("review-*.json"))
    assert left == [], f"round 2 kept round 1's reviews in place: {left}"
    write(e, ".critic/reviews/review-A.json", "[]")
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=e)
    assert json.loads((e / ".critic/tally.json").read_text())["kept"] == []

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

@test("4.2.2 review round 1: a .critic/ review file git already tracks is named in a warning, with the command to untrack it")
def _(d):
    subprocess.run(["git", "init", "-q"], cwd=d)
    write(d, ".critic/reviews/review-A.json", "[]"); write(d, "src/a.py", "x = 1\n")
    subprocess.run(["git", "add", "-f", ".critic/reviews/review-A.json", "src/a.py"], cwd=d)
    r = run(S / "critic_ledger.py", "init", cwd=d)
    assert "git tracks 1 .critic/ file" in r.stderr and ".critic/reviews/review-A.json" in r.stderr, r.stderr
    assert "git rm -r --cached .critic/reviews" in r.stderr, r.stderr
    d2 = d / "clean"; d2.mkdir(); subprocess.run(["git", "init", "-q"], cwd=d2)
    r = run(S / "critic_ledger.py", "init", cwd=d2); assert "git tracks" not in r.stderr, r.stderr

@test("4.2.2 review round 2: named passwords stay masked, ordinary names and paths aren't, unnamed random keys are")
def _(d):
    import random, string
    sys.path.insert(0, str(S)); import importlib, critic_findings; importlib.reload(critic_findings); r = critic_findings.redact_finding_text
    pw = "hun" + "ter2Xq9"
    for s in (f"DATABASE_PASSWORD={pw}", f"password: {pw}", f'"password": "{pw}"', f"Authorization: Bearer {pw}abc", f"curl -u admin:{pw} https://x",
              f"mysql -p{pw} db", f"redis-cli -a {pw}", f"Cookie: sid={pw}", f"--password {pw}", f"postgres://u:{pw}@h/db", f"token = '{pw}'"):
        assert pw not in r(s), f"a named password was left in: {r(s)}"
    for s in ("password = form.password", "cookies = req.cookies", 'token = request.headers.get("X-Token")', "auth = HTTPBasicAuth(user, pw)",
              "password = new_password", "password: str", "see commit 3f2a9c1d4e5b6a7980f1e2d3c4b5a6978e1f2d3c in history",
              "test_user_login_returns_401_after_3_failed_attempts", "db/migrate/20241024123456_add_users_table.rb:12", "x86_64-unknown-linux-gnu-gcc",
              "aarch64-apple-darwin23-clang15", "handleOAuth2CallbackForIOS17AndAndroid14", "sha256WithRSAEncryption2048", "ISO8601_UTC_TIMESTAMP_FORMAT_2024",
              "550e8400-e29b-41d4-a716-446655440000", "DocXMLRPCRequestHandler", "MAX_RETRY_BACKOFF_SECONDS_300"):
        assert r(s) == s, f"ordinary text was masked: {s} -> {r(s)}"
    rnd = random.Random(5); A = string.ascii_letters + string.digits
    keys = ["".join(rnd.choice(A) for _ in range(32)) for _ in range(200)] + ["".join(rnd.choice(A + "+/") for _ in range(40)) for _ in range(100)]
    missed = sum(1 for k in keys if k in r(f"the value {k} is used"))
    assert missed <= 9, f"{missed} of {len(keys)} unnamed random keys were left in"
    write(d, "config/app.env", f"DB_HOST=localhost\nDATABASE_PASSWORD={pw}\n")
    f = finding(category="secret", impact="High", file="config/app.env", line=2, quote=f"DATABASE_PASSWORD={pw}", title="Database password committed")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([f]))
    reviews = [f".critic/reviews/review-{L}.json" for L in "ABC"]
    run(S / "critic_merge.py", "tally", *reviews, cwd=d); fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, "v.json", json.dumps([{"id": fid, "verdict": "confirmed", "reproduced": "traced", "note": f"DATABASE_PASSWORD={pw} is read at boot"}]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    leaks = [str(p.relative_to(d)) for p in (d / ".critic").rglob("*") if p.is_file() and not (p.is_relative_to(d / ".critic/reviews") or p.is_relative_to(d / ".critic/history"))
             and pw in p.read_text(errors="replace")]
    assert leaks == [], f"a named password leaked to {leaks}"

@test("4.2.2 review round 2: a refutation is judged on its raw text, so masking can't turn a real file:line into 'no location'")
def _(d):
    reviews = [f".critic/reviews/review-{L}.json" for L in "ABC"]
    e = d / "mig"; write(e, "db/migrate/20241024123456_add_users_table.rb", "class AddUsers\n  def change\n    add_index :users, :email, unique: true\n  end\nend\n")
    write(e, "app/models/user.rb", "class User\n  def find(e)\n    where(email: e).first\n  end\nend\n")
    g = finding(category="performance", impact="Medium", file="app/models/user.rb", line=3, quote="    where(email: e).first", title="Lookup by email has no index")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    for L in "ABC": write(e, f".critic/reviews/review-{L}.json", json.dumps([g]))
    run(S / "critic_merge.py", "tally", *reviews, cwd=e); gid = json.loads((e / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(e, "v.json", json.dumps([{"id": gid, "verdict": "refuted", "attacker": "an outside user", "gain": "nothing", "reason": "guard_blocks", "reproduced": "traced",
          "refutation": "The users.email column has a unique index from db/migrate/20241024123456_add_users_table.rb:3, so the lookup is indexed."}]))
    out = run(S / "critic_merge.py", "apply", "v.json", cwd=e).stdout
    assert "refuted 1" in out, f"a valid refutation citing a real migration file was not accepted: {out}"

@test("4.2.2 review round 2: round --reset can repeat a round label, and the earlier archive is never overwritten")
def _(d):
    h = d / "arch"; write(h, "src/a.py", "x = 1\n")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=h)
    write(h, ".critic/reviews/review-A.json", '["v1"]'); run(S / "critic_ledger.py", "round", cwd=h)
    write(h, ".critic/reviews/review-A.json", '["v2"]'); run(S / "critic_ledger.py", "round", "--reset", cwd=h); run(S / "critic_ledger.py", "round", cwd=h)
    write(h, ".critic/reviews/review-A.json", '["v3"]'); run(S / "critic_ledger.py", "round", cwd=h)
    kept = sorted(p.read_text() for p in (h / ".critic/history").rglob("review-A.json"))
    assert kept == ['["v1"]', '["v2"]', '["v3"]'], f"an archived review was overwritten: {kept}"

@test("4.2.2 review round 3: when in doubt the masking masks (brackets, plain words, Go and PHP forms), and random keys of every case mix are caught")
def _(d):
    import random, string
    sys.path.insert(0, str(S)); import importlib, critic_findings; importlib.reload(critic_findings); r = critic_findings.redact_finding_text
    pw, word = "hun" + "ter2Xq9", "hun" + "ter"
    for s, secret in ((f"DATABASE_PASSWORD=Pa({pw})ss!9", pw), (f"DATABASE_PASSWORD=Pa[{pw}]ss9", pw), (f"POSTGRES_PASSWORD={{{pw}}}", pw),
                      (f"password: Pa0({pw}", pw), (f"password: {word}", word), (f"password = {word}", word), ("password: Correct" + "HorseBatteryStaple", "HorseBattery"),
                      (f'password := "{pw}"', pw), (f"'password' => '{pw}'", pw), (f"SECRET_KEY=<{pw}>", pw), (f"DB_PASS=${pw}", pw)):
        assert secret not in r(s), f"a credential was left in: {s} -> {r(s)}"
    for s in ("API_KEY = settings.API_KEY", "PASSWORD = config.password", "DB_PASSWORD = env.DB_PASSWORD", "password = get_password()",
              "password = params[:password]", "password: Optional[str] = None", "auth = HTTPBasicAuth(user, pw)", "password = newPassword",
              "password: ${DB_PASSWORD}", "uses: actions/checkout@" + "b4ffde65f46336ab88eb53be808477a3936bae11",
              "git checkout " + "b4ffde65f46336ab88eb53be808477a3936bae11", "AES256GCMSHA384CipherSuite", "HTTP2_SETTINGS_MAX_FRAME_SIZE"):
        assert r(s) == s, f"code was masked: {s} -> {r(s)}"
    rnd = random.Random(9); U, L, D = string.ascii_uppercase, string.ascii_lowercase, string.digits
    for alpha, lo, hi, allowed in ((U + D, 20, 40, 8), (L + D, 32, 32, 6), (U + L + D, 20, 40, 10), (L, 20, 40, 25)):
        keys = ["".join(rnd.choice(alpha) for _ in range(rnd.randint(lo, hi))) for _ in range(400)]
        missed = sum(1 for k in keys if k in r(f"the value {k} is used"))
        assert missed <= allowed, f"{missed} of 400 random keys ({alpha[:3]}..., {lo}-{hi} chars) were left in"

@test("5.0 SC-6: rule files read config files (workflows, SQL, TOML, Dockerfiles) only when a rule names them, and other types are listed as not checked")
def _(d):
    write(d, ".github/workflows/ci.yml", "on:\n  pull_request_target:\n    types: [opened]\njobs: {}\n")
    write(d, "db/001.sql", "CREATE INDEX idx_users_email ON users(email);\n"); write(d, "Dockerfile", "FROM node:latest\n")
    write(d, "pyproject.toml", "[tool.x]\nvar = 1\n"); write(d, "notes.txt", "var is fine here\n"); write(d, "src/a.js", "var x = 1;\n")
    write(d, ".critic/rules/ci.json", json.dumps([
        {"id": "prt", "severity": "WARN", "area": "safety", "pattern": "pull_request_target", "message": "fork code can run with secrets", "files": [".github/*", "*.yml"]},
        {"id": "idx", "severity": "NOTE", "area": "perf", "pattern": "CREATE INDEX (?!CONCURRENTLY)", "message": "index locks writes", "files": ["*.sql"]},
        {"id": "latest", "severity": "NOTE", "area": "deps", "pattern": "^FROM \\S+:latest", "message": "unpinned base image", "files": ["Dockerfile*"]},
        {"id": "anyvar", "severity": "NOTE", "area": "perf", "pattern": "\\bvar\\b", "message": "var used"}]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    hits = {(r["rule"], r["where"].split(":")[0]) for r in rep["findings"] if r["rule"].startswith("rule-")}
    for want in [("rule-prt", ".github/workflows/ci.yml"), ("rule-idx", "db/001.sql"), ("rule-latest", "Dockerfile"), ("rule-anyvar", "src/a.js")]:
        assert want in hits, (want, sorted(hits))
    assert ("rule-anyvar", "pyproject.toml") not in hits, "a rule with no file patterns fired on a config file"
    note = rep["checks"]["static"]["note"]
    assert "config files" in note and "not checked beyond secrets: .txt 1" in note, note

@test("5.0 SC-7: mutation touches code only (never strings, docstrings, comments or generics), checks the tests load the file, and runs without bytecode")
def _(d):
    write(d, "lib.py", 'def less(a, b):\n    """True when a < b."""\n    msg = "a > b is false"  # a >= b here\n    return a < b\n')
    write(d, "other.py", "def g(a, b):\n    return a < b\n")
    write(d, "test_lib.py", "import os\nfrom lib import less\nopen('env.txt', 'w').write(os.environ.get('PYTHONDONTWRITEBYTECODE', ''))\n"
                            "assert less(1, 2) and not less(2, 1) and not less(1, 1)\n")
    run(S / "critic_scan.py", ".", "--root", ".", "--mutate", "lib.py", "other.py", "--test-cmd", f"{sys.executable} test_lib.py", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    rows = [r for r in rep["findings"] if r["area"] == "tests"]
    surv = [r for r in rows if r["rule"] == "mutant-survived"]
    assert surv == [], f"a mutant landed in a string, docstring or comment: {surv}"
    assert any(r["rule"] == "mutation-not-exercised" and r["where"] == "other.py" for r in rows), rows
    assert (d / "env.txt").read_text() == "1", "the test command must run with PYTHONDONTWRITEBYTECODE=1"
    assert rep["checks"]["mutation"]["state"] == "pass", rep["checks"]["mutation"]
    assert (d / "lib.py").read_text().endswith("return a < b\n") and not list(d.glob("*.critic-mutation-backup"))
    sys.path.insert(0, str(S)); import importlib, scan_mutation; importlib.reload(scan_mutation)
    import pathlib as _pl
    v = scan_mutation.code_view(_pl.Path("m.ts"), "const xs: Array<string> = [];\nconst s = `a < b ${x}`; // a > b\nif (a < b) go();\n")
    hits = [(i, pat) for i, l in enumerate(v) for pat, _r in scan_mutation.OPS if __import__("re").search(pat, l)]
    assert hits == [(2, r"(?<=\s)<(?=\s)")], hits

@test("5.0 SC-8: a check with nothing to look at is n/a, never DEGRADED, and CI never passes when it read nothing")
def _(d):
    write(d, "src/a.js", "const x = 1;\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert rep["checks"]["ci"]["state"] == "n/a", rep["checks"]["ci"]
    assert rep["checks"]["deps"]["state"] == "n/a", rep["checks"]["deps"]
    assert rep["checks"]["page"]["state"] == "n/a" and rep["degraded"] == [], (rep["checks"]["page"], rep["degraded"])
    assert "DEGRADED" not in (d / ".critic/scan/report.md").read_text()
    write(d, "results.xml", '<testsuite name="t"><testcase classname="a" name="ok"/></testsuite>')
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    ci = json.loads((d / ".critic/scan/report.json").read_text())["checks"]["ci"]
    assert ci["state"] == "pass" and "1 result file" in ci["note"], ci

@test("5.0 SC-9: the structure check maps Python imports (cycles, layers), skips imports inside functions, and is n/a with nothing to map")
def _(d):
    write(d, "app/core/rules.py", "from app.ui import view\n\ndef total(x):\n    return x\n")
    write(d, "app/ui/view.py", "from ..core import rules\n\ndef show():\n    return rules.total(1)\n")
    write(d, "app/ui/__init__.py", ""); write(d, "app/core/__init__.py", ""); write(d, "app/__init__.py", "")
    write(d, "tools/a.py", "import b\n"); write(d, "tools/b.py", "def f():\n    import a\n    return a\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    rules = {(x["rule"], x["where"]) for x in rep["findings"] if x["rule"] in ("import-cycle", "boundary")}
    assert ("import-cycle", "app/core/rules.py") in rules, rules
    assert ("boundary", "app/core/rules.py") in rules, rules
    assert not any(w.startswith("tools/") for _r, w in rules), f"an import inside a function was counted: {rules}"
    assert rep["checks"]["structure"]["state"] == "pass" and "7 modules" in rep["checks"]["structure"]["note"], rep["checks"]["structure"]
    e = d / "html"; write(e, "index.html", "<!doctype html><title>t</title><p>hi</p>")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=e)
    st = json.loads((e / ".critic/scan/report.json").read_text())["checks"]["structure"]
    assert st["state"] == "n/a", st

@test("5.0 SC-10: a scripted FAIL gets its rule's impact (a live key from the real scanner is Critical), and a reviewer who restates it keeps the script's evidence")
def _(d):
    write(d, "src/a.js", "x = 1;\ny = 2;\neval(input);\nz = 3;\n")
    write(d, "src/k.js", 'const k = "@LIVE@";\nconst u = "postgres://app:' + 'Hunter2pw@db/x";\n')
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    g = finding(category="injection", impact="High", file="src/a.js", line=3, quote="eval(input);", title="eval runs user input")
    write(d, ".critic/reviews/review-A.json", json.dumps([g])); write(d, ".critic/reviews/review-B.json", json.dumps([g])); write(d, ".critic/reviews/review-C.json", "[]")
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", ".critic/reviews/review-B.json", ".critic/reviews/review-C.json", "--scan", ".critic/scan/report.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    by = {k["category"]: k for k in t["kept"]}
    assert by["secret-stripe-key"]["impact"] == "Critical", by.get("secret-stripe-key")
    assert by["secret-db-url-password"]["impact"] == "Critical", by.get("secret-db-url-password")
    ev = by["injection"]
    assert ev.get("scan_evidence") and "(eval)" in ev["scan_evidence"][0] and ev["votes"] == 2, ev

@test("5.0 SC-11: the background check scans every changed file in one bounded run, and SubagentStop only fires for reviewers and verifiers")
def _(d):
    subprocess.run(["git", "init", "-q"], cwd=d); write(d, "base.js", "const a = 1;\n")
    subprocess.run(["git", "add", "."], cwd=d); subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base"], cwd=d)
    write(d, ".critic/gate-async", "on\n"); write(d, "src/a.js", "eval(input);\n"); write(d, "src/b.js", "const ok = 1;\n"); write(d, "untouched.js", "eval(x);\n")
    subprocess.run(["git", "add", "untouched.js"], cwd=d); subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "u"], cwd=d)
    r = subprocess.run([sys.executable, str(H / "stop_async.py")], input=json.dumps({"cwd": str(d)}), capture_output=True, text=True, cwd=d)
    assert r.returncode == 2 and "src/a.js" in r.stderr and "untouched.js" not in r.stderr, (r.returncode, r.stderr)
    dirs = sorted(p.name for p in (d / ".critic/scan-async").iterdir())
    assert dirs == ["all"], f"expected one scan for all changed files, got {dirs}"
    src = (H / "stop_async.py").read_text()
    assert "timeout=10" in src and "DEADLINE" in src, "git calls and the whole check must be time-limited"
    hooks = json.loads((H / "hooks.json").read_text())["hooks"]
    m = hooks["SubagentStop"][0].get("matcher", "")
    import re as _re
    assert _re.fullmatch(m, "curmudgeon:curmudgeon-reviewer") and _re.fullmatch(m, "curmudgeon-verifier") and not _re.fullmatch(m, "general-purpose"), m

@test("5.0 SC-40: the review skill names its scripts by the substituted plugin path, the path exists, and SKILL.md stays under 500 lines")
def _(d):
    sk = (HERE / "skills/review/SKILL.md").read_text()
    assert "${CLAUDE_PLUGIN_ROOT}/skills/review/scripts" in sk and (HERE / "skills/review/scripts/critic_scan.py").exists()
    assert len(sk.splitlines()) < 500

@test("5.0 SC-28: agent token costs are read from the transcript once per request, recorded only during a run, and totalled by role")
def _(d):
    tr = d / "agent.jsonl"
    def row(req, out, cw=1000, cr=0, model="claude-test"):
        return json.dumps({"type": "assistant", "requestId": req, "message": {"model": model, "usage": {"input_tokens": 3, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr, "output_tokens": out}}})
    tr.write_text("\n".join([row("r1", 5), row("r1", 300), row("r2", 7, 0, 1000), row("r2", 400, 0, 1000), json.dumps({"type": "user", "message": {"content": "x"}})]) + "\n")
    hook = {"cwd": str(d), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "a1", "agent_transcript_path": str(tr)}
    run(H / "record_cost.py", cwd=d, stdin=json.dumps(hook))
    assert not (d / ".critic/cost.jsonl").exists(), "no run is active: nothing should be recorded"
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    run(H / "record_cost.py", cwd=d, stdin=json.dumps(hook))
    run(H / "record_cost.py", cwd=d, stdin=json.dumps(dict(hook, agent_type="curmudgeon:curmudgeon-verifier", agent_id="v1", agent_transcript_path=str(d / "missing.jsonl"))))
    rows = [json.loads(x) for x in (d / ".critic/cost.jsonl").read_text().splitlines()]
    r = rows[0]
    assert (r["role"], r["requests"], r["input_tokens"], r["cache_creation_input_tokens"], r["cache_read_input_tokens"], r["output_tokens"]) == ("reviewer", 2, 6, 1000, 1000, 700), r
    assert rows[1]["role"] == "verifier" and "unavailable" in rows[1], rows[1]
    out = run(S / "critic_ledger.py", "tokens", cwd=d).stdout
    assert "| reviewer | 1 | 2 | 6 | 1,000 | 1,000 | 700 |" in out and "verifier | 1 (1 unavailable)" in out, out
    hooks = json.loads((H / "hooks.json").read_text())["hooks"]
    n_hooks = sum(len(g["hooks"]) for groups in hooks.values() for g in groups)
    readme = (HERE / "README.md").read_text(); block = readme.split("- **Hooks:**", 1)[1].split("\n## ", 1)[0]
    assert len([l for l in block.splitlines() if l.startswith("  - ")]) == n_hooks, f"the README lists a different number of hooks than hooks.json registers ({n_hooks})"

@test("5.0 SC-15 and SC-71: the funnel names where each missed plant was lost, and the gate's self-test still fails a refute-everything verifier")
def _(d):
    E = HERE.parent / "eval"
    if not (E / "score.py").exists(): return  # the eval kit isn't shipped inside the plugin
    c = d / ".critic"; c.mkdir()
    f = lambda file, title: {"file": file, "line": 1, "category": "x", "impact": "High", "title": title, "quote": "", "evidence": "", "failing_case": ""}
    (c / "findings.jsonl").write_text(json.dumps(f("app.js", "search responses race out of order, no abort")) + "\n")
    (c / "tally.json").write_text(json.dumps({"kept": [], "retracted": [{"finding": f("app.js", "XSS: title into innerHTML unescaped")}],
                                               "dropped": [{"finding": f("store.js", "JSON.parse at top level with no try: corrupt storage crashes load")}],
                                               "rejected": [], "suppressed": []}))
    (c / "refutations.jsonl").write_text(json.dumps(dict(f("store.js", "pending save lost on close: no flush on beforeunload"), kind="refuted")) + "\n")
    (c / "reviews").mkdir(); (c / "reviews/review-A.json").write_text(json.dumps([f("store.js", "persist swallows quota errors silently")]))
    out = subprocess.run([sys.executable, str(E / "score.py"), "--funnel", str(d), "--suite", "1"], capture_output=True, text=True).stdout
    for stage, plant in (("retracted by the quote check", "D01"), ("dropped on votes", "D02"), ("refuted by a verifier", "D03"),
                         ("raised, then lost at an unrecorded step", "D05"), ("never raised", "D16")):
        assert any(l.strip().startswith(stage + ": " + plant) for l in out.splitlines()), (stage, plant, out)
    assert "1 of 16 planted defects reached" in out, out
    r = subprocess.run([sys.executable, str(E / "score.py"), "--selftest"], capture_output=True, text=True)
    assert r.returncode == 0 and "refutes everything FAILS" in r.stdout, r.stdout + r.stderr

@test("5.0 card-A review: --only scans changed files even under build/ or vendor/, and never a path that leaves the root")
def _(d):
    root = d / "p"; write(root, "tools/build/deploy.js", 'const k = "@LIVE@";\n'); write(root, "src/ok.js", "const a = 1;\n")
    write(d, "outside/creds.js", 'const k = "@LIVE@";\n'); os.symlink(d / "outside", root / "linkdir")
    write(root, "only.txt", "tools/build/deploy.js\nsrc/ok.js\nsrc/../../outside/creds.js\nlinkdir/creds.js\n")
    run(S / "critic_scan.py", str(root), "--root", str(root), "--only", str(root / "only.txt"), cwd=root)
    where = [r["where"] for r in json.loads((root / ".critic/scan/report.json").read_text())["findings"] if r["rule"].startswith("secret-")]
    assert any(w.startswith("tools/build/deploy.js") for w in where), where
    assert not any("outside" in w or "linkdir" in w for w in where), f"--only read a file outside the root: {where}"

@test("5.0 card-A review: Python imports resolve the way Python does (stdlib names, TYPE_CHECKING and __main__ blocks make no edges)")
def _(d):
    write(d, "app/__init__.py", ""); write(d, "app/core/__init__.py", ""); write(d, "app/components/__init__.py", "")
    write(d, "app/core/schedule.py", "import calendar\n\ndef days():\n    return calendar.mdays\n")
    write(d, "app/components/calendar.py", "from app.core.schedule import days\n")
    write(d, "svc/__init__.py", "")
    write(d, "svc/order.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from svc.customer import Customer\n\ndef total():\n    return 1\n")
    write(d, "svc/customer.py", "from svc.order import total\nif __name__ == '__main__':\n    import svc.order\n")
    write(d, "tools/a.py", "import b\n"); write(d, "tools/b.py", "import a\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = [(r["rule"], r["where"]) for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"] in ("import-cycle", "boundary")]
    assert not any(w.startswith(("app/", "svc/")) for _r, w in rows), f"a false edge: {rows}"
    assert ("import-cycle", "tools/a.py") in rows, f"sibling scripts that import each other are a real cycle: {rows}"

@test("5.0 card-A review: CI result files that exist but can't be read make the CI check blocked, not n/a")
def _(d):
    write(d, "src/a.js", "const a = 1;\n"); write(d, "reports/semgrep.sarif", '{"runs": [{"tool": {"driver": {"name": "semgrep"}}, "results": [')
    write(d, "reports/junit.xml", '<testsuite name="t"><testcase name="x"><failure message="boom"')
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert rep["checks"]["ci"]["state"] == "blocked" and "ci" in rep["degraded"], (rep["checks"]["ci"], rep["degraded"])

@test("5.0 card-A review: mutation blanks strings without adding spaces, breaks Vue/Svelte inside the script, and nothing to mutate is n/a")
def _(d):
    sys.path.insert(0, str(S)); import importlib, scan_mutation, re as _re; importlib.reload(scan_mutation)
    import pathlib as _pl
    v = scan_mutation.code_view(_pl.Path("x.tsx"), 'const seen: Map<string, "a" | "b"> = new Map();\nconst el = <p className="hint"> {hint}</p>;\n')
    assert not [l for l in v for pat, _r in scan_mutation.OPS if _re.search(pat, l)], v
    sb = scan_mutation.sanity_break(".vue", "<template><p>x</p></template>\n<script setup>\nconst a = 1;\n</script>\n")
    assert sb.index("throw new Error") > sb.index("<script setup>"), sb
    subprocess.run(["git", "init", "-q"], cwd=d)
    write(d, "calc.py", "def lt(a, b):\n    return a < b\n"); write(d, "test_calc.py", "from calc import lt\nassert lt(1, 2) and not lt(2, 1) and not lt(1, 1)\n")
    subprocess.run(["git", "add", "."], cwd=d); subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "c"], cwd=d)
    write(d, "calc.py", "# helpers\ndef lt(a, b):\n    return a < b\n")
    run(S / "critic_scan.py", ".", "--root", ".", "--mutate", "calc.py", "--test-cmd", f"{sys.executable} test_calc.py", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert rep["checks"]["mutation"]["state"] == "n/a" and "mutation" not in rep["degraded"], rep["checks"]["mutation"]

@test("5.0 SC-20: every plugin eval case has a prompt and at least one grader, and every grader is a free one (no model judges a score)")
def _(d):
    import re as _re
    E = HERE / "evals"; cases = [p for p in E.iterdir() if p.is_dir() and p.name not in ("results", "mocks")]
    assert len(cases) >= 4, cases
    for c in cases:
        assert (c / "prompt.md").exists() or (c / "case.yaml").exists(), c.name
        graders = list((c / "graders").glob("*.md"))
        assert graders, f"{c.name} has no grader"
        for g in graders:
            fm = _re.match(r"---\n(.*?)\n---", g.read_text(), _re.S); assert fm, g
            typ = _re.search(r"^type:\s*(\S+)", fm.group(1), _re.M).group(1)
            assert typ in ("regex", "tool_used", "tool_order", "file_exists"), f"{c.name}/{g.name}: {typ} grader calls a model"
        if (c / "case.yaml").exists():
            y = (c / "case.yaml").read_text(); assert 'schema_version: "1.1"' in y and f"name: {c.name}" in y, c.name
            m = _re.search(r"scaffold_script:\s*(\S+)", y)
            if m: assert (c / m.group(1)).exists(), f"{c.name}: scaffold script missing"

@test("5.0 SC-22 and SC-25: the blindness guard denies each role what it must not read (links included), leaves others alone, and refuses forks during a run")
def _(d):
    write(d, ".critic/reviews/review-B.json", "[]"); write(d, ".critic/verify/F-1.json", "{}"); write(d, ".critic/ledger.md", "# l"); write(d, "src/a.py", "x = 1\n")
    write(d, ".critic/scratch/me/notes.txt", "n"); write(d, ".critic/scratch/other/notes.txt", "n"); os.symlink(d / ".critic/reviews", d / "src/peek")
    def ask(agent, tool, **ti):
        inp = {"tool_name": tool, "tool_input": ti, "cwd": str(d)}
        if agent: inp.update(agent_type=agent, agent_id="me")
        return "deny" in run(H / "read_guard.py", cwd=d, stdin=json.dumps(inp)).stdout
    R, V, D_ = "curmudgeon:curmudgeon-reviewer", "curmudgeon-verifier", "curmudgeon:curmudgeon-dedup"
    assert ask(R, "Read", file_path=str(d / ".critic/reviews/review-B.json"))
    assert ask(R, "Read", file_path=str(d / "src/peek/review-B.json")), "a link into .critic/reviews must be caught"
    assert ask(R, "Bash", command="cat .critic/tally.json | head")
    assert ask(R, "Grep", pattern="x", path=".critic/scan")
    assert ask(R, "Read", file_path=str(d / ".critic/scratch/other/notes.txt"))
    assert not ask(R, "Read", file_path=str(d / ".critic/scratch/me/notes.txt"))
    assert not ask(R, "Read", file_path=str(d / "src/a.py"))
    assert not ask(V, "Read", file_path=str(d / ".critic/verify/F-1.json")) and not ask(V, "Read", file_path=str(d / ".critic/ledger.md"))
    assert ask(V, "Read", file_path=str(d / ".critic/reviews/review-B.json"))
    assert ask(D_, "Read", file_path=str(d / ".critic/scan/report.md"))
    assert not ask(None, "Read", file_path=str(d / ".critic/reviews/review-B.json")), "the main conversation is never limited"
    assert not ask("general-purpose", "Read", file_path=str(d / ".critic/reviews/review-B.json"))
    assert not ask(None, "Agent", subagent_type="fork", prompt="x"), "no run is active"
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    assert ask(None, "Agent", subagent_type="fork", prompt="x"), "a fork during a run must be refused"
    assert not ask(None, "Agent", subagent_type="curmudgeon:curmudgeon-reviewer", prompt="x")

@test("5.0 SC-23, SC-24, SC-26, SC-27, SC-29, SC-33: private scratch folders, lean blind agents, and a logged set-aside list")
def _(d):
    out = run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "a1b2", "cwd": str(d)})).stdout
    assert (d / ".critic/scratch/a1b2").is_dir() and "additionalContext" in out and "a1b2" in out, out
    assert not run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "Explore", "agent_id": "zz", "cwd": str(d)})).stdout.strip()
    e = d / "linked"; e.mkdir(); (d / "elsewhere").mkdir(); os.symlink(d / "elsewhere", e / ".critic")
    run(H / "scratch_dir.py", cwd=e, stdin=json.dumps({"agent_type": "curmudgeon-reviewer", "agent_id": "x9", "cwd": str(e)}))
    assert not (d / "elsewhere/scratch").exists(), "never create through a planted link"
    import re as _re
    for a in (HERE / "agents").glob("*.md"):
        fm = _re.match(r"---\n(.*?)\n---", a.read_text(), _re.S).group(1)
        for k in ("omitClaudeMd: true", 'disallowedTools: ["mcp__*"]', "maxTurns:", "effort:"): assert k in fm, (a.name, k)
        assert fm.count("<example>") == 1, a.name
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    write(d, ".critic/reviews/review-A.json", json.dumps({"findings": [g], "set_aside": [{"file": "src/app.js", "line": 2, "what": "innerHTML", "guard": "src/app.js:3 escapes it"}]}))
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert t["set_aside"] and t["set_aside"][0]["reviewer"] == "review-A" and len(t["kept"]) + len(t["contested"]) + len(t["dropped"]) == 1, t
    write(d, ".critic/reviews/review-B.json", json.dumps({"findings": [g], "set_aside": [{"file": "src/app.js", "what": "no guard named"}]}))
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-reviewer", "cwd": str(d), "last_assistant_message": "Wrote .critic/reviews/review-B.json"})).stdout
    assert "guard" in out and "block" in out, out
    write(d, ".critic/reviews/review-B.json", json.dumps({"findings": [g], "set_aside": []}))
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-reviewer", "cwd": str(d), "last_assistant_message": "Wrote .critic/reviews/review-B.json"})).stdout
    assert "block" not in out, out

@test("5.0 SC-68: the four typed fix skills are one /curmudgeon:fix with every function kept, and no old command name is left anywhere")
def _(d):
    import re as _re
    assert sorted(p.name for p in (HERE / "skills").iterdir() if p.is_dir()) == ["fix", "gate", "review"]
    fx = (HERE / "skills/fix/SKILL.md").read_text()
    assert "disable-model-invocation: true" in fx and all(f"## {w}" in fx for w in ("patch", "iterate", "approve", "rollback"))
    for p in list(HERE.rglob("*.md")) + list(HERE.rglob("*.py")) + [HERE.parent / "README.md"]:
        if "tests" in p.parts or "evals" in p.parts: continue
        assert not _re.search(r"/curmudgeon:(patch|iterate|approve|rollback)\b", p.read_text(errors="replace")), p

@test("5.0 card-B review: cost stops being recorded once the teardown is written, and the funnel reads only the current run")
def _(d):
    tr = d / "agent.jsonl"; tr.write_text(json.dumps({"type": "assistant", "requestId": "r1", "message": {"model": "m", "usage": {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}}}) + "\n")
    hook = {"cwd": str(d), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "a1", "agent_transcript_path": str(tr)}
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    time.sleep(1.1); write(d, ".critic/last-review.md", "# done")
    run(H / "record_cost.py", cwd=d, stdin=json.dumps(hook))
    assert not (d / ".critic/cost.jsonl").exists(), "the run ended with the teardown; nothing should be billed to it"
    E = HERE.parent / "eval"
    if not (E / "score.py").exists(): return
    e = d / "f"; c = e / ".critic"; (c / "history/run-1/reviews").mkdir(parents=True); (c / "reviews").mkdir()
    (c / "ledger.json").write_text(json.dumps({"run": 2}))
    fz = lambda title: {"file": "guards.js", "line": 1, "category": "x", "impact": "High", "title": title}
    (c / "history/run-1/reviews/review-A.json").write_text(json.dumps([fz("canVoid indexOf returns -1 which is truthy")]))
    (c / "refutations.jsonl").write_text(json.dumps(dict(fz("lastSend is never updated so a double click sends twice"), kind="refuted", run=1)) + "\n")
    out = subprocess.run([sys.executable, str(E / "score.py"), "--funnel", str(e), "--suite", "4"], capture_output=True, text=True).stdout
    assert "never raised: G2" in out and "never raised: G4" in out, out

@test("5.0 SC-42 and SC-44: a bare 'confirmed' counts as unclear, a confirmation with a real path counts, and a security refutation names attacker, gain and reason")
def _(d):
    write(d, "src/app.js", APP)
    g = finding(category="xss", impact="High", line=2, quote=APP.split("\n")[1].strip(), title="Title into innerHTML unescaped")
    h = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g, h]))
    revs = [f".critic/reviews/review-{L}.json" for L in "ABC"]
    run(S / "critic_merge.py", "tally", *revs, cwd=d)
    ids = {k["category"]: k["id"] for k in json.loads((d / ".critic/tally.json").read_text())["kept"]}
    def apply(verdicts):
        write(d, "v.json", json.dumps(verdicts)); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
        return {r["category"]: r for r in (json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines() if x.strip())}
    out = apply([{"id": ids["xss"], "verdict": "confirmed", "reproduced": "traced"}, {"id": ids["domain"], "verdict": "confirmed", "reproduced": "traced",
           "entry": "renderTotal is called on every render", "path": ["src/app.js:4 multiplies by the tax rate inside the render function"]}])
    assert out["xss"]["verifier"] == "unclear" and out["domain"]["verifier"] == "confirmed", out
    why = "The title reaches the page only through textContent at src/app.js:3 in the shipped build, so markup is never parsed."
    out = apply([{"id": ids["xss"], "verdict": "refuted", "reproduced": "executed", "refutation": why}])
    assert "xss" in out, "a security refutation without attacker, gain and reason must not drop the finding"
    out = apply([{"id": ids["xss"], "verdict": "refuted", "reproduced": "executed", "refutation": why, "attacker": "anyone who can name a note", "gain": "nothing", "reason": "guard_blocks"}])
    assert "xss" not in out, out
    msg = 'Done.\n```json\n' + json.dumps([{"id": ids["domain"], "verdict": "confirmed", "reproduced": "traced"}]) + '\n```'
    o = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon-verifier", "cwd": str(d), "last_assistant_message": msg})).stdout
    assert "block" in o and "unclear" in o, o

@test("5.0 SC-72: apply records a hash of every output, and integrity names any file edited afterwards")
def _(d):
    write(d, "src/app.js", APP); g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    man = json.loads((d / ".critic/manifest.json").read_text())
    assert {"findings.jsonl", "counts.md", "tally.json", "ledger.json"} <= set(man["files"]), man
    r = run(S / "critic_ledger.py", "integrity", cwd=d); assert r.returncode == 0 and "matches" in r.stdout, r.stdout
    c = d / ".critic/counts.md"; c.write_text(c.read_text().replace("Medium 1", "Medium 0"))
    r = run(S / "critic_ledger.py", "integrity", cwd=d)
    assert r.returncode == 1 and "counts.md changed" in r.stdout, r.stdout

@test("5.0 SC-37 and SC-61: fixes that can't be offered are named, partial fixes are labelled, and the two optional fields reach the verifier")
def _(d):
    sys.path.insert(0, str(S)); import importlib, critic_merge; importlib.reload(critic_merge)
    q = "const price = total * 1.0825;"
    fs = critic_merge.fix_status
    assert fs({"quote": q, "remediation": ""}) == "none"
    assert fs({"quote": q, "remediation": f"Replace it with `{q}`"}).startswith("not offerable: the fix is the same")
    assert fs({"quote": q, "remediation": "Use `price(total, rules.tax(region)`"}).startswith("not offerable: unbalanced")
    assert fs({"quote": q, "remediation": "A partial fix: move `TAX` to `config.js` for now"}) == "partial"
    assert fs({"quote": q, "remediation": "Move the rate to `pricing.tax(region)` and call it from render"}) == "usable"
    assert fs({"quote": q, "remediation": "Don't hard-code it; read `rules.tax()`"}) == "usable", "an apostrophe in prose is not an unbalanced quote"
    write(d, "src/app.js", APP)
    g = finding(category="domain", impact="Medium", line=4, quote=q, title="Tax rule in render code", remediation=f"Replace it with `{q}`",
                preconditions="a region with a different tax rate", root_cause="pricing rules live in the view")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    pk = json.loads(next((d / ".critic/verify").glob("*.json")).read_text())
    assert pk["preconditions"] and pk["root_cause"], pk
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "Fixes not to offer" in (d / ".critic/counts.md").read_text()
    from critic_findings import validate
    assert validate(dict(g, preconditions=3)) and not validate(g)

@test("5.0 card-C review: the guard covers .critic itself, searches from above it, case, globs and links, and no longer blocks payload or search text; with no workspace, Bash is off")
def _(d):
    write(d, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]'); write(d, "src/a.py", "x = 1\n"); write(d, "eval/fixture3/.critic/ledger.json", "{}")
    (d / ".critic/scratch/me").mkdir(parents=True); os.symlink(d / ".critic/reviews", d / ".critic/scratch/me/r"); os.symlink(d / ".critic", d / "src/link")
    def ask(tool, agent="curmudgeon:curmudgeon-reviewer", **ti):
        return "deny" in run(H / "read_guard.py", cwd=d, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(d), "agent_type": agent, "agent_id": "me"})).stdout
    for tool, ti in [("Grep", {"pattern": "x", "path": ".critic"}), ("Grep", {"pattern": "x", "path": str(d / ".critic")}), ("Grep", {"pattern": "x", "path": ".critic/"}),
                     ("Grep", {"pattern": "x", "path": ".critic/scratch"}), ("Grep", {"pattern": "x", "path": "src/link"}), ("Grep", {"pattern": "x"}), ("Grep", {"pattern": "x", "path": "."}),
                     ("Glob", {"pattern": "*", "path": ".critic/scratch"}), ("Glob", {"pattern": ".critic/**/*.json"}), ("Read", {"file_path": ".CRITIC/REVIEWS/review-B.json"}),
                     ("Read", {"file_path": ".critic/scratch/me/r/review-B.json"}), ("Bash", {"command": "cat .critic/*/review-B.json"}), ("Bash", {"command": "cat .critic/\"reviews\"/review-B.json"}),
                     ("Bash", {"command": "cd .critic && cat reviews/review-B.json"}), ("Bash", {"command": "grep -rn title ."}), ("Bash", {"command": "cat .critic/scratch/me/../../reviews/review-B.json"}),
                     ("Bash", {"command": "cat .critic/scratch/me/r/review-B.json"}), ("Bash", {"command": "rg --hidden title ."})]:
        assert ask(tool, **ti), f"should be denied: {tool} {ti}"
    for tool, ti in [("Grep", {"pattern": "x", "path": ".", "glob": "!.critic/**"}), ("Grep", {"pattern": "\\.critic/reviews", "path": "plugin"}), ("Grep", {"pattern": "x", "path": "src"}),
                     ("Read", {"file_path": "eval/fixture3/.critic/ledger.json"}), ("Read", {"file_path": "src/a.py"}), ("Glob", {"pattern": "**/*.py"}),
                     ("Read", {"file_path": ".critic/rules.md"})]:
        assert not ask(tool, **ti), f"should be allowed: {tool} {ti}"
    assert not ask("Read", agent="curmudgeon:curmudgeon-verifier", file_path=".critic/verify/F-1.json")
    assert ask("Read", agent="curmudgeon:curmudgeon-verifier", file_path=".critic/reviews/review-B.json")
    r = run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    assert r.returncode != 0 and "link" in r.stderr, "a link planted in a scratch folder must stop the run"
    (d / ".critic/scratch/me/r").unlink(); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    assert "scratch/" in (d / ".critic/.gitignore").read_text()
    write(d, ".critic/reviews/review-A.json", json.dumps({"findings": [], "set_aside": None}))
    r = run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d); assert r.returncode == 0, r.stdout + r.stderr
    e = d / "old"; write(e, ".critic/ledger.json", json.dumps({"started_at": time.time() - 13 * 3600, "run": 1}))
    assert "deny" not in run(H / "read_guard.py", cwd=e, stdin=json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "fork"}, "cwd": str(e)})).stdout, "an abandoned run must not block forks for ever"

@test("5.0 SC-36: round escalates a finding fixed twice, one open for 3 rounds, and open Critical+High that doesn't fall")
def _(d):
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    run(S / "critic_ledger.py", "add", "F-1", "High", "src/a.js:1", "a real bug", cwd=d)
    r = run(S / "critic_ledger.py", "round", cwd=d); assert "ESCALATE" not in r.stdout, r.stdout
    r = run(S / "critic_ledger.py", "round", cwd=d)
    assert r.returncode == 3 and "did not fall" in r.stdout, r.stdout
    L = json.loads((d / ".critic/ledger.json").read_text()); L["findings"]["F-1"]["history"] += ["run 1: fixed", "run 1: fixed"]; L["round"] = 1
    (d / ".critic/ledger.json").write_text(json.dumps(L))
    r = run(S / "critic_ledger.py", "round", cwd=d)
    assert "fixed twice" in r.stdout and "open for 3 rounds" in r.stdout, r.stdout

@test("5.0 SC-38: every report records the revision it reviewed, and fresh refuses a finding whose code changed since")
def _(d):
    write(d, "src/app.js", APP); g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    rev = json.loads((d / ".critic/revision.json").read_text()); assert len(rev["payload_sha256"]) == 64, rev
    assert "Revision reviewed:" in (d / ".critic/counts.md").read_text()
    fid = json.loads((d / ".critic/findings.jsonl").read_text().splitlines()[0])["id"]
    r = run(S / "critic_ledger.py", "fresh", fid, cwd=d); assert r.returncode == 0, r.stdout
    write(d, "src/app.js", APP.replace("const price = total * 1.0825;", "const price = total * taxRate(region);"))
    r = run(S / "critic_ledger.py", "fresh", fid, cwd=d)
    assert r.returncode == 1 and "STALE" in r.stdout, r.stdout

@test("5.0 SC-39: the same code under another category keeps its ledger history and its fp ruling, and acted waits for a full re-review")
def _(d):
    write(d, "src/app.js", APP); q = "const price = total * 1.0825;"
    def review(cat):
        g = finding(category=cat, impact="Medium", line=4, quote=q, title="Tax rule in render code")
        run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
        for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
        run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
        write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
        return json.loads((d / ".critic/tally.json").read_text())
    review("domain")
    led = json.loads((d / ".critic/ledger.json").read_text()); first = next(iter(led["findings"]))
    review("domain-leak")
    led = json.loads((d / ".critic/ledger.json").read_text())
    assert list(led["findings"]) == [first] and "still there" in led["findings"][first]["history"][-1], led["findings"]
    run(S / "critic_ledger.py", "fp", first, "the rate is fixed by law here", cwd=d)
    t = review("pricing")
    assert t["suppressed"] and not t["kept"], t["suppressed"]
    write(d, "src/app.js", APP.replace(q, "const price = total * rate(region);"))
    run(S / "critic_ledger.py", "acted", cwd=d)
    f = json.loads((d / ".critic/ledger.json").read_text())["findings"][first]
    assert "acted_on" not in f and f.get("acted_pending"), f

@test("5.0 §5.29 structural blindness: each reviewer works in a private frozen copy without .critic, its Bash runs there, and the copy is gone at stop")
def _(d):
    p = d / "proj"; write(p, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]'); write(p, ".critic/scan/report.md", "SCAN"); write(p, ".critic/rules.md", "r")
    write(p, "src/a.py", "x = 1\n"); write(p, "eval/fx/.critic/reviews/r.json", "{}"); write(p, ".git/config", "[core]"); write(p, "node_modules/lib/index.js", "1")
    write(p, "big.bin", "x" * (5 * 1024 * 1024 + 1)); os.symlink(p / ".critic", p / "src/link"); os.symlink(p, p / "src/up"); os.symlink(p / "src/a.py", p / "src/alias.py")
    def start(agent, aid):
        out = run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": agent, "agent_id": aid, "cwd": str(p)})).stdout
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]
    msg = start("curmudgeon:curmudgeon-reviewer", "me")
    rec = json.loads((p / ".critic/scratch/me/workspace.json").read_text()); ws = pathlib.Path(rec["payload"])
    assert ws.is_dir() and str(ws) in msg and "cd " in msg and ws == (p / ".critic/scratch/me/payload").resolve(), msg
    assert (ws / "src/a.py").read_text() == "x = 1\n" and (ws / "eval/fx/.critic/reviews/r.json").exists(), "the payload, fixtures' own .critic folders included, is copied"
    assert not (ws / ".critic").exists() and (ws / ".git").is_file() and not (ws / "big.bin").exists() and "big.bin" in msg, "a broken .git becomes a stub that stops git walking up"
    assert not os.path.lexists(ws / "src/link") and not os.path.lexists(ws / "src/up"), "links back into .critic or to the project itself are dropped"
    assert (ws / "src/alias.py").resolve() == (ws / "src/a.py").resolve(), "a link inside the project points at the same file in the copy"
    assert (ws / "node_modules").is_symlink(), "dependency folders are linked so tests can run"
    start("curmudgeon:curmudgeon-reviewer", "other"); other = json.loads((p / ".critic/scratch/other/workspace.json").read_text())["payload"]
    def ask(tool, aid="me", agent="curmudgeon:curmudgeon-reviewer", **ti):
        return "deny" in run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(p), "agent_type": agent, "agent_id": aid})).stdout
    c = f"cd {ws} && "
    for cmd in ["cat .critic/reviews/review-B.json", "grep -rn SECRET .", f"cd {p} && cat .critic/reviews/review-B.json", c + f"cat {p}/.critic/reviews/review-B.json",
                c + f"grep -rn SECRET {p}", c + "cd - && grep -rn SECRET .", c + "cat $OLDPWD/.critic/reviews/review-B.json", c + "cat $CLAUDE_PROJECT_DIR/.critic/scan/report.md",
                c + f"cat {other}/src/a.py", c + "cat node_modules/../.critic/reviews/review-B.json", f"cd {other} && ls", c + "cat ../../../reviews/review-B.json",
                c + "grep -rn SECRET ../..", c + "cat ../../*/payload/src/a.py", c + "grep -rn SECRET node_modules/..", c + "cat ../../../*/review-B.json", c + "rg SECRET --file=../../../scan/report.md"]:
        assert ask("Bash", command=cmd), f"should be denied: {cmd}"
    for cmd in [c + "grep -rn SECRET .", c + "rg --hidden SECRET", c + "python3 -m pytest -q", c + "cat eval/fx/.critic/reviews/r.json", f"cd '{ws}' && ls -la",
                c + f"python3 {rec['notes']}/probe.py", c + "node node_modules/lib/index.js", c + f"cp src/a.py {rec['notes']}/", c + "grep -n '.critic/reviews' src/a.py",
                c + "git log --oneline -3", c + f"cat {p}/src/a.py", c + "ls ../notes"]:
        assert not ask("Bash", command=cmd), f"should be allowed: {cmd}"
    assert ask("Grep", pattern="SECRET") and ask("Grep", pattern="SECRET", path=str(p)) and ask("Grep", pattern="x", path=str(p / ".critic/scratch")), "searches from the project or above the workspaces are refused"
    assert ask("Read", file_path=other + "/src/a.py") and ask("Glob", pattern="*/payload/src/*.py", path=str(p / ".critic/scratch"))
    assert not ask("Grep", pattern="SECRET", path=str(ws)) and not ask("Read", file_path=str(ws / "src/a.py")) and not ask("Glob", pattern="**/*.py", path=str(ws))
    assert not ask("Read", file_path=str(p / "src/a.py")) and ask("Read", file_path=str(p / ".critic/reviews/review-B.json")) and not ask("Read", file_path=str(p / ".critic/rules.md"))
    assert ask("Bash", aid="nobody", command=f"cd {ws} && ls"), "an agent with no workspace has no Bash"
    (pathlib.Path(rec["notes"]) / "probe.py").write_text("print(1)\n")
    run(H / "check_contract.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "me", "cwd": str(p), "stop_hook_active": True}))
    assert not ws.exists() and (p / ".critic/scratch/me/notes/probe.py").exists(), "the copy is deleted at stop and the notes are kept"
    assert "workspace" not in start("curmudgeon:curmudgeon-dedup", "dd") and not (p / ".critic/scratch/dd/workspace.json").exists(), "dedup reads one file; it needs no copy"
    from critic_findings import strip_workspace
    assert strip_workspace(f"{ws}/src/a.py:1 sets x") == "src/a.py:1 sets x"
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=p)
    assert not list((p / ".critic/history").glob("*/scratch/*/payload")), "a copy left behind is deleted at the next run's start, never archived"
    e = d / "linked"; write(e, "src/a.py", "x\n"); (e / ".critic").mkdir(); (d / "away").mkdir(); os.symlink(d / "away", e / ".critic/scratch")
    out = run(H / "scratch_dir.py", cwd=e, stdin=json.dumps({"agent_type": "curmudgeon-verifier", "agent_id": "v1", "cwd": str(e)})).stdout
    assert not list((d / "away").iterdir()), "never build a copy through a planted link"

@test("5.0 §5.29 live-run find: the contract check never echoes another review's words, and refuses a review file older than the agent")
def _(d):
    write(d, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]'); write(d, "src/a.py", "x = 1\n")
    time.sleep(2.5)  # older than the agent's start by more than the 2 s allowed for coarse file clocks
    run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "me", "cwd": str(d)}))
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "me", "cwd": str(d),
              "last_assistant_message": "I could not read .critic/reviews/review-B.json"})).stdout
    assert "SECRET-B" not in out and "not written by you" in out, out
    write(d, ".critic/reviews/review-A.json", '[{"title": "MINE"}]')
    out = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "me", "cwd": str(d), "last_assistant_message": ".critic/reviews/review-A.json"})).stdout
    assert "finding 1:" in out and "MINE" not in out, out

@test("5.0 SC-43: in a review of a change, findings are marked introduced or pre-existing by script, and a new caller of an old sink counts as introduced")
def _(d):
    subprocess.run(["git", "init", "-q"], cwd=d)
    write(d, "src/app.js", APP); write(d, "src/sink.js", "function show(el, t) {\n  el.innerHTML = t;\n}\n")
    subprocess.run(["git", "add", "."], cwd=d); subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base"], cwd=d)
    write(d, "src/sink.js", "function show(el, t) {\n  el.innerHTML = t;\n}\nshow(document.body, location.hash);\n")
    run(S / "critic_map.py", cwd=d)
    cm = json.loads((d / ".critic/change-map.json").read_text()); assert cm["mode"] == "diff" and cm["hunks"].get("src/sink.js"), cm
    old = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    new = finding(category="xss", impact="High", file="src/sink.js", line=2, quote="el.innerHTML = t;", title="Sink now fed from location.hash", evidence="src/sink.js:4 passes location.hash to show()")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([old, new]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    rows = {r["category"]: r for r in (json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines())}
    assert rows["xss"]["origin"] == "introduced" and rows["domain"]["origin"] == "pre-existing", rows
    assert "## Pre-existing" in (d / ".critic/counts.md").read_text()

@test("5.0 SC-46 and SC-47: Not reviewed is computed from the reviewers' coverage, and noisy scanner rows are pedantic NOTEs counted apart")
def _(d):
    write(d, "src/app.js", APP); write(d, "src/other.js", "export const x = 1;\n")
    run(S / "critic_map.py", "--files", "src/app.js", "src/other.js", cwd=d)
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps({"findings": [g], "coverage": {"read": ["src/app.js"], "not_reached": []}}))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    cov = json.loads((d / ".critic/tally.json").read_text())["coverage"]
    assert cov["known"] and cov["not_reviewed"] == ["src/other.js"], cov
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "Not reviewed (computed from the reviewers' coverage reports): src/other.js" in (d / ".critic/counts.md").read_text()
    e = d / "p"; write(e, "src/big.js", "\n".join(f"const v{i} = {i};" for i in range(420)) + "\n")
    write(e, ".critic/rules/r.json", json.dumps([{"id": "noisy", "severity": "WARN", "area": "perf", "pattern": "const v1 ", "message": "m", "pedantic": True}]))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=e)
    rows = {r["rule"]: r for r in json.loads((e / ".critic/scan/report.json").read_text())["findings"]}
    assert rows["long-file"]["tier"] == "pedantic" and rows["long-file"]["sev"] == "NOTE", rows["long-file"]
    assert rows["rule-noisy"]["tier"] == "pedantic" and rows["rule-noisy"]["sev"] == "NOTE", rows["rule-noisy"]
    assert " pedantic " in (e / ".critic/scan/report.md").read_text()

@test("5.0 SC-31: critic_run.py walks a run from begin to teardown, running each scripted step and naming the agents to start")
def _(d):
    write(d, "src/app.js", APP)
    out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d).stdout
    assert "curmudgeon:curmudgeon-reviewer" in out and "A, B, C" in out, out
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "kept 1" in out and "curmudgeon:curmudgeon-verifier" in out and ".critic/verify/" in out, out
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    write(d, ".critic/verdicts/1.json", json.dumps([{"id": fid, "verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on every update", "path": ["src/app.js:4 multiplies by the tax rate inside render"]}]))
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "final: 1 finding" in out and "write the teardown" in out, out
    assert "teardown" in run(S / "critic_run.py", "status", cwd=d).stdout

@test("5.0 SC-73: when one control in one file keeps springing new holes, round stops with a WHACK-A-MOLE escalation and a ranked-solutions guide")
def _(d):
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    L = json.loads((d / ".critic/ledger.json").read_text())
    def f(cat, where, status, hist): return {"score": "High", "where": where, "summary": "s", "status": status, "claims": {}, "history": hist, "quote": "", "category": cat}
    L["findings"] = {"F-1": f("blindness-bypass", "hooks/g.py:10", "fixed", ["run 1: new", "run 1: fixed"]), "F-2": f("blindness-glob", "hooks/g.py:40", "fixed", ["run 2: new", "run 2: fixed"]),
                     "F-4": f("xss", "src/a.js:1", "fixed", ["run 1: fixed"]), "F-5": f("xss", "src/b.js:1", "open", ["run 2: new"])}
    (d / ".critic/ledger.json").write_text(json.dumps(L))
    r = run(S / "critic_ledger.py", "round", cwd=d); assert "WHACK-A-MOLE" not in r.stdout, "two holes, both closed, is not a pattern yet: " + r.stdout
    L = json.loads((d / ".critic/ledger.json").read_text()); L["findings"]["F-3"] = f("blindness", "hooks/g.py:77", "open", ["run 3: new"])
    (d / ".critic/ledger.json").write_text(json.dumps(L))
    r = run(S / "critic_ledger.py", "round", cwd=d)
    assert r.returncode == 3 and "WHACK-A-MOLE in hooks/g.py (blindness)" in r.stdout and "F-3" in r.stdout and "src/" not in r.stdout, r.stdout
    guide = (HERE / "skills/review/references/escalation.md").read_text()
    assert "five solutions, ranked best to worst" in guide and guide.count("\n1. **Remove the need.**") == 1 and "5. **Accept, document and watch.**" in guide
    assert "WHACK-A-MOLE" in (HERE / "skills/fix/SKILL.md").read_text() and "escalation.md" in (HERE / "skills/fix/SKILL.md").read_text()

@test("5.0 SC-30 and SC-32: briefs share one byte-identical prefix and differ only in letter and order; begin prints the scan to run in the background")
def _(d):
    for n in "abcdef": write(d, f"src/{n}.js", "export const x = 1;\n")
    write(d, ".critic/scan/report.md", "SCAN-SECRET"); write(d, ".critic/reviews/review-B.json", '[{"title": "OTHER-REVIEW"}]')
    run(S / "critic_ledger.py", "decision", "Prices are in cents", cwd=d)
    out = run(S / "critic_run.py", "begin", "--files", *[f"src/{n}.js" for n in "abcdef"], "--tier", "full", cwd=d).stdout
    assert "run_in_background" in out and "critic_scan.py . --root . --only .critic/scan-only.txt" in out and ".critic/briefs/brief-B.md" in out, out
    assert sorted((d / ".critic/scan-only.txt").read_text().split()) == [f"src/{n}.js" for n in "abcdef"]
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text() for x in "ABC"}
    pre = {x: b[x].split("\n---\n")[0] for x in "ABC"}
    assert pre["A"] == pre["B"] == pre["C"] and "Prices are in cents" in pre["A"], "the shared part must be byte-identical"
    order = {x: [l.split(". ", 1)[1] for l in b[x].split("\n---\n")[1].splitlines() if l[:1].isdigit()] for x in "ABC"}
    assert order["B"] == list(reversed(order["A"])) and sorted(order["C"]) == sorted(order["A"]) and order["C"] not in (order["A"], order["B"]), order
    assert all("SCAN-SECRET" not in t and "OTHER-REVIEW" not in t for t in b.values()), "a brief never carries the scan or another review"
    first_c = b["C"]; run(S / "critic_brief.py", cwd=d); assert (d / ".critic/briefs/brief-C.md").read_text() == first_c, "the shuffle is seeded by the run: a rerun gives the same order"

@test("5.0 SC-34: the teardown opens with the verdict and counts, has a quiet mode that keeps every count, and the code section is named for what it holds")
def _(d):
    oc = (HERE / "skills/review/references/output-contract.md").read_text()
    assert "## First line: the verdict" in oc and "## Quiet mode" in oc and "#### 1. CODE AND ARCHITECTURE" in oc and "CRITICAL CODE ARCHITECTURE" not in oc
    assert "quiet" in (HERE / "skills/review/SKILL.md").read_text()
    body = "**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low\n#### INTENT GATE\nnot needed\n#### RISK MAP\nx\n#### SANDBOX LEDGER\nx\n#### {}\n- **C1** `a.js:1` | **IMPACT: High** | x\n#### 2. UI/UX & INTERACTION FRICTION\nnone\n#### 3. THE \"ANTI-AI\" CLEANUP\nnone\n#### 4. CLAIMS, NUMBERS AND CONSISTENCY\nnone\n#### 5. VERDICT\n- **BLOCK**\n- Counts: 0 Critical, 1 High, 0 Medium, 0 Low\n"
    for name in ("1. CODE AND ARCHITECTURE", "1. CRITICAL CODE ARCHITECTURE DEFECTS"):
        r = write(d, "r.md", body.format(name))
        out = run(HERE.parent / "eval" / "score.py", str(r), "--suite", "1", cwd=d).stdout
        assert "✓ all contract headers" in out, (name, out[-600:])

@test("5.0 SC-35: an opt-in compact change packet carries changed hunks with context, deletions as one line and new files whole")
def _(d):
    subprocess.run(["git", "init", "-q"], cwd=d)
    write(d, "src/m.py", "".join(f"v{i} = {i}\n" for i in range(1, 31)))
    subprocess.run(["git", "add", "."], cwd=d); subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base"], cwd=d)
    lines = [f"v{i} = {i}" for i in range(1, 31)]; lines[14] = "v15 = 'CHANGED'"; del lines[24]
    write(d, "src/m.py", "\n".join(lines) + "\n"); write(d, "src/new.py", "BRAND_NEW = 1\n")
    run(S / "critic_map.py", cwd=d); run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    run(S / "critic_brief.py", cwd=d); assert "Change packet" not in (d / ".critic/briefs/brief-A.md").read_text(), "off unless asked"
    run(S / "critic_brief.py", "--packet", cwd=d); b = (d / ".critic/briefs/brief-A.md").read_text()
    assert "Change packet" in b and "v15 = 'CHANGED'" in b and "   12  v12 = 12" in b and "   18  v18 = 18" in b and "v1 = 1\n" not in b and "v30 = 30" not in b, b
    assert "(lines deleted after line 24)" in b and "src/new.py (new file)" in b and "BRAND_NEW = 1" in b, b

@test("5.0 §5.29 blind review: git in the copy is its own repo, hooks find the project from inside the copy, a blocked stop keeps the copy, links and odd paths work")
def _(d):
    G = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    p = d / "o'brien proj"; write(p, "src/a.py", "x = 1\n"); write(p, ".gitignore", "dist/\n.critic/\n"); write(p, "dist/huge.js", "built\n")
    write(d, "outside/lib.txt", "shared\n"); os.symlink("../../outside/lib.txt", p / "src/extlink")
    subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "."], cwd=p); subprocess.run(G + ["commit", "-qm", "base"], cwd=p)
    write(p, "src/a.py", "x = 2  # uncommitted edit\n"); write(p, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]')
    out = run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v1", "cwd": str(p)})).stdout
    rec = json.loads((p / ".critic/scratch/v1/workspace.json").read_text()); ws = pathlib.Path(rec["payload"])
    assert rec["git"] == "clone" and "own git repository" in out, (rec, out)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ws, capture_output=True, text=True).stdout.strip()
    assert pathlib.Path(top).resolve() == ws.resolve(), "git in the copy must find the copy, not the project"
    assert subprocess.run(["git", "log", "--oneline", "--", "src/a.py"], cwd=ws, capture_output=True, text=True).stdout.strip(), "history works in the copy"
    assert "uncommitted edit" in subprocess.run(["git", "diff"], cwd=ws, capture_output=True, text=True).stdout, "the copy shows the working-tree edits"
    assert (ws / "src/extlink").read_text() == "shared\n", "a link outside the project still resolves from the copy"
    subprocess.run(G + ["stash", "-q"], cwd=ws); subprocess.run(["git", "reset", "-q", "--hard"], cwd=ws)
    assert "uncommitted edit" in (p / "src/a.py").read_text(), "stash and reset in the copy never touch the user's work"
    assert not subprocess.run(["git", "remote"], cwd=ws, capture_output=True, text=True).stdout.strip(), "no remote: a push can't reach the project"
    assert not (ws / "dist").exists(), "git-ignored build output is never copied"
    def ask(cwd, tool, **ti):
        return "deny" in run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(cwd), "agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v1"})).stdout
    import shlex as _sh
    assert not ask(p, "Bash", command=f"cd {_sh.quote(str(ws))} && ls"), "the cd the agent is told to use is accepted however it is quoted"
    assert not ask(ws, "Bash", command=f"cd {_sh.quote(str(ws))} && ls"), "after its first cd the session's cwd is the copy: the guard still finds the workspace"
    assert ask(ws, "Read", file_path=str(p / ".critic/reviews/review-B.json")), "and still guards the project's .critic"
    assert not ask(ws, "Grep", pattern="x"), "a Grep with no path searches the copy (the current folder)"
    assert ask(p, "Glob", pattern="**/*.json"), "a root Glob that matches .critic files is refused on every Python"
    blocked = run(H / "check_contract.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v1", "cwd": str(ws), "last_assistant_message": "no json here"})).stdout
    assert '"block"' in blocked and ws.is_dir(), "a blocked stop keeps the copy: the agent is still working"
    run(H / "check_contract.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v1", "cwd": str(ws), "stop_hook_active": True}))
    assert not ws.exists(), "the real finish deletes it, from inside the copy too"
    sys.path.insert(0, str(H)); import importlib; wsm = importlib.import_module("workspace")
    real_link = os.symlink
    def no_links(*a, **k): raise OSError(1314, "A required privilege is not held by the client")
    write(p, "node_modules/x/i.js", "1\n"); os.symlink = no_links
    try: rec2 = wsm.make(p, "win1")
    finally: os.symlink = real_link
    assert rec2 and not rec2.get("building") and "node_modules" in rec2["links_skipped"] and (pathlib.Path(rec2["payload"]) / "src/a.py").exists(), rec2
    from critic_findings import strip_workspace_path
    assert strip_workspace_path("/u/John Smith/p/.critic/scratch/abc/payload/src/a.py") == "src/a.py"

@test("5.0 SC-31 blind review: critic_run never loops on dedup, never applies an earlier run's verdicts, and waits for every verifier batch")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    g1 = finding(category="domain", impact="High", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    g2 = finding(category="xss", impact="High", line=2, quote=APP.splitlines()[1].strip(), title="Second issue")
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g1, g2]))
    write(d, ".critic/verdicts/9.json", json.dumps([{"id": "F-stale", "verdict": "refuted"}])); old = time.time() - 3600; os.utime(d / ".critic/verdicts/9.json", (old, old))
    out = run(S / "critic_run.py", "next", cwd=d).stdout; assert "curmudgeon-dedup" in out, out
    write(d, ".critic/groups.json", json.dumps({"groups": []}))
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "curmudgeon-dedup" not in out and "curmudgeon-verifier" in out, "after the groups tally the run goes on to verification: " + out
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]; assert len(ids) == 2, ids
    write(d, ".critic/verdicts/1.json", json.dumps([{"id": ids[0], "verdict": "unclear", "reproduced": "no"}]))
    st = run(S / "critic_run.py", "status", cwd=d).stdout
    assert ": verify" in st and ids[1] in st and ids[0] not in st, "half the verdicts is not done: " + st
    write(d, ".critic/verdicts/2.json", json.dumps([{"id": ids[1], "verdict": "unclear", "reproduced": "no"}]))
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "write the teardown" in out and "9.json" not in out, out
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    assert not (d / ".critic/verdicts").exists() and list((d / ".critic/history").glob("run-*/verdicts/1.json")), "a new run starts with no verdicts; the old ones are archived"

@test("5.0 SC-41: the README compares Curmudgeon with Anthropic's review options (dated and sourced), gives a CI recipe with the action's real inputs, and says the reviewers share one model")
def _(d):
    r = (HERE.parent / "README.md").read_text()
    assert r == (HERE / "README.md").read_text(), "the two READMEs must match"
    assert "## How it compares with Anthropic's own review options" in r and "code.claude.com/docs/en/ultrareview" in r and "24 October 2026" in r
    assert "plugin_marketplaces:" in r and "plugins: curmudgeon@curmudgeon" in r and "hasn't been run by us yet" in r and "secrets.ANTHROPIC_API_KEY" in r
    assert "All three are the same model" in r and "/curmudgeon:review quiet" in r

@test("5.0 §5.29 round 2: git from notes never reaches the project, any cwd in scratch maps to the project, lite runs reach the teardown, nested repos and absolute globs are handled")
def _(d):
    G = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    p = d / "proj"; write(p, "src/app.js", APP); write(p, "vendor/lib/lib.c", "int x;\n"); write(p, ".next/cache/blob", "x" * 100)
    subprocess.run(["git", "init", "-q"], cwd=p / "vendor/lib"); subprocess.run(["git", "add", "."], cwd=p / "vendor/lib"); subprocess.run(G + ["commit", "-qm", "lib"], cwd=p / "vendor/lib")
    write(d, "outside/one.txt", "real\n"); os.symlink(d / "outside/one.txt", p / "src/one.txt")
    subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "src"], cwd=p); subprocess.run(G + ["commit", "-qm", "base"], cwd=p)
    write(p, "src/app.js", APP + "// uncommitted\n"); write(p, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]')
    run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(p)}))
    rec = json.loads((p / ".critic/scratch/r1/workspace.json").read_text()); ws = pathlib.Path(rec["payload"]); notes = pathlib.Path(rec["notes"])
    subprocess.run(G + ["stash", "-q"], cwd=notes, capture_output=True)
    assert "// uncommitted" in (p / "src/app.js").read_text() and not subprocess.run(["git", "stash", "list"], cwd=p, capture_output=True, text=True).stdout.strip(), "git from notes must not reach the project"
    lst = subprocess.run(["git", "ls-files"], cwd=ws, capture_output=True, text=True).stdout
    assert (ws / "src/app.js").exists() and (ws / "vendor/lib/lib.c").read_text() == "int x;\n" and "vendor/lib" in rec["nested"], rec
    assert not (ws / "src/one.txt").is_symlink() and (ws / "src/one.txt").read_text() == "real\n", "an outside file link becomes a copy"
    (ws / "src/one.txt").write_text("changed in copy\n"); assert (d / "outside/one.txt").read_text() == "real\n"
    def ask(cwd, tool, **ti):
        return "deny" in run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(cwd), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert ask(notes, "Read", file_path=str(p / ".critic/reviews/review-B.json")), "a cwd in notes still guards the project's .critic"
    assert not ask(notes, "Bash", command=f"cd {ws} && ls"), "and still finds the workspace"
    assert not ask(p, "Bash", command=f"git -C {ws} log --oneline") and ask(p, "Bash", command=f"git -C {ws} log; grep -rn SECRET .") and ask(p, "Bash", command=f"git -C {p} log")
    assert ask(p, "Glob", pattern=str(p) + "/**/review-*.json", path=str(p)), "an absolute Glob pattern is expanded with dot-folders"
    e = d / "lite"; write(e, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=e)
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code", verified="executed")
    write(e, ".critic/reviews/review-A.json", json.dumps([g]))
    out = run(S / "critic_run.py", "next", cwd=e)
    assert out.returncode == 0 and "write the teardown" in out.stdout, "a lite run with only a Medium reaches the teardown: " + out.stdout + out.stderr
    assert (e / ".critic/findings.jsonl").exists()

@test("5.0 SC-63: ast_view prints the Python syntax tree for a line range, says 'no parser' for other languages, and briefs name it")
def _(d):
    write(d, "t.py", 'import os\n\ndef f(x):\n    if x is None or x == "a < b":\n        return os.path.join("a", x)\n    return x + 1\n')
    r = run(S / "ast_view.py", "t.py", "4", cwd=d)
    assert r.returncode == 0 and "If L4-5" in r.stdout and "BoolOp L4 (op=Or)" in r.stdout and "value='a < b'" in r.stdout and "Return L6" not in r.stdout, r.stdout
    r = run(S / "ast_view.py", "x.js", cwd=d); assert r.returncode == 3 and "no parser" in r.stdout
    write(d, "bad.py", "def f(:\n"); r = run(S / "ast_view.py", "bad.py", cwd=d); assert r.returncode == 2 and "syntax error" in r.stdout
    write(d, "src/a.py", "x = 1\n"); run(S / "critic_map.py", "--files", "src/a.py", cwd=d); run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    run(S / "critic_brief.py", cwd=d); assert "ast_view.py FILE" in (d / ".critic/briefs/brief-A.md").read_text()

@test("5.0 SC-48: the tests-of-the-tests lens finds every planted defect, flags no decoy and nothing in the clean twin, and the lens check can fail")
def _(d):
    L = HERE.parent / "eval" / "lens.py"; K = HERE.parent / "eval" / "lens5.json"
    r = run(L, str(K), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["verdict"] == "PASS" and out["recall"] == "7 of 7" and out["precision"] == "7 of 7", out
    k = json.loads(K.read_text()); k["planted"].append({"id": "TX", "rule": "test-no-assert", "where": "tests/test_cart.py:14", "why": "deliberately wrong"})
    for x in ("fixture", "clean"): k[x] = str(HERE.parent / "eval" / k[x])
    bad = write(d, "bad.json", json.dumps(k)); r = run(L, str(bad), cwd=d)
    assert r.returncode == 1 and "FAIL" in r.stdout, "a lens check that can't fail proves nothing: " + r.stdout
    write(d, "tests/test_x.py", "def test_a():\n    assert (1 == 2, 'm')\n\ndef test_b():\n    import time\n    time.sleep(1)\n    assert True is not False\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = {x["rule"]: x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "tests"}
    assert rows["test-const-assert"]["sev"] == "FAIL" and rows["test-sleep"]["tier"] == "pedantic" and "test-no-assert" not in rows, rows
    imp = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(S)!r}); from critic_merge import scan_impact; print(scan_impact('test-const-assert'))"], cwd=d, capture_output=True, text=True).stdout.strip()
    assert imp == "Medium", imp

@test("5.0 SC-49: a live page loads only when scope.json lists its origin and the run carries the typed host; the file is data, strictly read")
def _(d):
    write(d, "index.html", "<!doctype html><title>x</title><p>x</p>")
    def scan(*extra):
        run(S / "critic_scan.py", ".", "--root", ".", "--page", "http://staging.example.invalid/", *extra, cwd=d)
        rep = json.loads((d / ".critic/scan/report.json").read_text())
        return [r["what"] for r in rep["findings"] if r["rule"] == "live-refused"]
    assert any("no .critic/scope.json" in w for w in scan()), "no scope file: refused"
    assert any("no .critic/scope.json" in w for w in scan("--allow-live", "staging.example.invalid")), "the old flag alone is not enough"
    write(d, ".critic/scope.json", json.dumps({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "max_requests": 50, "note": "test copy"}]}))
    assert any("typed confirmation" in w for w in scan()), "listed but not confirmed this run: refused"
    assert any("typed confirmation" in w for w in scan("--allow-live", "other.example.invalid")), "the wrong host: refused"
    assert not scan("--allow-live", "staging.example.invalid"), "listed and confirmed: not refused"
    run(S / "critic_scan.py", ".", "--root", ".", "--page", "http://evil.example.invalid/", "--allow-live", "evil.example.invalid", cwd=d)
    assert any("not a target" in r["what"] for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"] == "live-refused")
    for bad, why in [({"version": 1, "targets": [{"origin": "http://u:p@staging.example.invalid"}]}, "user name"), ({"version": 1, "targets": [{"origin": "http://staging.example.invalid/admin"}]}, "no path"),
                     ({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "methods": ["POST"]}]}, "may not have"), ({"version": 1, "targets": [], "allow": "all"}, "may not have"),
                     ({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "max_requests": 10 ** 6}]}, "max_requests")]:
        write(d, ".critic/scope.json", json.dumps(bad)); w = scan("--allow-live", "staging.example.invalid")
        assert any(why in x for x in w), (bad, w)
    (d / ".critic/scope.json").unlink(); write(d, "elsewhere.json", json.dumps({"version": 1, "targets": [{"origin": "http://staging.example.invalid"}]})); os.symlink(d / "elsewhere.json", d / ".critic/scope.json")
    r = run(S / "critic_scan.py", ".", "--root", ".", "--page", "http://staging.example.invalid/", "--allow-live", "staging.example.invalid", cwd=d)
    assert r.returncode == 2 and "link" in r.stderr, "a linked scope file stops the scan: never read through a link"
    (d / ".critic/scope.json").unlink()
    run(S / "critic_scan.py", ".", "--root", ".", "--page", "index.html", cwd=d)
    assert not [r for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"] == "live-refused"], "a local file never needs a scope"

@test("5.0 SC-50: the strict YAML reader keeps every scalar a string, matches the pinned outputs, gives lines for findings, and refuses what it can't read safely")
def _(d):
    sys.path.insert(0, str(S)); import importlib; Y = importlib.import_module("yaml_lite")
    for f in sorted((HERE / "tests" / "yaml").glob("*.y*ml")):
        exp = json.loads(f.with_name(f.name.rsplit(".", 1)[0] + ".expected.json").read_text())
        try: got = {"data": Y.plain(Y.loads(f.read_text()))}
        except Y.Refused as e: got = {"refused_line": e.line, "why": e.why}
        assert got == exp, (f.name, got, exp)
    doc = Y.loads((HERE / "tests" / "yaml" / "ci-target.yml").read_text())
    assert "on" in doc and doc["on"] == "pull_request_target", "the key on stays the string on"
    steps = doc["jobs"]["build"]["steps"]
    assert steps.item_lines[0] == 8 and steps[1]["run"].line == 11 and doc.key_lines["jobs"] == 3
    for bad in ["a: *x", "a: !!str 1", "? complex\n: v", "%YAML 1.2\n---\na: 1", "a: [1, 2", "a: b: c", "- - x"]:
        try: Y.loads(bad); assert False, f"should refuse: {bad!r}"
        except Y.Refused: pass
    assert Y.plain(Y.loads("yes: no\nn: 010\nv: 1.0")) == {"yes": "no", "n": "010", "v": "1.0"}

@test("5.0 SC-51: the CI and supply-chain lens finds every planted defect, flags no decoy and nothing in the clean twin, and refuses to guess at YAML it can't read")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens6.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "13 of 13" and out["precision"] == "13 of 13", out
    write(d, ".github/workflows/x.yml", "on: push\nanchors: &a\n  k: v\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = [x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "supply-chain"]
    assert [(x["rule"], x["where"]) for x in rows] == [("ci-not-checked", ".github/workflows/x.yml:2")], rows
    imp = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(S)!r}); from critic_merge import scan_impact; print(scan_impact('ci-pwn-request'))"], cwd=d, capture_output=True, text=True).stdout.strip()
    assert imp == "Critical", imp

@test("5.0 fix: every script runs in Python's isolated mode (-I), as the golden tests and the background check run them")
def _(d):
    write(d, "src/a.py", "x = 1\n")
    for script, args in [("critic_scan.py", [".", "--root", ".", "--no-project-rules"]), ("critic_map.py", ["--files", "src/a.py"]), ("critic_brief.py", []), ("ast_view.py", ["src/a.py"])]:
        r = subprocess.run([sys.executable, "-I", str(S / script), *args], cwd=d, capture_output=True, text=True, env=dict(os.environ, CRITIC_ROOT=str(d)))
        assert r.returncode == 0 and "Traceback" not in r.stderr, (script, r.stderr[-400:])

@test("5.0 SC-52: the agent and MCP configuration lens finds every planted defect, flags no decoy and nothing in the clean twin")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens7.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "7 of 7" and out["precision"] == "7 of 7" and out["pedantic_rows"] == 1, out
    write(d, ".mcp.json", "{not json"); run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert [x["rule"] for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "agent-config"] == ["agent-not-checked"]

@test("5.0 SC-53: the release and rollback lens finds every planted defect, flags no decoy and nothing in the clean twin; SQL is split outside quotes")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens8.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "7 of 7" and out["precision"] == "7 of 7", out
    sys.path.insert(0, str(S)); import importlib; M = importlib.import_module("scan_migrations")
    st = M._statements("CREATE FUNCTION f() AS $$ BEGIN; x; END; $$ LANGUAGE plpgsql;\n-- a; comment\nSELECT 'a;b';\n/* c;\n d */ SELECT 1;")
    assert [l for l, _ in st] == [1, 3, 5] and st[1][1] == "SELECT 'a;b'", st

@test("5.0 SC-55: requirements are tabled with the tests that cite them, undefined and untested ids are found, and an inferred requirement can't make a finding Critical or High")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens9.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "4 of 4" and out["precision"] == "4 of 4", out
    write(d, "src/app.js", APP); write(d, "docs/spec.md", "# Spec\n\n- REQ-1: tax is computed by the server, never in the view.\n")
    base = finding(category="domain", impact="High", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    rows = [dict(base, requirement={"basis": "inferred", "why": "pricing usually lives on the server"}),
            dict(base, category="intent", title="Contradicts the spec", requirement={"basis": "stated", "where": "docs/spec.md:3"}),
            dict(base, category="intent-2", title="Cites a line that isn't there", requirement={"basis": "stated", "where": "docs/spec.md:99"})]
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps(rows))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text()); got = {f["category"]: f for f in t["kept"] + t["contested"]}
    assert got["domain"]["impact"] == "Medium" and got["domain"]["impact_capped_from"] == "High", got["domain"]
    assert got["intent"]["impact"] == "High" and "impact_capped_from" not in got["intent"]
    assert got["intent-2"]["impact"] == "Medium" and got["intent-2"]["requirement"]["basis"] == "inferred", got["intent-2"]
    from critic_findings import validate
    assert validate(dict(base, requirement={"basis": "stated"})) and validate(dict(base, requirement={"basis": "inferred"})) and not validate(dict(base, requirement={"basis": "inferred", "why": "x"}))
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "## Capped at Medium" in (d / ".critic/counts.md").read_text()

@test("5.0 SC-54: the operations lens finds every planted defect, flags no decoy and nothing in the clean twin")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens10.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "6 of 6" and out["precision"] == "6 of 6", out
    write(d, "k8s/app.yaml", "kind: Deployment\nspec:\n  template:\n    spec:\n      containers:\n        - name: app\n          image: x:1\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = {x["rule"]: x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "operations"}
    assert rows["ops-k8s-no-probes"]["tier"] == "pedantic" and rows["ops-k8s-no-limits"]["where"] == "k8s/app.yaml:6", rows

@test("5.0 SC-56: the variant hunt finds the same pattern elsewhere, and only blind-confirmed variants are reported, apart from the main counts")
def _(d):
    write(d, "src/a.js", "function show(el, name) {\n  el.innerHTML = '<b>' + name + '</b>';\n}\n")
    write(d, "src/b.js", "function card(box, title) {\n  box.title = title;\n  el.innerHTML = '<i>' + name + '</i>';\n}\n")
    write(d, "src/c.js", "function safe(el, name) {\n  el.textContent = name;\n}\n")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    f = {"id": "F-abcdef12", "category": "xss", "impact": "High", "confidence": "confirmed", "file": "src/a.js", "line": 2, "quote": "el.innerHTML = '<b>' + name + '</b>';",
         "title": "Name rendered as HTML", "failing_case": "name = <img src=x onerror=alert(1)> runs script"}
    write(d, ".critic/findings.jsonl", json.dumps(f) + "\n")
    out = run(S / "critic_variants.py", "find", cwd=d).stdout
    pk = sorted((d / ".critic/verify-variants").glob("*.json")); assert len(pk) == 1, (out, pk)
    p = json.loads(pk[0].read_text()); assert p["file"] == "src/b.js" and p["line"] == 3 and p["variant_of"] == "F-abcdef12", p
    write(d, "v.json", json.dumps([{"id": p["id"], "verdict": "unclear", "reproduced": "no"}]))
    run(S / "critic_variants.py", "apply", "v.json", cwd=d)
    assert (d / ".critic/variants.jsonl").read_text() == "" and "Not verified (no verdict or unclear; not findings): 1" in (d / ".critic/variants.md").read_text()
    write(d, "v.json", json.dumps([{"id": p["id"], "verdict": "confirmed", "reproduced": "traced", "entry": "card() is called with a user-supplied title and name", "path": ["src/b.js:3 assigns markup built from name to innerHTML"]}]))
    run(S / "critic_variants.py", "apply", "v.json", cwd=d)
    v = [json.loads(x) for x in (d / ".critic/variants.jsonl").read_text().splitlines()]
    assert len(v) == 1 and v[0]["source"] == "variant" and "Confirmed by blind verification: 1" in (d / ".critic/variants.md").read_text()
    assert "verify-variants" in (HERE / "hooks" / "read_guard.py").read_text()

@test("5.0 SC-57: reviewers and verifiers may use the LSP tool when a code-intelligence plugin makes it work, and the blindness guard judges its paths")
def _(d):
    write(d, ".critic/reviews/review-B.json", "[]"); write(d, "src/a.py", "x = 1\n")
    def ask(**ti):
        return "deny" in run(H / "read_guard.py", cwd=d, stdin=json.dumps({"tool_name": "LSP", "tool_input": ti, "cwd": str(d), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "me"})).stdout
    assert ask(operation="documentSymbol", filePath=str(d / ".critic/reviews/review-B.json")) and ask(uri="file://" + str(d / ".critic/reviews/review-B.json"))
    assert not ask(operation="findReferences", filePath=str(d / "src/a.py"), line=1, character=1)
    for a in ("curmudgeon-reviewer.md", "curmudgeon-verifier.md"): assert '"LSP"' in (HERE / "agents" / a).read_text()
    assert "LSP" in json.loads((H / "hooks.json").read_text())["hooks"]["PreToolUse"][1]["matcher"]

@test("5.0 SC-58 and SC-64: other tools' SARIF is read under the right lens, a line both tools flag is one row, and Semgrep in use is noticed but never run")
def _(d):
    write(d, "app.py", "import os\n\ndef run(cmd):\n    os.system(cmd)\n")
    sarif = {"runs": [{"tool": {"driver": {"name": "Semgrep OSS"}}, "results": [
        {"ruleId": "python.lang.security.audit.dangerous-system-call", "level": "error", "message": {"text": "os.system with a variable"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": "app.py"}, "region": {"startLine": 4}}}]},
        {"ruleId": "python.flask.debug", "level": "warning", "message": {"text": "debug on"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": "app.py"}, "region": {"startLine": 1}}}]}]},
        {"tool": {"driver": {"name": "zizmor"}}, "results": [{"ruleId": "template-injection", "level": "error", "message": {"text": "x"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": ".github/workflows/a.yml"}, "region": {"startLine": 9}}}]}]}]}
    write(d, "semgrep.sarif", json.dumps(sarif)); write(d, ".semgrep.yml", "rules: []\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = json.loads((d / ".critic/scan/report.json").read_text())["findings"]
    at4 = [x for x in rows if x["where"] == "app.py:4"]
    assert len(at4) == 1 and at4[0].get("also_found_by") == "Semgrep OSS" and at4[0]["area"] == "safety", at4
    z = [x for x in rows if "zizmor" in x["rule"]]; assert z and z[0]["area"] == "supply-chain" and z[0]["level"] == "ci", z
    s1 = [x for x in rows if x["where"] == "app.py:1" and "Semgrep" in x["what"]]; assert s1 and s1[0]["area"] == "safety", s1
    note = [x for x in rows if x["rule"] == "semgrep-present"]
    assert note and "config .semgrep.yml" in note[0]["what"] and note[0]["tier"] == "pedantic" and "read as evidence" in note[0]["what"], note

@test("5.0 SC-62: the while-you-work scan hands a FAIL in the file just written back to Claude, once per version, and stays quiet when off, outside a Curmudgeon project or for its own agents")
def _(d):
    write(d, "app.py", "x = 1\n")
    def post(rel, agent=None):
        inp = {"tool_name": "Write", "tool_input": {"file_path": str(d / rel)}, "cwd": str(d)}
        if agent: inp["agent_type"] = agent
        return run(H / "scan_on_write.py", cwd=d, stdin=json.dumps(inp)).stdout
    write(d, "bad.py", "KEY = '@LIVE@'\n")
    assert not post("bad.py").strip(), "no ledger: not a Curmudgeon project yet, so silent"
    run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    out = post("bad.py"); assert '"block"' in out and "bad.py:1" in out, out
    assert not post("bad.py").strip(), "the same problem in the same version is shown once"
    write(d, "bad.py", "KEY = '@LIVE@'\n# touched\n"); assert '"block"' in post("bad.py"), "a new version shows it again"
    assert not post("app.py").strip() and not post("bad.py", agent="curmudgeon:curmudgeon-verifier").strip()
    assert not (d / ".critic/scan/report.json").exists(), "the review's scan report is never written by the watcher"
    run(S / "critic_ledger.py", "gate", "off", cwd=d); write(d, "bad.py", "KEY = '@LIVE@'\n# again\n")
    assert not post("bad.py").strip(), "gate off silences it"
    run(S / "critic_ledger.py", "gate", "async", cwd=d); assert '"block"' in post("bad.py"), "gate async turns it back on"

if __name__ == "__main__":
    shutil.rmtree(TMP, ignore_errors=True)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} passed"); sys.exit(1 if bad else 0)
