#!/usr/bin/env python3
"""Tests for Curmudgeon's scripts. No test framework needed: python3 tests/run_tests.py (exit 1 on any failure;
CRITIC_TEST_ONLY=<text> runs only the tests whose name contains it).
Each test builds its own scratch project in a temp folder and runs the real scripts against it."""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent.parent
S = HERE / "skills" / "review" / "scripts"; H = HERE / "hooks"
sys.path.insert(0, str(S))  # tests import the scripts directly (from critic_findings import validate, ...)
RESULTS = []
TMP = tempfile.mkdtemp(prefix="critic-tmp-")  # the hooks' TMPDIR, so agent workspaces made by tests are removed with it

def run(script, *a, cwd, stdin=None, env=None):
    e = dict(os.environ, CRITIC_ROOT=str(cwd), TMPDIR=TMP, CURMUDGEON_FEED_DIR=os.path.join(TMP, "no-feed")); e.update(env or {})  # a user's own feed never changes a test
    return subprocess.run([sys.executable, str(script), *a], cwd=cwd, capture_output=True, text=True, input=stdin, env=e, timeout=300)

ONLY = os.environ.get("CRITIC_TEST_ONLY", "")  # run only the tests whose name contains this text

def test(name):
    def deco(fn):
        if ONLY and ONLY not in name: return fn
        d = pathlib.Path(tempfile.mkdtemp(prefix="critic-test-"))
        try: fn(d); RESULTS.append((name, True, "")); print("PASS", name)
        except AssertionError as e:  # the line number too, so an assert without a message still says which one failed
            import traceback; ln = traceback.extract_tb(e.__traceback__)[-1].lineno
            RESULTS.append((name, False, f"line {ln}: {e}")); print("FAIL", name, "—", f"line {ln}: {e}")
        except Exception as e:
            import traceback; ln = next((f.lineno for f in reversed(traceback.extract_tb(e.__traceback__)) if f.filename == __file__), "?")
            RESULTS.append((name, False, f"line {ln}: {e!r}")); print("FAIL", name, "—", f"line {ln}: {e!r}")
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
    f = lambda file, line, title: {"file": file, "line": line, "category": "x", "impact": "High", "title": title, "quote": "", "evidence": "", "failing_case": ""}  # lines where each plant lives (decision 28)
    (c / "findings.jsonl").write_text(json.dumps(f("app.js", 44, "search responses race out of order, no abort")) + "\n")
    (c / "tally.json").write_text(json.dumps({"kept": [], "retracted": [{"finding": f("app.js", 11, "XSS: title into innerHTML unescaped")}],
                                               "dropped": [{"finding": f("store.js", 2, "JSON.parse at top level with no try: corrupt storage crashes load")}],
                                               "rejected": [], "suppressed": []}))
    (c / "refutations.jsonl").write_text(json.dumps(dict(f("store.js", 14, "pending save lost on close: no flush on beforeunload"), kind="refuted")) + "\n")
    (c / "reviews").mkdir(); (c / "reviews/review-A.json").write_text(json.dumps([f("store.js", 26, "persist swallows quota errors silently")]))
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
    assert not ask(V, "Read", file_path=str(d / ".critic/verify/F-1.json")) and not ask(V, "Read", file_path=str(d / ".critic/decisions.md")) and ask(V, "Read", file_path=str(d / ".critic/ledger.md"))  # decisions only: ledger.md holds dismissal notes
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

@test("5.0 SC-67: a stuck agent gets one rope, then a typed STUCK row, a refusal of the repeated action, and a line in counts.md")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v9", "cwd": str(d)}))
    ws = json.loads((d / ".critic/scratch/v9/workspace.json").read_text())["payload"]
    call = {"tool_name": "Bash", "tool_input": {"command": f"cd {ws} && node run.js"}, "agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v9", "cwd": str(d), "hook_event_name": "PostToolUse"}
    def post(resp): return run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(call, tool_response=resp))).stdout
    outs = [post({"stdout": "", "stderr": f"Error: cannot find module at 2026-10-24T05:0{i}:00Z", "exit_code": 1}) for i in range(3)]
    assert not outs[0].strip() and not outs[1].strip() and "rope (stuck_error_loop)" in outs[2], outs
    outs = [post({"stderr": "Error: cannot find module", "exit_code": 1}) for _ in range(3)]
    assert any("STUCK (stuck_error_loop)" in o for o in outs), outs
    pre = run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(call, hook_event_name="PreToolUse"))).stdout
    assert '"deny"' in pre, pre
    other = run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(call, hook_event_name="PreToolUse", tool_input={"command": f"cd {ws} && ls"}))).stdout
    assert not other.strip(), "only the repeated action is refused"
    row = json.loads((d / ".critic/stuck.jsonl").read_text().splitlines()[0]); assert row["type"] == "stuck_error_loop" and row["role"] == "verifier" and row["run"] == 1, row
    assert not run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(call, agent_type="general-purpose", tool_response={}))).stdout.strip(), "other agents are never watched"
    pp = {"tool_name": "Read", "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r9", "cwd": str(d), "hook_event_name": "PostToolUse", "tool_response": "ok"}
    run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r9", "cwd": str(d)}))
    seq = [run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(pp, tool_input={"file_path": f}))).stdout for f in ["a", "b", "a", "b", "a", "b"]]
    assert "stuck_pingpong" in seq[-1], seq
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code")
    write(d, ".critic/reviews/review-A.json", json.dumps([g])); run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d)
    write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "## Stuck" in (d / ".critic/counts.md").read_text() and "stuck_error_loop" in (d / ".critic/counts.md").read_text()

@test("5.0 SC-69: the job plan picks the lenses and agents for what is being reviewed, and quotes cost only from recorded history")
def _(d):
    write(d, "src/app.py", "x = 1\n"); write(d, "tests/test_app.py", "def test_x():\n    assert True is not False\n"); write(d, ".github/workflows/ci.yml", "on: push\njobs: {}\n")
    write(d, "db/migrations/0001.sql", "SELECT 1;\n"); write(d, ".mcp.json", "{}"); write(d, "docs/req.md", "- REQ-1: x\n")
    run(S / "critic_map.py", "--files", "src/app.py", "tests/test_app.py", ".github/workflows/ci.yml", "db/migrations/0001.sql", ".mcp.json", "docs/req.md", cwd=d)
    p = json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout)
    assert set(p["lenses"]) >= {"tests of the tests", "CI and supply chain", "agent and MCP configuration", "release and rollback", "requirements and intent"}, p
    assert p["expected_tokens"] is None and "not guessed" in p["expected_basis"]
    write(d, ".critic/cost.jsonl", "\n".join(json.dumps({"role": r, "input_tokens": n, "output_tokens": 0}) for r, n in [("reviewer", 1000), ("reviewer", 3000), ("verifier", 500)]) + "\n")
    p = json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout); assert p["expected_tokens"] == 2000 * p["reviewers"] + 500 * (2 if p["tier"] == "full" else 1) + (0 if p["reviewers"] == 1 else 0), p
    e = d / "doc"; write(e, "README.md", "# Hi\n\nSome words.\n"); run(S / "critic_map.py", "--files", "README.md", cwd=e)
    p = json.loads(run(S / "critic_plan.py", "--json", cwd=e).stdout)
    assert p["kind"] == "document or plan" and p["reviewers"] == 1 and p["lenses"] == [] and p["checks"] == ["claims, numbers and consistency"], p
    assert "plan:" in run(S / "critic_run.py", "begin", "--files", "README.md", cwd=e).stdout

@test("5.0 SC-66 and decision 29: the browser driver clicks anything in the simulation (writes answered, never sent) with a before-and-after check, refuses destructive controls only when writes are real, and blocks other origins and live sites outside the scope")
def _(d):
    B = S / "browse.py"
    write(d, "site/index.html", "<!doctype html><title>Shop</title><label for=q>Search</label><input id=q name=q>"
          "<button id=go onclick=\"document.getElementById('out').textContent='searched '+document.getElementById('q').value\">Search</button>"
          "<button id=del onclick=\"fetch('/api/items/1',{method:'DELETE'})\">Delete item</button>"
          "<button id=save onclick=\"fetch('/api/save',{method:'POST',body:'x'}).catch(()=>{})\">Save draft</button>"
          "<button id=ext onclick=\"fetch('https://tracker.example.invalid/t?u=me').catch(()=>{})\">Track</button><p id=out></p>")
    r = run(B, "start", "site/index.html", "--session", "s/s.json", cwd=d)
    try: import playwright  # noqa: F401
    except ImportError:
        assert r.returncode == 3 and "unavailable" in r.stdout, r.stdout; return  # CI without Playwright: the driver says so and stops
    assert "e3 button/submit \"Delete item\" [looks destructive: safe to try here, in the simulation]" in r.stdout and (d / "s/step-0.png").exists(), r.stdout
    run(B, "step", "type", "e1", "socks", "--session", "s/s.json", cwd=d)
    out = run(B, "step", "click", "e2", "--session", "s/s.json", "--expect", "the results line says it searched for socks", cwd=d).stdout
    assert "searched socks" in out and "expected: the results line says it searched" in out and "+searched socks" in out and "step-2-before.png" in out, out
    out = run(B, "step", "click", "e3", "--session", "s/s.json", cwd=d).stdout  # decision 29: in the simulation even Delete is clicked, and its request answered, never sent
    assert "answered by the simulation" in out and "DELETE http://127.0.0.1" in out, out
    out = run(B, "step", "click", "e4", "--session", "s/s.json", cwd=d).stdout; assert "POST" in out and "answered by the simulation" in out, out
    out = run(B, "step", "click", "e5", "--session", "s/s.json", cwd=d).stdout; assert "tracker.example.invalid/t?u=…" in out and "would have sent" in out, out
    r = run(B, "start", "http://shop.example.invalid/", "--session", "s/l.json", cwd=d); assert r.returncode == 2 and "scope.json" in r.stdout, r.stdout
    out = run(B, "start", "site/index.html", "--session", "s/w.json", "--allow-writes", cwd=d).stdout
    assert "[destructive: never clicked]" in out, "a session that sends data for real still refuses destructive controls: " + out
    r = run(B, "step", "click", "e3", "--session", "s/w.json", cwd=d); assert r.returncode == 2 and "never used" in r.stdout, r.stdout
    assert json.loads((d / "s/w.json").read_text())["steps"] == [], "a refused step is not recorded"
    out = run(B, "step", "click", "e4", "--session", "s/w.json", cwd=d).stdout
    assert re.search(r"POST http://127\.0\.0\.1:\d+/api/save 501", out) and "would have sent" not in out, "with the user's yes, a write reaches the local server: " + out

@test("5.0 SC-65: JavaScript code rules read code with strings and comments blanked, so a rule name in a comment or string is not a finding")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens11.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "6 of 6" and out["precision"] == "6 of 6" and not out["decoy_rows"], out
    write(d, "a.js", "el.addEventListener('input', save);\n// TODO: debounce\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rules = {x["rule"] for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"]}
    assert {"per-keystroke", "todo"} <= rules, "rules that read strings or comments on purpose still do: " + str(rules)

@test("5.0 SC-70: the death-match harness refuses to spend without --yes-spend, and scores every arm with one scorer, leaving precision NOT MEASURED until labelled")
def _(d):
    DM = HERE.parent / "eval" / "deathmatch.py"
    r = run(DM, "run", cwd=d); assert r.returncode == 2 and "--yes-spend" in r.stdout
    assert re.search(r"\d+ arm\(s\) x 7 task\(s\)", run(DM, "plan", cwd=d).stdout)
    key = json.loads((HERE.parent / "eval" / "answer_key4.json").read_text()); g2 = next(k for k in key if k.startswith("G2"))
    rd = d / "runs"; (rd / "plain-claude" / "suite4").mkdir(parents=True); (rd / "plain-claude" / "suite4-clean").mkdir(parents=True)
    (rd / "plain-claude" / "suite4" / "output.md").write_text("Findings:\n\n1. guards.js:10 canVoid uses indexOf truthiness, so -1 passes and a viewer can void.\n2. app.js:9 the total is wrong for empty carts.\n")
    (rd / "plain-claude" / "suite4-clean" / "output.md").write_text("- app.js:4 possible bug: the price may overflow.\n")
    (rd / "curmudgeon" / "suite4").mkdir(parents=True)
    (rd / "curmudgeon" / "suite4" / "findings.jsonl").write_text(json.dumps({"file": "guards.js", "line": 10, "title": "viewer can void", "evidence": "indexOf returns -1 (truthy)"}) + "\n")
    out = run(DM, "score", str(rd), cwd=d).stdout
    res = {(x["arm"], x["task"]): x for x in json.loads((rd / "results.json").read_text())}
    p4 = res[("plain-claude", "suite4")]; assert p4["found"] >= 1 and p4["unlabelled"] == 1 and p4["precision"] is None, p4
    assert res[("plain-claude", "suite4-clean")]["false_alarms"] == 1 and res[("curmudgeon", "suite4")]["found"] >= 1
    (rd / "labels.json").write_text(json.dumps({"plain-claude/suite4/1": "false"})); run(DM, "score", str(rd), cwd=d)
    p4 = {(x["arm"], x["task"]): x for x in json.loads((rd / "results.json").read_text())}[("plain-claude", "suite4")]
    assert p4["unlabelled"] == 0 and p4["precision"] == f"{p4['found']} of {p4['found'] + 1}", p4

@test("5.0 audit mode: begin --audit is the full tier with rules of engagement, warns about a shipped .mcp.json, and audit fields are validated")
def _(d):
    write(d, "src/app.js", APP); write(d, ".mcp.json", json.dumps({"mcpServers": {"x": {"command": "npx", "args": ["x"]}}}))
    out = run(S / "critic_run.py", "begin", "--audit", "--files", "src/app.js", cwd=d).stdout
    assert "audit, not repair" in out and "WARNING: this repository ships .mcp.json" in out and "A, B, C" in out, out
    assert json.loads((d / ".critic/ledger.json").read_text())["tier"] == "full"
    from critic_findings import validate
    g = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="t")
    assert not validate(dict(g, difficulty="High", exploit_scenario="x", fix_short="y", fix_long="z")) and validate(dict(g, difficulty="Extreme"))

@test("5.0 SC-18: the planter keeps only mutants a behaviour test proves broken, and writes an answer key for them")
def _(d):
    ev = d
    write(ev, "tiny-clean/calc.py", "def total(xs):\n    return sum(xs)\n\n\ndef is_empty(xs):\n    return len(xs) == 0\n\n\ndef label():\n    return 'ok'\n")
    write(ev, "behaviour_tiny.py", "import runpy, pathlib\ndef run(d):\n    m = runpy.run_path(str(pathlib.Path(d) / 'calc.py'))\n    return {'empty list is empty': m['is_empty']([]) is True, 'non-empty is not': m['is_empty']([1]) is False}\n")
    r = run(HERE.parent / "eval" / "planter.py", str(ev / "tiny-clean"), str(ev / "behaviour_tiny.py"), "--out", "tiny", "--max", "5", "--dest", str(ev), cwd=ev)
    key = json.loads((ev / "answer_key_tiny.json").read_text())
    assert key and all(v["synthetic"] and v["breaks"] for v in key.values()), (r.stdout, key)
    assert all("calc.py:" in k for k in key) and (ev / "tiny-1" / "calc.py").read_text() != (ev / "tiny-clean" / "calc.py").read_text()
    assert not any("label" in k or ":10" in k for k in key), "a change no behaviour check notices is never kept"

@test("5.0 card-E review: the browser can reach nothing but the page's own origin (WebSockets, redirects, service workers, symlinks), destructive controls can't be reached by other verbs or a swap, and sessions aren't trusted")
def _(d):
    try: import playwright  # noqa: F401
    except ImportError: return  # no browser here: the driver reports unavailable (tested in SC-66)
    import http.server as hs, threading
    hits = []
    class Sink(hs.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _h(self): hits.append(f"{self.command} {self.path}"); self.send_response(200); self.end_headers(); self.wfile.write(b"SINK")
        do_GET = do_POST = _h
    sink = hs.ThreadingHTTPServer(("127.0.0.1", 0), Sink); threading.Thread(target=sink.serve_forever, daemon=True).start(); sp_ = sink.server_address[1]
    other = f"127.0.0.1:{sp_}"
    write(d, "outside/secret.txt", "TOPSECRET"); (d / "site").mkdir(); os.symlink(d / "outside/secret.txt", d / "site/leak.txt")
    write(d, "site/sw.js", f"self.addEventListener('install', e => {{ fetch('http://{other}/from-sw', {{method: 'POST'}}); }});")
    write(d, "site/index.html", "<!doctype html><title>t</title><p id=o></p><script>"
          "fetch('/leak.txt').then(r=>r.text()).then(t=>document.getElementById('o').textContent='leak:'+t);"
          f"try{{const w=new WebSocket('ws://{other}/ws');w.onopen=()=>w.send('x');}}catch(e){{}}"
          f"fetch('http://{other}/direct').catch(()=>{{}}); navigator.serviceWorker && navigator.serviceWorker.register('sw.js').catch(()=>{{}});"
          "</script><form action='delete-account.html'><input id=n aria-label=Name></form>"
          "<button id=deleteBtn>Go</button><input type=checkbox id=purge aria-label=Option>"
          f"<button id=nx onclick=\"location='http://{other}/away'\">Next</button>")
    B = S / "browse.py"; ses = "s/s.json"
    out = run(B, "start", "site/index.html", "--session", ses, "--allow-writes", cwd=d).stdout  # writes for real, so the destructive backstop is on (decision 29)
    assert "TOPSECRET" not in out and "leak.txt 404" in out, "a link out of the served folder is never served: " + out
    refs = {m.group(2): m.group(1) for m in re.finditer(r"(e\d+) \S+ \"([^\"]*)\"", out)}
    assert "[destructive" in out.split("\"Go\"")[1].split("\n")[0], "deleteBtn reads as destructive by its id: " + out
    r = run(B, "step", "check", refs["Option"], "--session", ses, cwd=d); assert r.returncode == 2 and "destructive" in r.stdout, r.stdout
    r = run(B, "step", "type", refs["Name"], "bob", "--session", ses, cwd=d); assert r.returncode == 2 and "destructive" in r.stdout, "a field of a form that deletes is not used: " + r.stdout
    run(B, "step", "press", "Tab", "--session", ses, cwd=d)
    r = run(B, "step", "press", "Enter", "--session", ses, cwd=d); assert r.returncode == 2 and "destructive" in r.stdout, "Enter in that form is refused: " + r.stdout
    r = run(B, "step", "click", refs["Next"], "--session", ses, cwd=d); assert r.returncode == 2 and "left its origin" in r.stdout or "refused" in r.stdout, r.stdout
    time.sleep(0.5); assert not hits, f"nothing may reach another origin: {hits}"
    s_ = json.loads((d / ses).read_text()); s_["page"] = "http://localhost.:1/forged"; (d / ses).write_text(json.dumps(s_))
    r = run(B, "step", "snapshot", "--session", ses, cwd=d); assert r.returncode == 2 and "refused" in r.stdout, "a hand-edited session is checked again: " + r.stdout
    write(d, "swap/index.html", "<!doctype html><title>t</title><button id=b onclick=\"document.title='NEXT'\">Next page</button><script>"
          "new MutationObserver(()=>setTimeout(()=>{const b=document.getElementById('b'); b.textContent='Delete everything'; b.onclick=()=>{document.title='DELETED'};},20))"
          ".observe(document.getElementById('b'),{attributes:true});</script>")
    run(B, "start", "swap/index.html", "--session", "s/w.json", cwd=d)
    r = run(B, "step", "click", "e1", "--session", "s/w.json", cwd=d)
    assert "DELETED" not in r.stdout and ("changed" in r.stdout or "destructive" in r.stdout), r.stdout
    write(d, "w/index.html", "<!doctype html><title>t</title><button onclick=\"fetch('/save',{method:'POST',body:'x'}).catch(()=>{})\">Save draft</button>")
    run(B, "start", "w/index.html", "--session", "s/x.json", "--allow-writes", cwd=d); run(B, "step", "click", "e1", "--session", "s/x.json", cwd=d)
    r = run(B, "step", "snapshot", "--session", "s/x.json", cwd=d); assert r.returncode == 2 and "send it again" in r.stdout, r.stdout
    sink.shutdown()

@test("5.0 card-E review: stuck detection compares actions exactly (a search in a new folder is new) and writes one STUCK row per episode")
def _(d):
    run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(d)}))
    base = {"tool_name": "Grep", "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(d), "hook_event_name": "PostToolUse", "tool_response": "No matches found"}
    outs = [run(H / "stuck.py", cwd=d, stdin=json.dumps(dict(base, tool_input={"pattern": "eval", "path": f"/tmp/proj/src/{x}"}))).stdout for x in "abcdef"]
    assert not any(o.strip() for o in outs), outs
    same = dict(base, tool_input={"pattern": "eval", "path": "/tmp/proj/src/a"})
    for _ in range(6): run(H / "stuck.py", cwd=d, stdin=json.dumps(same))
    for _ in range(3): run(H / "stuck.py", cwd=d, stdin=json.dumps(same))
    assert len((d / ".critic/stuck.jsonl").read_text().splitlines()) == 2, "one row per episode, not one per call"

def _mod(name):
    sys.path.insert(0, str(S)); import importlib; return importlib.import_module(name)
E = object()  # where _rows puts its collecting emit() in a lens call (last, when not given)
def _rows(fn, *a):
    out = []; em = lambda sev, rid, area, where, what, ev="": out.append((sev, rid, where))
    fn(*[em if x is E else x for x in a]) if E in a else fn(*a, em); return out

@test("5.0 card-E review B #1: the agent-config lens reads ${input:..} and ${env:..} after Bearer as references, and paths and mode words aren't credentials")
def _(d):
    A = _mod("scan_agentcfg")
    def rules(cfg, rel=".mcp.json"): return [r for _, r, _ in _rows(A.scan, rel, json.dumps(cfg, indent=1), E, {})]
    assert "agent-literal-credential" not in rules({"servers": {"github": {"type": "http", "url": "https://api.example.invalid/mcp/", "headers": {"Authorization": "Bearer ${input:github_mcp_pat}"}}}}, ".vscode/mcp.json")
    assert "agent-literal-credential" not in rules({"mcpServers": {"x": {"command": "x", "headers": {"Authorization": "Bearer ${env:API_TOKEN}"}}}})
    for k, v in [("GOOGLE_APPLICATION_CREDENTIALS", "/Users/me/.config/gcloud/application_default_credentials.json"), ("AUTH_MODE", "service-account"),
                 ("TOKEN_FILE", "~/.config/x/token.json"), ("AUTH_TYPE", "oauth-device"), ("SECRETS_PATH", "C:\\Users\\me\\secrets.json"), ("AUTH_URI", "https://auth.example.invalid/o/oauth2")]:
        assert "agent-literal-credential" not in rules({"mcpServers": {"x": {"command": "x", "env": {k: v}}}}), (k, v)
    assert "agent-literal-credential" in rules({"mcpServers": {"x": {"command": "x", "env": {"API_TOKEN": "Zq9xEXAMPLEEXAMPLE7731"}}}}), "a real literal is still found"
    assert "agent-literal-credential" in rules({"mcpServers": {"x": {"command": "x", "headers": {"Authorization": "Bearer Zq9xEXAMPLEEXAMPLE7731"}}}})

@test("5.0 card-E review B #2, #3, #19, #20, #21: the YAML reader drops a byte-order mark, refuses deep nesting, reads block scalars as YAML does, allows tabs inside them, and reads long flow lists in linear time")
def _(d):
    Y = _mod("yaml_lite")
    assert Y.plain(Y.loads("\ufeffon: push\n")) == {"on": "push"}
    for bad in ["k: " + "[" * 1200 + "]" * 1200, "\n".join(" " * i + f"k{i}:" for i in range(3000)) + " x"]:
        try: Y.loads(bad); assert False, "deep nesting must be refused"
        except Y.Refused: pass
    for text, want in [("a: |+\n  x\n", "x\n"), ("a: |\n  x", "x"), ("a: |+\n  x\n\n", "x\n\n"), ("k: >\n\n  lead\n", "\nlead\n"),
                       ("a: |\n    x\n      \n    y\n", "x\n  \ny\n"), ("a: >\n  one\n  two\n\n  three\n", "one two\nthree\n")]:
        assert Y.plain(Y.loads(text))["a" if text.startswith("a") else "k"] == want, (text, Y.plain(Y.loads(text)), want)
    try: Y.loads("k: |\n    \n  # com\n"); assert False, "an over-indented leading blank line is refused, not guessed"
    except Y.Refused: pass
    wf = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: |\n          cat <<-EOF\n          \tindented with tab\n          EOF\n"
    assert Y.plain(Y.loads(wf))["jobs"]["a"]["steps"][0]["run"] == "cat <<-EOF\n\tindented with tab\nEOF\n"
    try: Y.loads("a:\n\tb: 1\n"); assert False, "a tab in structural indentation is still refused"
    except Y.Refused as e: assert "tab" in e.why
    t0 = time.time(); doc = Y.loads("k: [\n" + "".join(f"  item{i},\n" for i in range(4000)) + "]\n")
    assert len(doc["k"]) == 4000 and time.time() - t0 < 3, time.time() - t0
    w = d / ".github/workflows"; w.mkdir(parents=True); (w / "x.yml").write_text("on: push\njobs:\n  a:\n    runs-on: " + "[" * 1500 + "]" * 1500 + "\n")
    (d / "app.js").write_text("const x = 1;\n")
    r = run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert any(x["rule"] == "ci-not-checked" for x in rep["findings"]), [x["rule"] for x in rep["findings"]]
    (w / "bom.yml").write_text("\ufeffon: pull_request_target\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert any(x["rule"] == "ci-pwn-request" for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"]), "a workflow saved with a BOM is still read"

@test("5.0 card-E review B #3: a lens that crashes on one file is reported and the rest of the scan still runs")
def _(d):
    write(d, "app.js", APP); write(d, "tests/test_x.py", "def test_x():\n    pass\n")
    r = run(S / "critic_scan.py", ".", "--root", ".", cwd=d, env={"CRITIC_TEST_CRASH_LENS": "scan_tests"})
    rep = json.loads((d / ".critic/scan/report.json").read_text()); rules = {x["rule"] for x in rep["findings"]}
    assert "lens-crashed" in rules and "test-no-assert" not in rules and len(rules - {"lens-crashed"}) > 0, rules

@test("5.0 card-E review B #4-#7: CI rules know upload-artifact v4.4+, a guarded workflow_run, boolean-only expressions and Docker stage names")
def _(d):
    C = _mod("scan_ci")
    def rules(text): return [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", text)]
    up = "on: push\npermissions: read-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/upload-artifact@{v}\n        with:\n          name: site\n          path: .\n{extra}"
    assert "ci-upload-checkout" not in rules(up.format(v="v4", extra="")), "v4 now resolves to 4.4+, which leaves .git out"
    assert "ci-upload-checkout" not in rules(up.format(v="v5", extra=""))
    assert "ci-upload-checkout" in rules(up.format(v="v4", extra="          include-hidden-files: true\n"))
    assert "ci-upload-checkout" in rules(up.format(v="v3", extra="")) and "ci-upload-checkout" in rules(up.format(v="v4.3.6", extra=""))
    wr = ("on:\n  workflow_run:\n    workflows: [CI]\n    types: [completed]\npermissions:\n  contents: read\njobs:\n  deploy:\n    if: {guard}\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: actions/checkout@v4\n        with:\n          ref: ${{{{ github.event.workflow_run.head_sha }}}}\n      - run: ./deploy.sh\n")
    assert "ci-pwn-request" not in rules(wr.format(guard="github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'"))
    assert "ci-pwn-request" not in rules(wr.format(guard="github.event.workflow_run.head_repository.full_name == github.repository"))
    assert "ci-pwn-request" in rules(wr.format(guard="github.event.workflow_run.conclusion == 'success'")), "an unguarded one is still FAIL"
    inj = "on: pull_request_target\npermissions: {{}}\njobs:\n  l:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"x=${{{{ {e} }}}}\"\n"
    assert "ci-injection" not in rules(inj.format(e="startsWith(github.event.pull_request.title, 'chore')"))
    assert "ci-injection" not in rules(inj.format(e="github.event.pull_request.title == 'x'"))
    assert "ci-injection" in rules(inj.format(e="github.event.pull_request.title"))
    assert "ci-injection" in rules(inj.format(e="github.event.pull_request.title || 'none'")), "|| returns the value itself"
    rows = _rows(C.scan_text, "Dockerfile", "FROM node:20-alpine AS build\nRUN make\nFROM build AS test\nFROM nginx\n")
    assert [w for _, r, w in rows if r == "docker-latest"] == ["Dockerfile:4"], rows

@test("5.0 card-E review B #8, #9: conftest fixtures aren't tests, and try/except/else-fail is a real check")
def _(d):
    Tm = _mod("scan_tests")
    conf = "import pytest\n\n@pytest.fixture\ndef test_app():\n    app = make()\n    yield app\n\n@pytest.fixture()\ndef test_client(test_app):\n    yield test_app.client()\n"
    assert not _rows(Tm.scan, "tests/conftest.py", conf)
    assert not [r for _, r, _ in _rows(Tm.scan, "tests/test_f.py", conf) if r == "test-no-assert"], "a fixture named test_* is not a test anywhere"
    idiom = "import unittest\nclass P(unittest.TestCase):\n    def test_rejects(self):\n        try:\n            parse('{')\n        except Exception:\n            pass\n        else:\n            self.fail('accepted')\n"
    assert not [r for _, r, _ in _rows(Tm.scan, "tests/test_p.py", idiom) if r == "test-swallowed-error"]
    bad = "def test_x():\n    try:\n        assert f() == 1\n    except Exception:\n        pass\n"
    assert [r for _, r, _ in _rows(Tm.scan, "tests/test_p.py", bad) if r == "test-swallowed-error"], "a swallowed assert is still found"

@test("5.0 card-E review B #10: req-undefined only fires for an id family the project defines")
def _(d):
    R = _mod("scan_reqs")
    assert not _rows(R.check, {}, {"tests/test_geo.py": 'assert subdivision_name("FR-75") == "Paris"'})
    assert not _rows(R.check, {"docs/req.md": "- REQ-1: login works\n"}, {"tests/test_geo.py": 'assert name("FR-75") == "Paris"  # REQ-1'}), "FR- isn't a family this project uses"
    assert [r for _, r, _ in _rows(R.check, {"docs/req.md": "- REQ-1: login works\n"}, {"tests/test_a.py": "# covers REQ-2\n"})] == ["req-undefined", "req-untested"]

@test("5.0 card-E review B #11-#13: migrations know op.create_table, types with commas, serial columns, and split big SQL in linear time")
def _(d):
    M = _mod("scan_migrations")
    al = ("def upgrade():\n    op.create_table('users', sa.Column('id', sa.Integer))\n    op.execute(\"CREATE INDEX ix_users_name ON users (name)\")\n\ndef downgrade():\n    op.drop_table('users')\n")
    assert not [r for _, r, _ in _rows(M.scan, "alembic/versions/1.py", al) if r == "mig-index-blocking"]
    dj = "class Migration(migrations.Migration):\n    operations = [migrations.CreateModel(name='Note', fields=[]), migrations.RunSQL('CREATE INDEX ix ON app_note (t)', 'DROP INDEX ix')]\n"
    assert not [r for _, r, _ in _rows(M.scan, "app/migrations/0001.py", dj) if r == "mig-index-blocking"]
    assert "mig-not-null-no-default" in [r for _, r, _ in _rows(M.scan, "m.sql", "ALTER TABLE orders ADD COLUMN total numeric(12,2) NOT NULL;")]
    assert "mig-not-null-no-default" not in [r for _, r, _ in _rows(M.scan, "m.sql", "ALTER TABLE orders ADD COLUMN seq bigserial NOT NULL;")]
    assert "mig-not-null-no-default" not in [r for _, r, _ in _rows(M.scan, "m.sql", "ALTER TABLE orders ADD COLUMN a numeric(12,2) NOT NULL DEFAULT 0, ADD COLUMN b int;")]
    big = "INSERT INTO t VALUES ('a; b', $$x$$);\n" * 40000
    t0 = time.time(); n = len(M._statements(big)); assert n == 40000 and time.time() - t0 < 5, (n, time.time() - t0)

@test("5.0 card-E review B #14: ops-log-secret skips *_method style names and values passed through mask()")
def _(d):
    O = _mod("scan_ops")
    py = "import logging\nlogger = logging.getLogger()\nlogger.info('login %s %s', user.name, auth_method)\nlogger.debug('pw: %s', mask(password))\nlogger.info('k %s', redact(api_key))\nlogger.info('pw %s', password)\n"
    assert [w for _, r, w in _rows(O.scan, "app/x.py", py, E, str(d)) if r == "ops-log-secret"] == ["app/x.py:6"]
    assert [w for _, r, w in _rows(O.scan, "app/x.js", "console.log('t', mask(token));\nconsole.log('m', authMethod);\nconsole.log(token);\n", E, str(d)) if r == "ops-log-secret"] == ["app/x.js:3"]

@test("5.0 card-E review B #15: the plan never calls requirements.txt or CMakeLists.txt a document")
def _(d):
    write(d, "requirements.txt", "--extra-index-url https://pkgs.example.invalid/simple\nflask==3.0\n")
    (d / ".critic").mkdir(exist_ok=True); (d / ".critic/change-map.json").write_text(json.dumps({"files": ["requirements.txt"], "tier": "full"}))
    p = json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout)
    assert p["tier"] == "full" and p["kind"] != "document or plan" and "CI and supply chain" in p["lenses"], p
    (d / ".critic/change-map.json").write_text(json.dumps({"files": ["CMakeLists.txt"], "tier": "full"}))
    assert json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout)["kind"] != "document or plan"
    (d / ".critic/change-map.json").write_text(json.dumps({"files": ["docs/notes.txt", "README.md"], "tier": "full"}))
    assert json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout)["kind"] == "document or plan"

@test("5.0 card-E review B #16: lens.py fails a lens that adds a wrong row, so precision can fail the gate")
def _(d):
    ev = d / "ev"; shutil.copytree(HERE.parent / "eval" / "fixture7", ev / "fixture7"); shutil.copytree(HERE.parent / "eval" / "fixture7-clean", ev / "fixture7-clean")
    key = json.loads((HERE.parent / "eval" / "lens7.json").read_text()); key["planted"] = key["planted"][1:]
    key["fixture"] = str(ev / "fixture7"); key["clean"] = str(ev / "fixture7-clean"); (d / "k.json").write_text(json.dumps(key))
    r = run(HERE.parent / "eval" / "lens.py", str(d / "k.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert out["false_rows"] and out["verdict"] == "FAIL" and r.returncode == 1, out

@test("5.0 card-E review B #17, #18: the death-match scorer credits a plant only from the claim, the same way for every arm, and hides no failed run")
def _(d):
    DM = HERE.parent / "eval" / "deathmatch.py"; rd = d / "runs"
    def put(arm, task, name, text): (rd / arm / task).mkdir(parents=True, exist_ok=True); (rd / arm / task / name).write_text(text)
    put("curmudgeon", "suite1", "findings.jsonl", json.dumps({"file": "app.js", "line": 40, "category": "domain", "title": "Sort order of notes is reversed", "quote": "a.t - b.t",
        "failing_case": "two notes show newest last", "evidence": "app.js:40", "remediation": "escape the confusion: reverse the comparator"}) + "\n")
    put("plain-claude", "suite1", "output.md", "1. app.js:40 sort order of notes is reversed: two notes show newest last.\n   Fix: escape the confusion and reverse the comparator.\n")
    put("plain-claude", "suite1-clean", "output.md", "## Review of app.js and store.js\n\nI read every file. No bugs found.\n\n## Summary\n\n- No issues in store.js worth reporting.\n")
    (rd / "code-review" / "suite1").mkdir(parents=True); (rd / "code-review" / "suite1" / "meta.json").write_text(json.dumps({"error": "timeout after 3600 s"}))
    run(DM, "score", str(rd), cwd=d)
    res = {(x["arm"], x["task"]): x for x in json.loads((rd / "results.json").read_text())}
    assert res[("curmudgeon", "suite1")]["found"] == 0 and res[("plain-claude", "suite1")]["found"] == 0, "a word in the fix text credits nothing"
    assert res[("plain-claude", "suite1-clean")]["false_alarms"] == 0, res[("plain-claude", "suite1-clean")]
    cr = res[("code-review", "suite1")]; assert cr.get("error") and cr.get("recall") == "NOT MEASURED" and cr.get("found") is None, cr
    assert "timeout" in (rd / "report.md").read_text()
    src = (DM).read_text(); assert "TimeoutExpired" in src, "a run that times out is recorded, not fatal"

@test("5.0 card-E verify round: a comment inside a multi-line flow list is read as YAML reads it, never as an empty item")
def _(d):
    Y = _mod("yaml_lite")
    assert Y.plain(Y.loads("branches: [main, # primary\n  release]\n")) == {"branches": ["main", "release"]}
    assert Y.plain(Y.loads("k: {a: 1, # c\n  b: 2}\n")) == {"k": {"a": "1", "b": "2"}}
    assert Y.plain(Y.loads("k: ['--color=#fff', # c\n  'it''s', # d\n  x]\n")) == {"k": ["--color=#fff", "it's", "x"]}
    assert Y.plain(Y.loads("k: [a, b] # c\n")) == {"k": ["a", "b"]} and Y.plain(Y.loads("k: [a,\n  'b # not a comment']\n")) == {"k": ["a", "b # not a comment"]}
    C = _mod("scan_ci")
    wf = "on: [push, # deploys\n  pull_request_target]\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n"
    assert "ci-pwn-request" in [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", wf)], "the commented trigger list is read, so the rule fires"

@test("5.0 card-E verify round: agent config still FAILs a literal token in AUTH_HEADER or after Bearer under any key name")
def _(d):
    A = _mod("scan_agentcfg")
    def rules(env): return [r for _, r, _ in _rows(A.scan, ".mcp.json", json.dumps({"mcpServers": {"x": {"command": "x", "env": env}}}, indent=1), E, {})]
    assert "agent-literal-credential" in rules({"AUTH_HEADER": "Bearer Zq9xEXAMPLEEXAMPLE7731"})
    assert "agent-literal-credential" in rules({"TOKEN_TYPE": "Bearer Zq9xEXAMPLEEXAMPLE7731"})
    assert "agent-literal-credential" not in rules({"AUTH_URL": "https://auth.example.invalid/token"})

@test("5.0 card-E verify round: CI skips only real true/false expressions, honours parentheses on uploads, and a negated guard is no guard")
def _(d):
    C = _mod("scan_ci")
    def rules(text): return [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", text)]
    inj = "on: issue_comment\npermissions: {{}}\njobs:\n  l:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"${{{{ {e} }}}}\"\n"
    assert "ci-injection" in rules(inj.format(e="startsWith(github.event.comment.body, '/run') && github.event.comment.body || toJSON(github.event.issue.number)"))
    assert "ci-injection" not in rules(inj.format(e="startsWith(github.event.comment.body, '/run')"))
    up = "on: push\npermissions: read-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/upload-artifact@v4\n        with:\n          name: site\n          path: \"**\"\n"
    assert "ci-upload-checkout" not in rules(up)
    neg = ("on: pull_request_target\npermissions: {}\njobs:\n  a:\n    if: ${{ !(github.event.pull_request.head.repo.full_name == github.repository) }}\n    runs-on: x\n    steps:\n"
           "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n")
    assert "ci-pwn-request" in rules(neg)
    assert "ci-pwn-request" in rules(neg.replace("${{ !(github.event.pull_request.head.repo.full_name == github.repository) }}", "github.event.pull_request.head.repo.full_name != github.repository"))

@test("5.0 card-E verify round: migrations count only tables upgrade() creates, keep a column named serial, and read quotes in ADD clauses")
def _(d):
    M = _mod("scan_migrations")
    al = "def upgrade():\n    op.execute('CREATE INDEX ix ON orders (customer_id)')\n\ndef downgrade():\n    op.create_table('orders')\n"
    assert "mig-index-blocking" in [r for _, r, _ in _rows(M.scan, "alembic/versions/2.py", al)]
    assert "mig-not-null-no-default" in [r for _, r, _ in _rows(M.scan, "m.sql", "ALTER TABLE devices ADD COLUMN serial text NOT NULL;")]
    assert "mig-not-null-no-default" in [r for _, r, _ in _rows(M.scan, "m.sql", "ALTER TABLE t ADD COLUMN a text DEFAULT '(', ADD COLUMN b int NOT NULL;")]

@test("5.0 card-E verify round: only mask, redact and obfuscate count as masking a logged secret")
def _(d):
    O = _mod("scan_ops")
    py = "import logging\nlog = logging.getLogger()\nlog.info('t=%s', sanitize(token))\nlog.info('p=%s', sanitize_html(password))\nlog.info('k=%s', mask(api_key))\nlog.info('k=%s', redact_secret(api_key))\n"
    assert [w for _, r, w in _rows(O.scan, "app/y.py", py, E, str(d)) if r == "ops-log-secret"] == ["app/y.py:3", "app/y.py:4"]

@test("5.0 card-E verify round: the plan treats a .txt under requirements/ as build input")
def _(d):
    (d / ".critic").mkdir(); write(d, "requirements/base.txt", "flask==3.0\n")
    (d / ".critic/change-map.json").write_text(json.dumps({"files": ["requirements/base.txt"], "tier": "full"}))
    p = json.loads(run(S / "critic_plan.py", "--json", cwd=d).stdout); assert p["tier"] == "full" and "CI and supply chain" in p["lenses"], p

@test("5.0 card-E verify round: the death-match scorer uses a plant's line range when it has one, counts uncited clean-twin claims as unlabelled, keeps claims before Fix:, and calls an empty reply no output")
def _(d):
    DM = HERE.parent / "eval" / "deathmatch.py"; rd = d / "runs"
    def put(arm, task, name, text): (rd / arm / task).mkdir(parents=True, exist_ok=True); (rd / arm / task / name).write_text(text)
    put("plain-claude", "suite1-clean", "output.md", "- store.js: save() drops the last note when two notes share a title; this is a bug.\n- app.js:12 a race in search.\n")
    put("plain-claude", "suite1", "output.md", "1. **app.js:46** Fix: escape note titles (titles are injected unescaped, XSS)\n")
    put("code-review", "suite1", "output.md", "")
    run(DM, "score", str(rd), cwd=d)
    res = {(x["arm"], x["task"]): x for x in json.loads((rd / "results.json").read_text())}
    c = res[("plain-claude", "suite1-clean")]; assert c["false_alarms"] == 1 and c["unlabelled"] == 1 and c["precision"] is None, c
    assert res[("plain-claude", "suite1")]["found"] == 1, "the claim before Fix: on the same line still counts"
    assert res[("code-review", "suite1")]["error"] == "no output", res[("code-review", "suite1")]
    sys.path.insert(0, str(HERE.parent / "eval")); import importlib; dm = importlib.import_module("deathmatch")
    plants = {"X": {"file": "app.js", "lines": [40, 44], "any": ["escap"]}}
    hit = lambda loc, claim: dm.match_plants(plants, [{"loc": loc, "claim": claim}])
    assert not hit("app.js:120", "app.js:120 Pressing Escape doesn't clear the filter") and hit("app.js:42", "app.js:42 titles not escaped")

@test("5.0 card-E verify round: Enter typed as a newline is still Enter, same-origin sockets need consent, ids like delete1 count, labelled inputs work, and clicks are real")
def _(d):
    try: import playwright  # noqa: F401
    except ImportError: return
    B = S / "browse.py"
    write(d, "f/index.html", "<!doctype html><title>t</title><form action='delete-account.html'><input id=n aria-label=Name><button>Go</button></form>")
    write(d, "f/delete-account.html", "<!doctype html><title>DELETED</title>")
    run(B, "start", "f/index.html", "--session", "s/a.json", "--allow-writes", cwd=d); run(B, "step", "press", "Tab", "--session", "s/a.json", cwd=d)
    for k in ("\n", "\r", "Shift+Enter"):
        r = run(B, "step", "press", k, "--session", "s/a.json", cwd=d); assert "DELETED" not in r.stdout and "refused" in r.stdout, (repr(k), r.stdout)
    write(d, "w/index.html", "<!doctype html><title>t</title><script>try{const w=new WebSocket('ws://'+location.host+'/ws');w.onopen=()=>w.send('x');}catch(e){}</script>")
    r = run(B, "start", "w/index.html", "--session", "s/w.json", cwd=d); assert "a socket can't be simulated" in r.stdout, r.stdout
    write(d, "x/index.html", "<!doctype html><title>t</title><button id=delete1 onclick=\"document.title='DELETED'\">Go</button><button id=XMLDelete>Go</button><button id=DELETEALL>Go</button>")
    r = run(B, "start", "x/index.html", "--session", "s/x.json", "--allow-writes", cwd=d); assert r.stdout.count("[destructive: never clicked]") == 3, r.stdout
    write(d, "l/index.html", "<!doctype html><title>L</title><label for=a>I agree to the terms</label><input type=checkbox id=a onchange=\"document.title='AGREED'\">"
          "<button id=m onmousedown=\"document.title=event.isTrusted?'TRUSTED':'UNTRUSTED'\">Press</button>"
          "<div style='position:relative'><button id=c onclick=\"document.title='COVERED-CLICKED'\">Under</button><div style='position:absolute;inset:0;background:#fff'></div></div>")
    run(B, "start", "l/index.html", "--session", "s/l.json", cwd=d)
    r = run(B, "step", "check", "e1", "--session", "s/l.json", cwd=d); assert "title: AGREED" in r.stdout, r.stdout
    r = run(B, "step", "click", "e2", "--session", "s/l.json", cwd=d); assert "title: TRUSTED" in r.stdout, r.stdout
    r = run(B, "step", "click", "e3", "--session", "s/l.json", cwd=d); assert "COVERED-CLICKED" not in r.stdout and "covers it" in r.stdout, r.stdout
    s_ = json.loads((d / "s/l.json").read_text()); s_["requests_total"] = -100000; (d / "s/l.json").write_text(json.dumps(s_))
    r = run(B, "step", "snapshot", "--session", "s/l.json", cwd=d); assert r.returncode == 2 and "signature" in r.stdout, r.stdout
    write(d, "p/index.html", "<!doctype html><title>t</title><button id=delete_account onclick=\"location='wipe.html?all=1'\">Go</button>")
    run(S / "critic_scan.py", "p", "--root", ".", "--page", "p/index.html", cwd=d)
    note = json.loads((d / ".critic/scan/report.json").read_text())["checks"].get("interactive", {}).get("note", "")
    assert "1 skipped as destructive" in note, note

@test("5.0 card-E round 3: lens and scorer regressions (async downgrade, helper-created tables, mid-line Fix:, 'no issues' replies)")
def _(d):
    M = _mod("scan_migrations")
    al = "def upgrade():\n    op.execute('CREATE INDEX ix ON orders (customer_id)')\n\nasync def downgrade():\n    op.create_table('orders')\n"
    assert "mig-index-blocking" in [r for _, r, _ in _rows(M.scan, "alembic/versions/3.py", al)]
    helper = "def _make():\n    op.create_table('things')\n\ndef upgrade():\n    _make()\n    op.execute('CREATE INDEX ix ON things (a)')\n\ndef downgrade():\n    op.drop_table('things')\n"
    assert "mig-index-blocking" not in [r for _, r, _ in _rows(M.scan, "alembic/versions/4.py", helper)]
    sys.path.insert(0, str(HERE.parent / "eval")); import importlib; dm = importlib.import_module("deathmatch")
    assert "XSS" not in dm.FIX_strip("1. **app.js:120** — Pressing Esc doesn't clear the search box. **Fix:** sanitize titles too, they allow XSS.")
    assert "XSS" in dm.FIX_strip("1. **app.js:42** Fix: escape note titles (titles are injected unescaped, XSS)")
    assert dm.blocks_from("## Review\n- No issues found.\n") == [] and dm.blocks_from("- No bugs in store.js worth reporting.\n") == []

@test("5.0 card-E round 3: browser regressions (stale click guard, uppercase labels, wrapping labels, smooth scroll, idle sockets, worker sockets)")
def _(d):
    try: import playwright  # noqa: F401
    except ImportError: return
    B = S / "browse.py"
    write(d, "a/index.html", "<!doctype html><title>T</title><style>.u{text-transform:uppercase}html{scroll-behavior:smooth}</style>"
          "<button disabled>Off</button><button onclick=\"document.title='OK-CLICKED'\">On</button>"
          "<button class=u onclick=\"document.title='DD'\">Dropdown</button>"
          "<label class=sw><input type=checkbox style='position:absolute;opacity:0;width:1px;height:1px' onchange=\"document.title='TOGGLED'\"><span style='display:inline-block;width:40px;height:20px;background:#ccc'></span> Dark mode</label>"
          "<div style='height:3000px'></div><button onclick=\"document.title='TARGET'\">Far</button>")
    out = run(B, "start", "a/index.html", "--session", "s/a.json", cwd=d).stdout
    refs = {m.group(2): m.group(1) for m in re.finditer(r"(e\d+) \S+ \"([^\"]*)\"", out)}
    assert "[destructive" not in out, "uppercase styling doesn't make a control destructive: " + out
    run(B, "step", "click", refs["Off"], "--session", "s/a.json", cwd=d)
    r = run(B, "step", "click", refs["On"], "--session", "s/a.json", cwd=d); assert "title: OK-CLICKED" in r.stdout, r.stdout
    r = run(B, "step", "click", next(v for k, v in refs.items() if k.lower() == "dropdown"), "--session", "s/a.json", cwd=d); assert "title: DD" in r.stdout, r.stdout
    cb = next(v for k, v in refs.items() if "Dark mode" in k)
    r = run(B, "step", "check", cb, "--session", "s/a.json", cwd=d); assert "title: TOGGLED" in r.stdout, r.stdout
    r = run(B, "step", "click", refs["Far"], "--session", "s/a.json", cwd=d); assert "title: TARGET" in r.stdout, r.stdout
    write(d, "w/index.html", "<!doctype html><title>W</title><script>const b=new Blob([\"try{new WebSocket('ws://'+self.location.host+'/w')}catch(e){};postMessage(typeof WebSocket)\"]);"
          "let ok='none'; try{ const w=new Worker(URL.createObjectURL(b)); ok='made'; }catch(e){ ok='blocked'; } document.title='W-'+ok;</script>")
    r = run(B, "start", "w/index.html", "--session", "s/w.json", cwd=d); assert "title: W-blocked" in r.stdout, "workers are off without --allow-writes: " + r.stdout
    r = run(B, "start", "w/index.html", "--session", "s/w2.json", "--allow-writes", cwd=d); assert "title: W-made" in r.stdout, r.stdout
    write(d, "h/index.html", "<!doctype html><title>H</title><script>try{new WebSocket('ws://'+location.host+'/hmr')}catch(e){}</script><button onclick=\"document.title='CLICKED'\">Go on</button>")
    run(B, "start", "h/index.html", "--session", "s/h.json", "--allow-writes", cwd=d)
    r = run(B, "step", "click", "e1", "--session", "s/h.json", cwd=d); assert "sent data" not in r.stdout, "an idle socket is not a write: " + r.stdout

@test("5.0 open item 7: a browser session is signed, a live target's request cap holds across sessions, and an earlier write is never replayed even if the record is forged")
def _(d):
    try: import playwright  # noqa: F401
    except ImportError: return
    import http.server as hs, threading
    seen = []
    class App(hs.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            seen.append(f"GET {self.path}"); self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(b"<!doctype html><title>L</title><script>fetch('/a');fetch('/b')</script><p>x</p>" if self.path in ("/", "/index.html") else b"ok")
        def do_POST(self): seen.append(f"POST {self.path}"); self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    app = hs.ThreadingHTTPServer(("127.0.0.1", 0), App); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
    B = S / "browse.py"; live = f"http://localhost.:{port}/"
    write(d, ".critic/scope.json", json.dumps({"version": 1, "targets": [{"origin": f"http://localhost.:{port}", "max_requests": 5, "note": "test"}]}))
    r = run(B, "start", live, "--session", "s/a.json", "--allow-live", "localhost.", cwd=d); assert "refused" not in r.stdout, r.stdout
    time.sleep(0.3); n1 = len(seen)
    r = run(B, "start", live, "--session", "s/b.json", "--allow-live", "localhost.", cwd=d)
    time.sleep(0.3); assert len(seen) <= 5 and "request cap" in r.stdout, (seen, r.stdout)
    assert not (d / ".critic/private/browse.key").read_text() in json.dumps(json.loads((d / "s/a.json").read_text())), "the key never goes into a session"
    s_ = json.loads((d / "s/a.json").read_text()); s_["requests_total"] = 0; (d / "s/a.json").write_text(json.dumps(s_))
    r = run(B, "step", "snapshot", "--session", "s/a.json", cwd=d); assert r.returncode == 2 and "signature" in r.stdout, r.stdout
    seen.clear()
    write(d, "w/index.html", "<!doctype html><title>W</title><button onclick=\"fetch('/save',{method:'POST',body:'x'}).catch(()=>{})\">Save draft</button>")
    run(B, "start", "w/index.html", "--session", "s/w.json", "--allow-writes", cwd=d); run(B, "step", "click", "e1", "--session", "s/w.json", cwd=d)
    forge = ("import json, os, sys; sys.path.insert(0, sys.argv[1]); os.environ['CRITIC_ROOT'] = sys.argv[2]; import browse; p = sys.argv[3]; "
             "s = json.load(open(p)); s.pop('wrote_at', None); open(p, 'w').write(json.dumps(browse.sign(s)))")
    subprocess.run([sys.executable, "-c", forge, str(S), str(d), str(d / "s/w.json")], cwd=d, check=True, env=dict(os.environ, CRITIC_ROOT=str(d)))
    r = run(B, "step", "snapshot", "--session", "s/w.json", cwd=d)
    assert r.returncode == 2 and "send it again" in r.stdout and "not sent again" in r.stdout, "even a validly signed record without wrote_at never re-sends: " + r.stdout
    gs = subprocess.run([sys.executable, str(H / "guard_state.py")], input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(d / ".critic/private/browse.key")}, "cwd": str(d)}), capture_output=True, text=True)
    assert "deny" in gs.stdout, "agents can't write the key"
    run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    rg = run(H / "read_guard.py", cwd=d, stdin=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(d / ".critic/private/browse.key")}, "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(d)}))
    assert "deny" in rg.stdout, "a reviewer can't read the key: " + rg.stdout
    app.shutdown()

@test("5.0 decision 28: every planted defect has its places, and score.py credits a finding only when it points at one (an old loose baseline is compared loosely)")
def _(d):
    for f in ("answer_key.json", "answer_key2.json", "answer_key3.json", "answer_key4.json"):
        key = json.loads((HERE.parent / "eval" / f).read_text()); fx = HERE.parent / "eval" / ("fixture" if f == "answer_key.json" else "fixture" + f[10])
        for name, k in key.items():
            assert k.get("at"), (f, name)
            for file_, a, b in k["at"]:
                n = len((fx / file_).read_text().splitlines()); assert 1 <= a <= b <= n, (f, name, file_, a, b, n)
    SC = HERE.parent / "eval" / "score.py"; (d / "r").mkdir()
    (d / "r/last-review.md").write_text("# review\n## VERDICT\n**CONCERNS**\n")
    (d / "r/findings.jsonl").write_text(json.dumps({"id": "F-1", "file": "app.js", "line": 120, "category": "ux", "impact": "Low", "title": "Pressing Escape does not clear the filter"}) + "\n")
    out = subprocess.run([sys.executable, str(SC), str(d / "r/last-review.md"), "--suite", "1", "--baseline", str(d / "none.json"), "--labels", str(d / "l.json")], capture_output=True, text=True).stdout
    assert "Recall: 0%" in out and "file and pattern only: 1 of 16" in out, out
    (d / "old.json").write_text(json.dumps({"suite1": {"recall": 1.0, "precision": 0.96}}))
    out = subprocess.run([sys.executable, str(SC), str(d / "r/last-review.md"), "--suite", "1", "--baseline", str(d / "old.json"), "--labels", str(d / "l.json")], capture_output=True, text=True).stdout
    assert "as this suite's baseline was scored" in out and "pointing at the planted lines: 0 of 16" in out, out

@test("5.0 decision 31: a brief names only the references the payload needs (no design rubric without interface files, only the picked lens sections)")
def _(d):
    def brief(files, extra=None):
        write(d, ".critic/change-map.json", json.dumps({"files": files, "tier": "lite"})); (d / ".critic/plan.json").unlink(missing_ok=True)
        if extra is not None: write(d, ".critic/plan.json", json.dumps({"lenses": extra}))
        run(S / "critic_brief.py", cwd=d); return (d / ".critic/briefs/brief-A.md").read_text()
    for f in ("src/a.py", ".github/workflows/ci.yml", "web/index.html"): write(d, f, "x\n")
    b = brief(["src/a.py"]); assert "skip Rubric 2" in b and "ai-tells" not in b and "lenses.md" not in b and "output-contract" not in b, b
    b = brief(["src/a.py", ".github/workflows/ci.yml"]); assert '"CI and supply chain"' in b and '"Operations"' not in b, b
    b = brief(["web/index.html"]); assert "ai-tells.md" in b and "both rubrics" in b, b
    b = brief(["src/a.py"], ["release and rollback"]); assert '"Release and rollback"' in b, "the job plan's lenses win when there is one"
    refs = HERE / "skills/review/references"
    for sec in re.findall(r'"([^"]+)"', brief(["src/a.py"], ["tests of the tests", "CI and supply chain", "agent and MCP configuration", "release and rollback", "requirements and intent", "operations"])):
        assert f"## {sec}" in (refs / "lenses.md").read_text(), sec
    rv = (HERE / "agents/curmudgeon-reviewer.md").read_text(); assert "references your brief names" in rv and "output-contract" not in rv

@test("5.0 decision 29: a running app is recorded once and then replayed offline, so a click (even a GET that deletes) never reaches the real server")
def _(d):
    try: import playwright  # noqa: F401
    except ImportError: return
    import http.server as hs, threading
    seen = []
    PAGE = (b"<!doctype html><title>App</title><a href='/about'>About</a>"
            b"<button id=wipe onclick=\"fetch('/wipe?all=1').then(()=>document.title='WIPED')\">Clear all</button>"
            b"<button id=save onclick=\"fetch('/api/save',{method:'POST',body:'x'}).then(r=>r.json()).then(()=>document.title='SAVED')\">Save</button>")
    class App(hs.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _ok(self, body, t="text/html"): self.send_response(200); self.send_header("Content-Type", t); self.end_headers(); self.wfile.write(body)
        def do_GET(self): seen.append(f"GET {self.path}"); self._ok(PAGE if self.path in ("/", "/index.html") else b"<!doctype html><title>About</title><p>About us</p>" if self.path == "/about" else b"done")
        def do_POST(self): seen.append(f"POST {self.path}"); self._ok(b"{}", "application/json")
    app = hs.ThreadingHTTPServer(("127.0.0.1", 0), App); threading.Thread(target=app.serve_forever, daemon=True).start()
    B = S / "browse.py"; url = f"http://127.0.0.1:{app.server_address[1]}/"
    r = run(B, "start", url, "--session", "s/a.json", cwd=d); assert "mode: simulation" in r.stdout, r.stdout
    assert seen == ["GET /"], seen
    out = run(B, "step", "click", "e2", "--session", "s/a.json", cwd=d).stdout
    assert "/wipe" in out and "not in the recording" in out and "GET /wipe?all=1" not in seen, (out, seen)
    out = run(B, "step", "click", "e3", "--session", "s/a.json", cwd=d).stdout
    assert "title: SAVED" in out and "answered by the simulation" in out and not any(x.startswith("POST") for x in seen), (out, seen)
    r = run(B, "record", "/wipe-all", "--session", "s/a.json", cwd=d); assert r.returncode == 2 and "looks like an action" in r.stdout and "GET /wipe-all" not in seen, r.stdout
    r = run(B, "record", "/about", "--session", "s/a.json", cwd=d); assert r.returncode == 0 and seen.count("GET /about") == 1, (r.stdout, seen)
    n = len(seen); out = run(B, "step", "goto", "/about", "--session", "s/a.json", cwd=d).stdout
    assert "About us" in out and len(seen) == n, ("a recorded page replays offline", out, seen)
    har = next((d / "s").glob("a-recording-1.har")); har.write_text(har.read_text().replace("App", "Hacked"))
    r = run(B, "step", "snapshot", "--session", "s/a.json", cwd=d); assert r.returncode == 2 and "recording" in r.stdout and "changed" in r.stdout, r.stdout
    app.shutdown()

@test("5.0 smoke-run finding: findings are assigned to plants by maximum matching, so a loose pattern on one plant can't steal the only finding another plant has")
def _(d):
    SC = HERE.parent / "eval" / "score.py"; (d / "r").mkdir()
    (d / "r/last-review.md").write_text("# review\n## VERDICT\n**CONCERNS**\n")
    rows = [{"id": "F-1", "file": "app.js", "line": 12, "category": "ux", "impact": "High", "title": "Delete has no confirm or undo, and with no notes there is no empty state"},
            {"id": "F-2", "file": "app.js", "line": 5, "category": "ux", "impact": "Medium", "title": "No empty state when there are no notes"}]
    (d / "r/findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = subprocess.run([sys.executable, str(SC), str(d / "r/last-review.md"), "--suite", "1", "--baseline", str(d / "none.json"), "--labels", str(d / "l.json")], capture_output=True, text=True).stdout
    assert "missed: D12" not in out and "missed: D13" not in out, "D12 can take F-2, so F-1 is left for D13: " + out
    rows = [{"id": "F-1", "file": "app.js", "line": 11, "category": "security", "impact": "High", "title": "Titles injected unescaped into innerHTML (XSS), re-rendered quadratically"},
            {"id": "F-2", "file": "app.js", "line": 12, "category": "style", "impact": "Low", "title": "Inline onclick built without escaping"},
            {"id": "F-3", "file": "app.js", "line": 8, "category": "perf", "impact": "Medium", "title": "Quadratic: the whole list is sorted inside the per-note loop"}]
    (d / "r/findings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = subprocess.run([sys.executable, str(SC), str(d / "r/last-review.md"), "--suite", "1", "--baseline", str(d / "none.json"), "--labels", str(d / "l.json")], capture_output=True, text=True).stdout
    assert "impact miss: D01" not in out and "missed: D07" not in out, "the XSS plant is credited to the High finding, and D07 still gets one: " + out
    sys.path.insert(0, str(HERE.parent / "eval")); import importlib; dm = importlib.import_module("deathmatch")
    plants = {"A": {"file": "", "any": ["x"]}, "B": {"file": "", "any": ["only-b"]}}
    assert len(dm.match_plants(plants, [{"loc": "", "claim": "x only-b"}, {"loc": "", "claim": "x"}])) == 2

@test("5.0 self-review (eval): free-text citations count, evidence doesn't move a finding, impact preference is graded, the funnel matches one-to-one, planter keys have places, and missing tools fail cleanly")
def _(d):
    sys.path.insert(0, str(HERE.parent / "eval")); import importlib; km = importlib.import_module("keymatch")
    k = {"file": "store.js", "at": [["store.js", 2, 2]], "any": ["x"]}
    for loc in ["`store.js` line 2", "store.js (line 2)", "store.js lines 2-3", "store.js#L2", "store.js:L2", "in store.js, line 2"]:
        assert km.points_at(k, loc), loc
    assert not km.points_at(k, "store.js line 40") and not km.points_at(k, "app.js line 2")
    import random
    rnd = random.Random(7)
    def brute(el, ser):
        import itertools
        plants = list(el); best = (-1, -1)
        def go(i, used, n, sv):
            nonlocal best
            if i == len(plants): best = max(best, (n, sv)); return
            go(i + 1, used, n, sv)
            for f in el[plants[i]]:
                if f not in used: go(i + 1, used | {f}, n + 1, sv + (1 if f in ser.get(plants[i], []) else 0))
        go(0, frozenset(), 0, 0); return best
    for _ in range(400):
        P = [f"p{i}" for i in range(rnd.randint(1, 5))]; F = list(range(rnd.randint(1, 5)))
        el = {p_: rnd.sample(F, rnd.randint(0, len(F))) for p_ in P}
        ser = {p_: [f for f in el[p_] if rnd.random() < 0.5] for p_ in P if rnd.random() < 0.6}
        got = km.serious_first(el, ser); n, sv = brute(el, ser)
        assert len(got) == n and sum(1 for p_, f in got.items() if f in ser.get(p_, [])) == sv, (el, ser, got, n, sv)
    sc = (HERE.parent / "eval" / "score.py").read_text()
    assert "r.get('evidence'" not in sc.split("def locs_of")[1].split("def ")[0], "a finding's location is its file, line and quote, never its evidence"
    c = d / ".critic"; c.mkdir()
    one = {"file": "app.js", "line": 11, "category": "x", "impact": "High", "title": "XSS: titles into innerHTML unescaped, and search responses race out of order", "quote": "", "evidence": "", "failing_case": ""}
    (c / "findings.jsonl").write_text(json.dumps(one) + "\n"); (c / "tally.json").write_text(json.dumps({"kept": [], "retracted": [], "dropped": [], "rejected": [], "suppressed": []}))
    out = subprocess.run([sys.executable, str(HERE.parent / "eval" / "score.py"), "--funnel", str(d), "--suite", "1"], capture_output=True, text=True).stdout
    assert "1 of 16 planted defects reached" in out, "one finding reaches one plant, as score.py counts it: " + out
    pl = (HERE.parent / "eval" / "planter.py").read_text(); assert '"at": [[' in pl, "planter keys carry their place"
    dm = (HERE.parent / "eval" / "deathmatch.py").read_text(); assert "FileNotFoundError" in dm
    ln = (HERE.parent / "eval" / "lens.py").read_text(); assert "TimeoutExpired" in ln

@test("5.0 self-review (pipeline): a link a reviewer made inside its own scratch notes doesn't stop the scripts, but a link at the scratch folder itself, or anywhere else in .critic, still does")
def _(d):
    from critic_findings import state_links
    run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    n = d / ".critic/scratch/agent1/notes/p1"; n.mkdir(parents=True); (n / "f.txt").write_text("x"); os.symlink(n / "f.txt", n / "link")
    h = d / ".critic/history/run-1/scratch/agent0/notes"; h.mkdir(parents=True); os.symlink(h, h / "loop")
    assert state_links(d) == [], state_links(d)
    os.symlink(d / ".critic/scratch/agent1", d / ".critic/scratch/agent2")
    assert any("agent2" in x for x in state_links(d)), "a scratch folder that is itself a link is refused"
    (d / ".critic/scratch/agent2").unlink(); os.symlink(d / "elsewhere", d / ".critic/reviews-link")
    assert any("reviews-link" in x for x in state_links(d))

@test("5.0 self-review (browser): errored steps aren't kept, dialogs are shown and accepted in the simulation, secrets aren't typed or echoed, a form post gets a page, and agents can't write scope.json")
def _(d):
    gs = subprocess.run([sys.executable, str(H / "guard_state.py")], input=json.dumps({"tool_name": "Write", "agent_type": "curmudgeon:curmudgeon-reviewer", "tool_input": {"file_path": str(d / ".critic/scope.json")}, "cwd": str(d)}), capture_output=True, text=True)
    assert "deny" in gs.stdout, "an agent can't write the owner's live-site list"
    gs = subprocess.run([sys.executable, str(H / "guard_state.py")], input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(d / ".critic/scope.json")}, "cwd": str(d)}), capture_output=True, text=True)
    assert "deny" not in gs.stdout, "the lead, acting for the owner, still can"
    try: import playwright  # noqa: F401
    except ImportError: return
    B = S / "browse.py"
    write(d, "a/index.html", "<!doctype html><title>A</title><p id=o>start</p>"
          "<button onclick=\"if (confirm('Delete all notes?')) { fetch('/api/wipe',{method:'POST',body:JSON.stringify({id:2})}); document.getElementById('o').textContent='wiped'; }\">Delete all</button>"
          "<input type=password id=pw aria-label=Password><input id=nm aria-label=Name>"
          "<form method=post action='/submit'><button>Send form</button></form>")
    out = run(B, "start", "a/index.html", "--session", "s/a.json", cwd=d).stdout
    r = run(B, "step", "select", "e2", "x", "--session", "s/a.json", cwd=d); assert r.returncode == 2
    assert json.loads((d / "s/a.json").read_text())["steps"] == [], "a step that errors is not kept"
    out = run(B, "step", "click", "e1", "--session", "s/a.json", cwd=d).stdout
    assert "Delete all notes?" in out and "wiped" in out and '"id":2' in out, "the confirm is shown and accepted, and the body is listed: " + out
    r = run(B, "step", "type", "e2", "hunter2", "--session", "s/a.json", cwd=d); assert r.returncode == 2 and "password" in r.stdout.lower(), r.stdout
    out = run(B, "step", "type", "e3", "bob", "--session", "s/a.json", cwd=d).stdout; assert "hunter2" not in out
    out = run(B, "step", "click", "e4", "--session", "s/a.json", cwd=d).stdout
    assert "answered by the simulation" in out and "Submitted" in out and "left its origin" not in out, out
    r = run(B, "start", "http://127.0.0.1:9/", "--session", "s/dead.json", cwd=d); assert r.returncode == 2 and not (d / "s/dead.json").exists(), r.stdout
    import safe_web, browse as bw
    for w in ("Clear all", "Reset database", "Discard changes", "Revoke key", "Log out", "Terminate session"): assert safe_web.looks_destructive(w, bw.DESTRUCTIVE), w

@test("5.0 self-review (scanners run): a reviewer may read its brief by path (a brief holds no findings), and still not another review")
def _(d):
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d); write(d, ".critic/briefs/brief-A.md", "brief"); write(d, ".critic/reviews/review-B.json", "[]")
    ask = lambda f: run(H / "read_guard.py", cwd=d, stdin=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(d / f)}, "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(d)})).stdout
    assert "deny" not in ask(".critic/briefs/brief-A.md") and "deny" in ask(".critic/reviews/review-B.json")

@test("5.0 self-review (evidence rules): no dismissal, ruling or refutation hides a finding of higher impact, a refuted finding reopens, and an unverified outside-only finding isn't counted")
def _(d):
    L = S / "critic_ledger.py"; write(d, "src/app.js", APP); run(L, "start", "full", cwd=d)
    low = finding(impact="Low", category="style", line=2, title="odd template string")
    crit = finding(impact="Critical", category="xss", line=2, title="title rendered as HTML")
    from critic_findings import fingerprint
    low["id"] = fingerprint(low); crit["id"] = fingerprint(crit)
    write(d, "f1.jsonl", json.dumps(low) + "\n"); run(L, "import", "f1.jsonl", cwd=d)
    run(L, "dismiss", low["id"], "preference", "fine as is", cwd=d)
    write(d, "f2.jsonl", json.dumps(crit) + "\n"); run(L, "import", "f2.jsonl", cwd=d)
    r = run(L, "check", cwd=d); assert r.returncode == 1 and crit["id"] in r.stdout, "a Critical on a dismissed Low's line is open: " + r.stdout
    led = json.loads((d / ".critic/ledger.json").read_text()); led["false_positives"] = [{"id": low["id"], "why": "fine"}]; (d / ".critic/ledger.json").write_text(json.dumps(led))
    sys.path.insert(0, str(S)); import importlib, critic_merge as cm
    assert cm.suppressed_by_ledger(dict(crit), led) is None, "a ruling on a Low never hides a Critical on the same code"
    assert cm.suppressed_by_ledger(dict(low, category="other-style"), led), "the same Low under another category is still hidden"
    led2 = json.loads((d / ".critic/ledger.json").read_text()); led2["findings"][crit["id"]]["status"] = "refuted"; (d / ".critic/ledger.json").write_text(json.dumps(led2))
    run(L, "import", "f2.jsonl", cwd=d)
    r = run(L, "check", cwd=d); assert r.returncode == 1, "a refuted finding raised again is open again: " + r.stdout
    src = (S / "critic_merge.py").read_text(); assert '"wontfix", "refuted by verification' not in src, "a verifier never writes the owner's wontfix"
    assert '"refuted", "refuted by verification' in src
    e = d / "outside"; e.mkdir(); write(e, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=e)
    for x in "ABC": write(e, f".critic/reviews/review-{x}.json", "[]")
    write(e, "o.json", json.dumps([dict(finding(impact="High", title="Invented by the outside AI", category="perf"), source="outside", outside_id="N1")]))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{x}.json" for x in "ABC"], "--outside", "o.json", cwd=e)
    oid = next(f["id"] for f in json.loads((e / ".critic/tally.json").read_text())["contested"] if f.get("outside_only"))
    run(S / "critic_merge.py", "apply", str(write(e, "v.json", json.dumps([{"id": oid, "verdict": "unclear", "note": "could not run it"}]))), cwd=e)
    final = [json.loads(l) for l in (e / ".critic/findings.jsonl").read_text().splitlines() if l.strip()]
    assert not any(f["title"] == "Invented by the outside AI" for f in final), "an outside-only finding the verifier couldn't confirm isn't counted"

@test("5.0 self-review (pipeline robustness): a null quote doesn't crash the tally, restore never writes outside the project, short quotes far apart aren't one finding, and small rules match their words")
def _(d):
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d); write(d, "src/app.js", APP)
    for L_ in "ABC": write(d, f".critic/reviews/review-{L_}.json", json.dumps([finding(impact="Low", category="style", line=1, quote=None, title="naming", file="README.md")]))
    r = run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{x}.json" for x in "ABC"], cwd=d); assert "Traceback" not in r.stderr, r.stderr[-600:]
    led = json.loads((d / ".critic/ledger.json").read_text()); led["restore"] = [{"at": "x", "dir": ".critic/restore/x", "files": ["../../escaped.txt"], "ids": []}]
    (d / ".critic/restore/x").mkdir(parents=True); (d / ".critic/ledger.json").write_text(json.dumps(led))
    r = run(S / "critic_ledger.py", "restore", "apply", cwd=d); assert r.returncode != 0 and not (d.parent.parent / "escaped.txt").exists(), r.stdout + r.stderr
    from critic_findings import similar, SECURITY, to_sarif
    a = dict(finding(), line=10, quote="x = 1;", category="state", title="counter reset on every render"); b = dict(finding(), line=80, quote="x = 1;", category="state", title="stale value after save")
    assert not similar(a, b), "a short quote at distant lines is two findings"
    long_ = "list.innerHTML = `<li>${n.title}</li>`;"; assert similar(dict(a, quote=long_), dict(b, quote=long_)), "a long identical quote is the same code, wherever cited"
    assert not SECURITY.search("Unclosed resource handle") and SECURITY.search("stored XSS in title")
    assert to_sarif([])["runs"][0]["tool"]["driver"]["version"] == json.loads((HERE / ".claude-plugin/plugin.json").read_text())["version"]
    assert "redacted in restore copies" not in (S / "critic_ledger.py").read_text().split('"""')[1]
    assert "within 15 lines" in (S / "critic_findings.py").read_text()

@test("5.0 self-review (change map): renames and odd names, a project in a subfolder, folders keep every text file, qualified callers, bounded reads, sensitivity from the change, and an honest intent")
def _(d):
    def git(*a, cwd=d): subprocess.run(["git", *a], cwd=cwd, capture_output=True, check=True)
    def commit(cwd=d): git("add", "-A", cwd=cwd); git("-c", "user.email=a@b.invalid", "-c", "user.name=a", "commit", "-qm", "base: earlier work", cwd=cwd)
    git("init", "-q")
    write(d, "lib.py", "def compute_total(xs):\n    return sum(xs)\n"); write(d, "use.py", "import lib\nprint(lib.compute_total([1]))\n")
    write(d, "rename_me.py", "x = 1\n"); write(d, "notes.py", "# mentions token and role and schema\nx = 1\n"); commit()
    git("mv", "rename_me.py", "renamed.py"); write(d, "café.py", "y = 2\n"); write(d, "old name.py", "z = 3\n")
    write(d, "lib.py", "def compute_total(xs):\n    return sum(xs) + 0\n"); write(d, "notes.py", "# mentions token and role and schema\nx = 2\n")
    run(S / "critic_map.py", cwd=d); cm = json.loads((d / ".critic/change-map.json").read_text())
    assert {"renamed.py", "café.py", "old name.py", "lib.py"} <= set(cm["files"]) and not any("=>" in f or "\\\\" in f for f in cm["files"]), cm["files"]
    assert "notes.py" in cm["files"] and not cm["sensitive"].get("notes.py"), "sensitivity comes from the changed lines, not every word in the file"
    assert any("compute_total" in k for k in cm["radius"]), "a call written lib.compute_total() is a caller: " + str(cm["radius"])
    assert cm["intent"] == "", "an uncommitted change has no stated intent; the last commit's message is not it"
    big = d / "dump.bin"; big.write_bytes(b"\0" * 1000 + b"x" * (5 * 1024 * 1024))
    rr = run(S / "critic_map.py", cwd=d); assert rr.returncode == 0 and "dump.bin" not in json.loads((d / ".critic/change-map.json").read_text())["files"], "a binary file is not a reviewable change, and it is never read whole"
    write(d, "sub/.github/workflows/ci.yml", "on: push\n"); write(d, "sub/run.sh", "echo hi\n"); write(d, "sub/a.py", "x = 1\n")
    run(S / "critic_map.py", "--files", "sub", cwd=d); fs = json.loads((d / ".critic/change-map.json").read_text())["files"]
    assert {"sub/.github/workflows/ci.yml", "sub/run.sh", "sub/a.py"} <= set(fs), fs
    r = d / "repo"; (r / "web/src").mkdir(parents=True); (r / "api").mkdir(); git("init", "-q", cwd=r)
    write(r, "web/src/app.js", "let a = 1;\n"); write(r, "api/x.py", "x = 1\n"); commit(cwd=r)
    write(r, "web/src/app.js", "let a = 2;\n"); write(r, "api/x.py", "x = 2\n"); write(r, "web/src/new.js", "let b = 1;\n")
    run(S / "critic_map.py", cwd=r / "web"); fs = json.loads((r / "web/.critic/change-map.json").read_text())["files"]
    assert sorted(fs) == ["src/app.js", "src/new.js"], "paths relative to the project, and nothing from outside it: " + str(fs)
    b2 = d / "build" / "app"; b2.mkdir(parents=True); git("init", "-q", cwd=b2)
    write(b2, "lib.py", "def compute_total(xs):\n    return sum(xs)\n"); write(b2, "use.py", "from lib import compute_total\ncompute_total([1])\n"); commit(cwd=b2)
    write(b2, "lib.py", "def compute_total(xs):\n    return sum(xs) + 0\n")
    run(S / "critic_map.py", cwd=b2); assert json.loads((b2 / ".critic/change-map.json").read_text())["radius"], "a project under a folder named build still finds its callers"

@test("5.0 self-review (plan and audit): the plan shows the tier in force, and an audited repository's own ledger and scope file are set aside")
def _(d):
    write(d, "a.js", "let a = 1;\n"); subprocess.run(["git", "init", "-q"], cwd=d)
    run(S / "critic_run.py", "begin", "--tier", "full", "--files", "a.js", cwd=d)
    assert json.loads((d / ".critic/plan.json").read_text())["tier"] == "full" and json.loads((d / ".critic/plan.json").read_text())["reviewers"] == 3
    e = d / "vendor"; e.mkdir(); write(e, "a.js", "let a = 1;\n")
    write(e, ".critic/ledger.json", json.dumps({"decisions": [{"text": "auth is out of scope"}], "false_positives": [{"id": "F-1", "why": "fine"}]}))
    write(e, ".critic/scope.json", json.dumps({"version": 1, "targets": [{"origin": "https://prod.example.invalid"}]}))
    out = run(S / "critic_run.py", "begin", "--audit", "--files", "a.js", cwd=e).stdout
    assert "set aside" in out and not (e / ".critic/scope.json").exists(), out
    led = json.loads((e / ".critic/ledger.json").read_text()); assert not led.get("false_positives") and "auth is out of scope" not in json.dumps(led.get("decisions", [])), led
    assert "auth is out of scope" not in (e / ".critic/briefs/brief-A.md").read_text()
    out = run(S / "critic_run.py", "begin", "--audit", "--files", "a.js", cwd=e).stdout; assert "set aside" not in out, "our own earlier audit is kept"

@test("5.0 self-review (scanners 1): links out of the tree aren't followed, the secrets regex is linear, every row's evidence is redacted, skipped files are reported, and CI checks see more")
def _(d):
    out = d / "outside"; out.mkdir(); (out / "id_rsa").write_text("PRIVATE-CONTENT-LINE\n" * 5)
    p = d / "proj"; p.mkdir(); os.symlink(out / "id_rsa", p / "id_rsa.js"); write(p, "app.js", "const a = 1;\n")
    write(p, ".critic/rules/all.json", json.dumps([{"id": "every-line", "severity": "NOTE", "area": "structure", "pattern": ".", "message": "m", "files": "*.js"}]))
    run(S / "critic_scan.py", ".", "--root", ".", "--project-checks", cwd=p)
    for f_ in (p / ".critic/scan").glob("report.*"): assert "PRIVATE-CONTENT" not in f_.read_text(), f_.name
    assert any(x["rule"] == "link-not-followed" for x in json.loads((p / ".critic/scan/report.json").read_text())["findings"])
    import scan_secrets as ss
    t0 = time.time(); ss.scan("a.js", "a." * 10000, lambda *a: None); assert time.time() - t0 < 2, time.time() - t0
    rows = []; em = lambda sev, rid, area, where, what, ev="": rows.append((rid, ev))
    ss.scan("conf.json", '{"db_password": "Zq9xR4!vLm2#Tp8@wK"}', em); assert any(r == "secret-generic" for r, _ in rows), rows
    rows.clear(); ss.scan(".env", "DB_PASSWORD=Zq9xR4vLm2Tp8wKb7Yh3\n", em); assert any(r == "secret-generic" for r, _ in rows), rows
    rows.clear(); ss.scan("a.js", '{password: "changeme123456", token: "Zq9xR4vLm2Tp8wKb7Yh3Jd"}', em); assert any(r == "secret-generic" for r, _ in rows), "a placeholder first doesn't hide a real key: " + str(rows)
    rows.clear(); ss.scan("a.js", 'const t = {token: "testZq9xR4vLm2Tp8wKb7Yh"};', em); assert any(r == "secret-generic" for r, _ in rows), "a real value starting with test is still a value"
    rows.clear(); ss.scan("docker-compose.yml", "url: postgres://user:${DB_PASSWORD}@db/app\nurl2: postgres://user:<password>@db/app\n", em); assert not rows, rows
    rows.clear(); ss.scan("docker-compose.yml", "url: postgres://postgres:postgres@localhost/app\n", em); assert rows and rows[0][0] == "secret-db-url-password", rows
    import critic_scan as cs
    rows.clear(); line = 'x' * 39000 + ' token: "Zq9xR4vLm2Tp8wKb7Yh3Jd" '; ss.scan("a.js", line, em); assert len([r for r, _ in rows if r == "secret-generic"]) == 1, rows
    write(p, "k.js", T('const k = "@LIVE@"; console.log(k); // TODO remove\n')); run(S / "critic_scan.py", ".", "--root", ".", cwd=p)
    allr = (p / ".critic/scan/report.json").read_text() + (p / ".critic/scan/report.md").read_text(); assert T("@LIVE@") not in allr, "no report row carries the key"
    (p / "big.txt").write_bytes(b"x" * (3 * 1024 * 1024)); (p / "u16.env").write_bytes(T("API_TOKEN=@LIVE@\n").encode("utf-16"))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=p); rep = json.loads((p / ".critic/scan/report.json").read_text())["findings"]
    assert any(x["rule"] == "files-not-read" for x in rep) and any(x["rule"].startswith("secret-") and "u16.env" in x["where"] for x in rep), [x["rule"] for x in rep]
    b = d / "build" / "app"; b.mkdir(parents=True); write(b, "results.sarif", json.dumps({"runs": [{"tool": {"driver": {"name": "eslint"}}, "results": [{"ruleId": "no-x", "level": "error", "message": {"text": "bad"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": "a.js"}, "region": {"startLine": 1}}}]}]}]})); write(b, "a.js", "x\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=b); assert json.loads((b / ".critic/scan/report.json").read_text())["checks"]["ci"]["state"] != "n/a"
    C = _mod("scan_ci"); wf = lambda t: [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", t)]
    assert "ci-pwn-request" in wf("on: pull_request_target\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.merge_commit_sha }}\n")
    assert "ci-unpinned-action" in wf("on: push\npermissions: {}\njobs:\n  call:\n    uses: org/repo/.github/workflows/w.yml@main\n    secrets: inherit\n")
    t0 = time.time(); wf("on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: |\n          " + "${{ " * 12000 + "\n"); assert time.time() - t0 < 2, time.time() - t0
    up = "on: push\npermissions: read-all\njobs:\n  b:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/upload-artifact@3a1b2c3d4e5f60718293a4b5c6d7e8f901234567\n        with:\n          path: .\n"
    assert "ci-upload-checkout" not in wf(up), "a pinned SHA is never read as an old version"
    assert "ci-secret-in-run" not in wf("on: push\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: echo \"has=${{ secrets.K != '' }}\"\n")
    assert "ci-unpinned-action" in [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", "on: push\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: acme/deploy@main\n", E, "acme/deploy-tools@0123456789abcdef0123456789abcdef01234567\n")], "a longer name in the lockfile doesn't cover a shorter one"
    lock = json.dumps({"packages": {"node_modules/a": {"resolved": "http://evil.example.invalid/x.tgz"}, "node_modules/b": {"resolved": "http://evil.example.invalid/x.tgz"}}}, indent=1)
    w = [w_ for _, r, w_ in _rows(C.scan_npm_lock, "package-lock.json", lock) if r == "npm-resolved-host"]; assert len(set(w)) == 2, w

@test("5.0 self-review (scanners 2): credential names are whole words, every import is an edge, media without controls isn't interactive, migrations read sql= and text(), loggers on self count, methods aren't eval, and the mutation run stops cleanly")
def _(d):
    A = _mod("scan_agentcfg")
    mcp = lambda env: json.dumps({"mcpServers": {"git": {"command": "node", "args": ["s.js"], "env": env}}}, indent=1)
    assert not [r for _, r, _ in _rows(A.scan, ".mcp.json", mcp({"GIT_AUTHOR_EMAIL": "bot@example.com", "AUTHOR": "Ryan Smith Writer"}), E, {}) if r == "agent-literal-credential"]
    assert "agent-literal-credential" in [r for _, r, _ in _rows(A.scan, ".mcp.json", mcp({"SENDGRID_KEY": "SG.live_value_here_123"}), E, {})]
    pin = lambda args: [w for _, r, w in _rows(A.scan, ".mcp.json", json.dumps({"mcpServers": {"x": {"command": args[0], "args": args[1:]}}}, indent=1), E, {}) if r == "agent-unpinned-runner"]
    assert not pin(["pipx", "run", "pkg==1.2.3"]) and not pin(["uvx", "--python", "3.12", "pkg@1.0"]) and pin(["uvx", "--python", "3.12", "pkg"])
    G = _mod("scan_graph")
    g = G.python_graph({"pkg/a.py": "from . import b, c\n", "pkg/b.py": "x = 1\n", "pkg/c.py": "from . import a\n", "pkg/__init__.py": ""})
    assert g["pkg/a.py"] == {"pkg/b.py", "pkg/c.py"}, g
    big = {f"m{i}.js": "".join(f"export function f{i}_{k}() {{ return {k}; }}\n" for k in range(10)) for i in range(200)}
    t0 = time.time(); _rows(G.scan, d, big); assert time.time() - t0 < 3, time.time() - t0
    rows = _rows(G.scan, d, {"lib.js": "export function used() { return 1; }\n", "main.js": "import * as api from './lib.js';\napi.used();\n"})
    assert not [w for _, r, w in rows if r == "dead-function"], rows
    H = _mod("scan_html"); hr = lambda t: [r for _, r, _ in _rows(H.scan, "a.html", t)]
    assert "html-nested-interactive" not in hr('<a href="/w"><video src="x.mp4" muted loop></video></a>')
    assert "html-nested-interactive" in hr('<a href="/w"><video src="x.mp4" controls></video></a>')
    assert "html-content-model" not in hr("<p>one\n<div>two</div>\n<span>x</span>")
    M = _mod("scan_migrations"); mr = lambda t: [r for _, r, _ in _rows(M.scan, "app/migrations/0002_x.py", t)]
    dj = "from django.db import migrations\nclass Migration(migrations.Migration):\n    operations = [migrations.RunSQL(sql=%s, reverse_sql='DROP INDEX i')]\n"
    assert "mig-index-blocking" in mr(dj % '"CREATE INDEX i ON big (c)"') and "mig-index-blocking" in mr(dj % '["CREATE INDEX i ON big (c)"]')
    al = "def upgrade():\n    op.execute(sa.text('CREATE INDEX i ON big (c)'))\n\ndef downgrade():\n    ...\n"
    assert {"mig-index-blocking", "mig-irreversible"} <= set(mr(al)), mr(al)
    assert "mig-constraint-validate" in mr("def upgrade():\n    op.execute('ALTER TABLE big ADD CONSTRAINT a CHECK (x > 0) NOT VALID, ADD CONSTRAINT b CHECK (y > 0)')\n\ndef downgrade():\n    op.execute('x')\n")
    O = _mod("scan_ops")
    assert "ops-log-secret" in [r for _, r, _ in _rows(O.scan, "svc.py", "class A:\n    def login(self, password):\n        self.logger.info('login %s', password)\n", E, str(d))]
    assert not [r for _, r, _ in _rows(O.scan, "alerts.yml", "groups:\n  - name: g\n    rules:\n      - alert: Down\n        annotations:\n          runbook_url: '{{ $labels.runbook }}'\n", E, str(d)) if r.startswith("ops-runbook")]
    P = _mod("scan_python"); pr = lambda rel, t: [r for _, r, _ in _rows(P.scan, rel, t)]
    assert "py-eval" not in pr("a.py", "get_session().exec(stmt)\nclients[0].eval(s)\n") and "py-eval" in pr("a.py", "eval(s)\n")
    assert "py-assert-guard" not in pr("tests/test_a.py", "def test_a():\n    assert user.is_valid\n")
    Q = _mod("scan_reqs"); rq = _rows(Q.check, {"docs/req.md": "## REQ-1\ntext\n## REQ-2: other\n"}, {"tests/test_a.py": "# covers REQ-1\n"}, E)
    assert "req-undefined" not in [r for _, r, _ in rq], rq
    X = _mod("scan_rules_extra"); xr = lambda suf, t: [r for _, r, _ in _rows(X.scan, "a" + suf, suf, t)]
    assert "outerhtml" in xr(".js", "row.outerHTML = '<tr><td>' + comment.text + '</td></tr>';\n") and "outerhtml" not in xr(".js", "row.outerHTML = '<b>x</b>';\n")
    assert "autoplay" not in xr(".html", "<video muted autoplay loop></video>\n") and "target-blank" not in xr(".html", '<a rel="noopener" target="_blank" href="/x">x</a>\n')
    assert "hover-only" not in xr(".css", "@media (hover:hover) { .a { color: red } }\n")
    TT = _mod("scan_tests"); tr = lambda t: [r for _, r, _ in _rows(TT.scan, "tests/test_a.py", t)]
    assert "test-no-assert" in tr("def test_a():\n    cart.checkout()\n") and "test-no-assert" in tr("def test_b():\n    def helper():\n        return 1\n    helper()\n")
    MU = _mod("scan_mutation")
    view = MU.code_view(pathlib.Path("x.vue"), "<template>\n  <p>Sign in and continue</p>\n</template>\n<script>\nexport const ok = a && b;\n</script>\n<style>\n.a > .b { color: red }\n</style>\n")
    assert "and" not in view[1] and ">" not in view[7] and "&&" in view[4], view
    m = d / "mut"; m.mkdir()
    for n in ("a", "b"): write(m, f"{n}.py", "def f(x, y):\n    return x < y\n")
    write(m, "t.py", "import a, b\nfor m in (a, b):\n    assert m.f(1, 2) is True and m.f(2, 1) is False and m.f(2, 2) is False\n")
    rows, st = [], {}
    MU.run(m, ["a.py", "b.py"], lambda *a: rows.append(a), lambda k, s, n="": st.update({k: (s, n)}), given_cmd="python3 t.py", cap=1, timeout=60)
    assert any(r[1] == "mutation-cap-reached" for r in rows) and "not mutated" in st["mutation"][1], (rows, st)
    h = d / "hang"; h.mkdir(); write(h, "a.py", "a, b = 1, 2\nok = a < b\n")
    MU.run(h, ["a.py"], lambda *a: None, lambda *a: None, given_cmd="python3 a.py >/dev/null && if grep -q ' <= ' a.py; then sleep 60 & echo $! > child.pid; wait; fi", cap=5, timeout=3)
    pid = int((h / "child.pid").read_text())
    try: alive = "\tZ" not in pathlib.Path(f"/proc/{pid}/status").read_text().split("State:")[1][:4]  # a killed orphan can linger as a zombie, unreaped
    except (OSError, IndexError): alive = False
    if alive: os.kill(pid, 9)
    assert not alive, "a hung mutant's child process is stopped with it"
    AV = run(S / "ast_view.py", "--depth", "3", cwd=d); assert AV.returncode == 2 and "Traceback" not in AV.stderr, AV.stderr
    write(d, "v.py", "x = 1\ny = 2\n"); AV = run(S / "ast_view.py", str(d / "v.py"), "2-1", cwd=d); assert AV.returncode == 2, AV.stdout

@test("5.0 self-review (skills and docs): the run's scripts refuse to run from a workspace, the verifier reads decisions only, approve never marks a fix twice, the intent names no author, an audit can't be fixed, --fix records full mode, and sandbox lines get SB ids")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=d)
    sc = d / ".critic/scratch/A"; sc.mkdir(parents=True)
    r = run(S / "critic_ledger.py", "start", "review", cwd=sc); assert r.returncode == 2 and "workspace" in r.stderr, (r.returncode, r.stderr)
    assert json.loads((d / ".critic/ledger.json").read_text())["run"] == 1, "a reviewer's start never reset the real run"
    assert run(S / "critic_merge.py", "tally", "x.json", cwd=sc).returncode == 2
    run(S / "critic_ledger.py", "decision", "prices are rounded on purpose", "owner", cwd=d)
    run(S / "critic_ledger.py", "add", "F-1", "Medium", "src/app.js:1", "a thing", cwd=d); run(S / "critic_ledger.py", "dismiss", "F-1", "intended", "owner said so", cwd=d)
    dec = (d / ".critic/decisions.md").read_text(); assert "rounded on purpose" in dec and "owner said so" not in dec and "memories" not in dec.lower(), dec
    ask = lambda path: "deny" in run(H / "read_guard.py", cwd=d, stdin=json.dumps({"tool_name": "Read", "tool_input": {"file_path": path}, "cwd": str(d), "agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v1"})).stdout
    assert ask(".critic/ledger.md") and not ask(".critic/decisions.md")
    run(S / "critic_ledger.py", "add", "F-2", "High", "src/app.js:2", "b thing", cwd=d)
    for c in ("targeted", "no-new-defect", "behaviour-unchanged"): run(S / "critic_ledger.py", "claim", "F-2", c, "test_x", cwd=d)
    run(S / "critic_ledger.py", "fixed", "F-2", "test_x", cwd=d); run(S / "critic_ledger.py", "fixed", "F-2", "approve", cwd=d)
    assert sum("fixed" in h for h in json.loads((d / ".critic/ledger.json").read_text())["findings"]["F-2"]["history"]) == 1
    g = d / "g"; g.mkdir(); write(g, "a.py", "x = 1\n")
    for c in (["init", "-q"], ["add", "-A"], ["-c", "user.email=e@example.invalid", "-c", "user.name=e", "commit", "-qm", "Fix the parser\n\nCo-Authored-By: Some Person <person@example.invalid>\nSigned-off-by: Some Person <person@example.invalid>"]):
        subprocess.run(["git", *c], cwd=g, capture_output=True)
    run(S / "critic_map.py", "--files", "a.py", cwd=g); it = json.loads((g / ".critic/change-map.json").read_text())["intent"]
    assert "Fix the parser" in it and "Some Person" not in it and "example.invalid" not in it, it
    a = d / "aud"; a.mkdir(); write(a, "a.js", "x\n"); run(S / "critic_run.py", "begin", "--audit", "--files", "a.js", cwd=a)
    run(S / "critic_ledger.py", "add", "F-3", "High", "a.js:1", "c", cwd=a)
    assert run(S / "critic_ledger.py", "fixed", "F-3", "x", "--untested", cwd=a).returncode != 0, "an audit refuses fixes"
    fx = d / "fx"; fx.mkdir(); write(fx, "a.js", "x\n"); run(S / "critic_run.py", "begin", "--fix", "--files", "a.js", cwd=fx)
    assert json.loads((fx / ".critic/ledger.json").read_text())["mode"] == "full"
    sb = d / "sb"; sb.mkdir(); write(sb, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=sb)
    write(sb, "a.json", json.dumps({"findings": [finding()], "sandbox": [{"scenario": "first run, empty", "happens": "shows an empty list", "result": "holds", "how": "driven"}]}))
    write(sb, "b.json", json.dumps({"findings": [finding()]}))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=sb); write(sb, "v.json", "[]"); r = run(S / "critic_merge.py", "apply", "v.json", cwd=sb); assert r.returncode == 0, r.stderr
    cm = (sb / ".critic/counts.md").read_text(); assert "| SB1 | a | first run, empty |" in cm, cm[-800:]

@test("5.0 A/B scoring: the stamp names the build that ran (--plugin), a clean-twin baseline from several runs takes the median, and --meta-cost reads each run's whole-session cost")
def _(d):
    EV = HERE.parent / "eval"; fake = d / "arm" / "plugin"; write(fake, ".claude-plugin/plugin.json", json.dumps({"name": "curmudgeon", "version": "9.9.9-test"}))
    revs = []
    for i, n in enumerate((0, 2, 4)):
        r = d / f"run{i}"; write(r, "meta.json", json.dumps({"cost_usd": 1.5 + i}))
        body = "**CONCERNS** · Counts: 0 Critical, 0 High, %d Medium, 0 Low\n\n" % n + "".join(f"- **C{k}** `app.js:{k + 1}` | **IMPACT: Medium** | finding {i}-{k}\n" for k in range(n))
        write(r, ".critic/teardown.md", body); revs.append(str(r / ".critic/teardown.md"))
    out = subprocess.run([sys.executable, str(EV / "score.py"), *revs, "--clean", "1", "--set-baseline", "--baseline", str(d / "bl.json"), "--labels", str(d / "lab.json"), "--plugin", str(fake), "--meta-cost"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    b = json.loads((d / "bl.json").read_text())["clean1"]
    assert b["stamp"]["version"] == "9.9.9-test" and b["fp_clean"] == 2 and b["false_block"] == 0 and b["cost_unit"] == "usd_millionths" and b["tokens"] == 2500000, b
    assert "Cost per run: $1.50, $2.50, $3.50" in out.stdout, out.stdout

@test("5.0 A/B finding: a quote at another line of its file is still retracted, but the tally says it is a wrong line number, and reviewers are told to number one file at a time")
def _(d):
    write(d, "app.js", "\n".join(["// x"] * 40 + ["if (user.roles.indexOf(\"admin\")) {", "  return true;", "}"]) + "\n"); run(S / "critic_ledger.py", "start", "review", cwd=d)
    bad = finding(file="app.js", line=5, quote='if (user.roles.indexOf("admin")) {', title="canVoid is inverted")
    write(d, "a.json", json.dumps([bad])); write(d, "b.json", json.dumps([bad]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert not t["kept"] and t["retracted"] and "the exact quote is at line 41" in t["retracted"][0]["why"], t["retracted"]
    write(d, "v.json", "[]"); assert run(S / "critic_merge.py", "apply", "v.json", cwd=d).returncode == 0
    cm = (d / ".critic/counts.md").read_text(); assert "Line numbers to check: 2 retracted" in cm, cm[-600:]
    for a in ("curmudgeon-reviewer.md", "curmudgeon-verifier.md"): assert "grep -n" in (HERE / "agents" / a).read_text() and "cat -n" in (HERE / "agents" / a).read_text()

@test("5.0 A/B finding: a merged finding shows every place its reviewers cited, and the scorer credits a plant at any of them")
def _(d):
    write(d, "styles.css", ".toast { animation: pop 1s infinite; }\n"); write(d, "index.html", '<div id="toast"></div>\n'); run(S / "critic_ledger.py", "start", "review", cwd=d)
    a = finding(file="styles.css", line=1, quote=".toast { animation: pop 1s infinite; }", title="Toast pulses forever with no reduced-motion option", impact="Medium", category="a11y")
    b = finding(file="index.html", line=1, quote='<div id="toast"></div>', title="Toast is never announced and pulses forever", impact="Medium", category="a11y")
    write(d, "a.json", json.dumps([a])); write(d, "b.json", json.dumps([b]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d)
    cands = json.loads((d / ".critic/dedup-candidates.json").read_text())["findings_by_file"]
    write(d, ".critic/groups.json", json.dumps({"groups": [[x["id"] for v in cands.values() for x in v]]}))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", "--groups", ".critic/groups.json", cwd=d)
    write(d, "v.json", "[]"); assert run(S / "critic_merge.py", "apply", "v.json", cwd=d).returncode == 0
    cm = (d / ".critic/counts.md").read_text(); assert "(also at " in cm, cm[:900]
    r = d / "run"; write(r, ".critic/teardown.md", "**CONCERNS** · Counts: 0 Critical, 0 High, 1 Medium, 0 Low\n")
    write(r, ".critic/findings.jsonl", json.dumps({"id": "F-1", "file": "index.html", "line": 23, "quote": '<div id="toast" class="toast"></div>', "category": "a11y", "impact": "Medium",
                                                   "title": "Toast pulses forever with an infinite animation and no reduced-motion option", "locations": ["index.html:23", "styles.css:20"]}) + "\n")
    out = subprocess.run([sys.executable, str(HERE.parent / "eval" / "score.py"), str(r / ".critic/teardown.md"), "--suite", "2", "--baseline", str(d / "none.json"), "--labels", str(d / "none.json")], capture_output=True, text=True).stdout
    assert "missed: E21" not in out, out[:600]

@test("decision 36: a decoy hit points at the decoy's place and makes its claim; a real bug that only mentions the decoy's words is not one")
def _(d):
    def score(rows):
        r = d / f"r{len(list(d.iterdir()))}"; write(r, ".critic/teardown.md", "**CONCERNS** · Counts: 0 Critical, 0 High, 1 Medium, 0 Low\n")
        write(r, ".critic/findings.jsonl", "".join(json.dumps(x) + "\n" for x in rows))
        return subprocess.run([sys.executable, str(HERE.parent / "eval" / "score.py"), str(r / ".critic/teardown.md"), "--suite", "3", "--baseline", str(d / "none.json"), "--labels", str(d / "none.json")], capture_output=True, text=True).stdout
    real = {"id": "F-1", "file": "app.js", "line": 37, "quote": "render();", "category": "a11y-focus", "impact": "Medium", "title": "After Delete the whole list is re-rendered and keyboard focus falls to the body"}
    assert "Decoys reported as defects: 0" in score([real]), "a focus bug that names the re-render is not the performance decoy"
    decoy = {"id": "F-2", "file": "app.js", "line": 40, "quote": "// shortcut: the list re-renders whole on each change", "category": "perf", "impact": "Medium", "title": "Whole list re-render on every change will not scale"}
    assert "Decoys reported as defects: 1 (1 at Medium" in score([decoy])
    elsewhere = dict(decoy, id="F-3", file="store.js", line=15, quote="localStorage.setItem(KEY, JSON.stringify(list));")
    assert "Decoys reported as defects: 0" in score([elsewhere]), "a finding that points away from the decoy's place is not a decoy hit"

@test("death match kit: every arm runs with only its own plugin, the built-in /code-review's JSON and Semgrep's output are read like any other arm's, and `file` L8-14 is a citation")
def _(d):
    EV = HERE.parent / "eval"; sys.path.insert(0, str(EV))
    import importlib, keymatch, deathmatch; importlib.reload(keymatch); importlib.reload(deathmatch)
    assert keymatch.cited_lines("`guards.js` L8-14 (`canVoid`)", "guards.js") == list(range(8, 15)) and keymatch.cited_lines("guards.js Lambda", "guards.js") == []
    js = deathmatch.json_findings('```json\n[{"file": "guards.js", "line": 11, "summary": "canVoid is inverted", "failure_scenario": "sam may void. Fix: use includes"}]\n```')
    assert js and js[0]["loc"] == "guards.js:11" and "canVoid is inverted" in js[0]["claim"] and "includes" not in js[0]["claim"], js
    assert deathmatch.json_findings("1. guards.js:11 canVoid is inverted") is None
    r = subprocess.run([sys.executable, str(EV / "semgrep_md.py")], input=json.dumps({"results": [{"path": "app.js", "start": {"line": 32}, "check_id": "x.y.insecure-innerhtml", "extra": {"message": "User data in innerHTML", "lines": "tb.innerHTML = x"}}]}), capture_output=True, text=True).stdout
    assert r.startswith("- app.js:32 [insecure-innerhtml] User data in innerHTML"), r
    assert "No issues found." in subprocess.run([sys.executable, str(EV / "semgrep_md.py")], input='{"results": []}', capture_output=True, text=True).stdout
    seen = []
    class R: stdout = '{"result": "ok", "usage": {}}'; stderr = ""; returncode = 0
    orig = deathmatch.subprocess.run
    deathmatch.subprocess.run = lambda cmd, **k: (seen.append(cmd), R())[1]
    try:
        deathmatch.PLUGINS[:] = ["curmudgeon@synced", "code-review-anthropics@anthropic-plugin-directory"]
        deathmatch.one_run({"id": "x", "prompt": "/code-review:code-review", "plugin_enable": ["code-review-anthropics@anthropic-plugin-directory"]}, d, d, None)
        deathmatch.one_run({"id": "y", "prompt": "review"}, d, d, None)
    finally: deathmatch.subprocess.run = orig
    s0 = json.loads(seen[0][seen[0].index("--settings") + 1])["enabledPlugins"]; s1 = json.loads(seen[1][seen[1].index("--settings") + 1])["enabledPlugins"]
    assert s0 == {"curmudgeon@synced": False, "code-review-anthropics@anthropic-plugin-directory": True} and not any(s1.values()), (s0, s1)

@test("death match scorer: an indented sub-bullet stays part of its finding, and a structured finding's claim includes its evidence, as a free-form one does")
def _(d):
    EV = HERE.parent / "eval"; sys.path.insert(0, str(EV))
    import importlib, deathmatch; importlib.reload(deathmatch)
    text = "1. **`guards.js:10`: the void check is inverted.**\n   - `indexOf` returns -1 when admin is absent, and -1 is truthy.\n   - A viewer can void.\n2. **`app.js:8`: dead link.**\n"
    bl = deathmatch.blocks_from(text); assert len(bl) == 2 and "-1 is truthy" in bl[0], bl
    write(d, "a/findings.jsonl", json.dumps({"file": "guards.js", "line": 10, "title": "canVoid lets every non-admin void", "evidence": "indexOf returns -1 (truthy) when admin is absent", "failing_case": "a viewer voids", "remediation": "use includes"}) + "\n")
    b = deathmatch.blocks_for(d / "a")[0]; assert "indexOf returns -1" in b["claim"] and "includes" not in b["claim"], b

@test("5.1 SC-80: the scan's FAIL rows reach the user as soon as the report exists, once per report, while the reviewers work")
def _(d):
    write(d, "a.js", T('const k = "@LIVE@";\neval(x);\n'))
    assert run(S / "critic_run.py", "begin", "--tier", "lite", "--files", "a.js", cwd=d).returncode == 0
    assert "has not written" in run(S / "critic_run.py", "early", cwd=d).stdout
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "early results" in out and "FAIL" in out and T("@LIVE@") not in out, out
    assert "early results" not in run(S / "critic_run.py", "next", cwd=d).stdout, "shown once per scan report"
    assert "early results" in run(S / "critic_run.py", "early", cwd=d).stdout, "asked for, it shows again"

@test("5.1 SC-79: Nits are listed but never counted or verified, a verifier may lower a Low to a Nit, and the scorer credits a planted bug found as a Nit only as an impact miss")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    nit = finding(impact="Nit", line=4, quote="const price = total * 1.0825;", title="Name the tax constant", category="style")
    low = finding(impact="Low", title="Title rendered as HTML")
    write(d, "a.json", json.dumps([nit, low])); write(d, "b.json", json.dumps([nit, low]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d)
    t = json.loads((d / ".critic/tally.json").read_text())
    assert [x["title"] for x in t["nits"]] == ["Name the tax constant"] and all(f["impact"] != "Nit" for f in t["kept"]), t
    assert not any("Name the tax" in json.dumps(json.loads(p.read_text())) for p in (d / ".critic/verify").glob("*.json")), "Nits are never verified"
    lid = t["kept"][0]["id"]; write(d, "v.json", json.dumps([{"id": lid, "verdict": "downgrade", "impact_after": "Nit", "note": "cosmetic"}]))
    assert run(S / "critic_merge.py", "apply", "v.json", cwd=d).returncode == 0
    assert not (d / ".critic/findings.jsonl").read_text().strip(), "the lowered Low left the counted findings"
    nj = [json.loads(l)["title"] for l in (d / ".critic/nits.jsonl").read_text().splitlines()]; assert set(nj) == {"Name the tax constant", "Title rendered as HTML"}, nj
    cm = (d / ".critic/counts.md").read_text(); assert "## Nits (2;" in cm and "Low 0" in cm, cm[:500]
    r = d / "run"; write(r, ".critic/teardown.md", "**CLEAN** · Counts: 0 Critical, 0 High, 0 Medium, 0 Low\n"); write(r, ".critic/findings.jsonl", "")
    write(r, ".critic/nits.jsonl", json.dumps({"id": "F-9", "file": "app.js", "line": 10, "quote": "list.innerHTML += `<li>${n.title}", "category": "xss", "title": "Title is put into innerHTML without escaping (XSS)"}) + "\n" + json.dumps({"id": "F-8", "file": "app.js", "line": 1, "quote": "x", "category": "style", "title": "Rename a variable"}) + "\n")
    out = subprocess.run([sys.executable, str(HERE.parent / "eval" / "score.py"), str(r / ".critic/teardown.md"), "--suite", "1", "--baseline", str(d / "none.json"), "--labels", str(d / "none.json")], capture_output=True, text=True).stdout
    assert "impact miss" in out and "unlabelled 0" in out, out[:900]

@test("5.1 SC-79 measured fix: the stricter Low never covers a data loss, a wrong result or a failure shown as success, however rare the path")
def _(d):
    r = (HERE / "skills/review/references/rubrics.md").read_text()
    assert "a missing message on a rare path" not in r, "the measured run showed reviewers reading this as permission to rate a false 'Deleted' Low"
    assert re.search(r"However rare the path, anything that loses or corrupts data, gives a wrong result, or reports a failure as success is High or worse", r)

@test("5.1 measured reverts: verifiers keep five packets each and a Medium two reviewers executed is still verified (SC-78 measured worse), and the lead-diet lab is gone (no saving)")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "full", cwd=d)
    med = finding(impact="Medium", verified="executed")
    write(d, "a.json", json.dumps([med])); write(d, "b.json", json.dumps([med]))
    run(S / "critic_merge.py", "tally", "a.json", "b.json", cwd=d)
    fid = json.loads((d / ".critic/tally.json").read_text())["kept"][0]["id"]
    assert (d / ".critic/verify" / f"{fid}.json").exists(), "every surviving Medium gets its blind verifier"
    sys.path.insert(0, str(S)); import importlib, critic_run; importlib.reload(critic_run); assert critic_run.VERIFY_BATCH == 5
    assert not (S / "critic_skeleton.py").exists()

@test("5.2 SC-74: the integrity lens finds every planted look-alike link, punycode host, http form, off-site form, unpinned script and weak CSP, with no row on decoys or the clean twin")
def _(d):
    r = run(HERE.parent / "eval" / "lens.py", str(HERE.parent / "eval" / "lens12.json"), "--json", cwd=d); out = json.loads(r.stdout)
    assert r.returncode == 0 and out["recall"] == "10 of 10" and out["precision"] == "10 of 10" and not out["decoy_rows"] and not out["clean_twin_rows"], out

@test("5.2 SC-74: --integrity-record writes hosts only, and a later swap of a link target, a form action or a new script origin fails against it")
def _(d):
    page = '<a href="https://help.example.com/">Contact support</a>\n<form action="/pay"></form>\n<script src="https://cdn.example.org/a.js" integrity="sha384-x"></script>\n'
    write(d, "site/index.html", page)
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=d); assert r.returncode == 0, r.stderr
    rec = json.loads((d / ".critic/integrity-baseline.json").read_text())["files"]["site/index.html"]
    assert rec == {"links": ["Contact support\texample.com"], "forms": ["(this site)"], "origins": ["example.org"]}, rec
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert not [x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "integrity"], "an unchanged page raises nothing"
    write(d, "site/index.html", page.replace("help.example.com", "help.example.net").replace('"/pay"', '"https://pay.example.net/c"').replace("cdn.example.org", "cdn.example.net"))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    got = sorted((x["rule"], x["where"]) for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "integrity" and x["sev"] == "FAIL")
    assert got == [("integrity-changed", "site/index.html:1"), ("integrity-changed", "site/index.html:2"), ("integrity-new-origin", "site/index.html:3")], got

def _feed_mirror(d, npm_records, kev_cves):
    import zipfile
    for eco, recs in (("npm", npm_records), ("PyPI", [{"id": "PYSEC-1", "affected": [{"package": {"ecosystem": "PyPI", "name": "Django"}, "versions": ["3.2.0"]}]}])):
        (d / "mirror" / eco).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(d / "mirror" / eco / "all.zip", "w") as z:
            for r in recs: z.writestr(r["id"] + ".json", json.dumps(r))
    write(d, "mirror/kev.json", json.dumps({"vulnerabilities": [{"cveID": c} for c in kev_cves]}))
    return {"CURMUDGEON_FEED_DIR": str(d / "feed"), "CURMUDGEON_FEED_OSV": (d / "mirror").as_uri(), "CURMUDGEON_FEED_KEV": (d / "mirror/kev.json").as_uri()}

@test("5.2 SC-75: the security feed downloads nothing until switched on, and off never downloads")
def _(d):
    env = _feed_mirror(d, [{"id": "GHSA-1", "affected": []}], [])
    F = S / "security_feed.py"
    r = run(F, "update", cwd=d, env=env); assert r.returncode == 3 and "off" in r.stdout and not (d / "feed/osv-npm.json").exists(), r.stdout
    assert run(F, "due", cwd=d, env=env).returncode == 1
    run(F, "set", "--cadence", "off", cwd=d, env=env)
    r = run(F, "update", "--force", cwd=d, env=env); assert r.returncode == 3 and not (d / "feed/osv-npm.json").exists()
    assert json.loads((d / "feed/feed.json").read_text())["consent"] == "no"

@test("5.2 SC-75: with the feed on, lockfiles are checked locally; a CISA KEV CVE makes it a FAIL, a range and an exact version both match, and a fixed version does not")
def _(d):
    rec = {"id": "GHSA-lp", "aliases": ["CVE-2099-0001"], "summary": "bad pad", "affected": [{"package": {"ecosystem": "npm", "name": "left-pad"}, "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "1.3.0"}]}]}]}
    env = _feed_mirror(d, [rec], ["CVE-2099-0001"]); F = S / "security_feed.py"
    run(F, "set", "--cadence", "weekly", cwd=d, env=env)
    r = run(F, "update", cwd=d, env=env); assert r.returncode == 0 and "npm 1" in r.stdout, r.stdout + r.stderr
    assert json.loads((d / "feed/feed-log.jsonl").read_text().splitlines()[-1])["downloads"][0]["sha256"]
    assert run(F, "due", cwd=d, env=env).returncode == 1, "just updated: not due for a week"
    lock = {"lockfileVersion": 3, "packages": {"": {}, "node_modules/left-pad": {"version": "1.1.0"}, "node_modules/safe": {"version": "1.3.0"}}}
    write(d, "p/package.json", json.dumps({"dependencies": {"left-pad": "1.1.0"}})); write(d, "p/package-lock.json", json.dumps(lock))
    write(d, "p/requirements.txt", "django==3.2.0\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d / "p", env=env)
    got = {(x["sev"], x["what"].split(" has")[0]) for x in json.loads((d / "p/.critic/scan/report.json").read_text())["findings"] if x["rule"] == "deps-vulnerable"}
    assert got == {("FAIL", "left-pad 1.1.0"), ("WARN", "django 3.2.0")}, got
    sys.path.insert(0, str(S)); import importlib, security_feed; importlib.reload(security_feed)
    assert security_feed.vkey("1.0.0-rc1") < security_feed.vkey("1.0.0") < security_feed.vkey("1.10") and security_feed.vkey("1.9") < security_feed.vkey("1.10")
    assert not security_feed.affected("1.3.0", ["x", [], [["SEMVER", [["introduced", "0"], ["fixed", "1.3.0"]]]], [], ""])

@test("5.2 SC-75: a damaged or shrunken download keeps the old copy")
def _(d):
    rec = lambda i: {"id": f"GHSA-{i}", "affected": [{"package": {"ecosystem": "npm", "name": f"p{i}"}, "versions": ["1.0.0"]}]}
    env = _feed_mirror(d, [rec(i) for i in range(10)], []); F = S / "security_feed.py"
    run(F, "set", "--cadence", "daily", cwd=d, env=env); assert run(F, "update", cwd=d, env=env).returncode == 0
    before = (d / "feed/osv-npm.json").read_text()
    _feed_mirror(d, [rec(1)], [])
    r = run(F, "update", "--force", cwd=d, env=env); assert r.returncode == 1 and "lost over half" in r.stdout, r.stdout
    (d / "mirror/npm/all.zip").write_bytes(b"not a zip")
    r = run(F, "update", "--force", cwd=d, env=env); assert r.returncode == 1 and "old copy is kept" in r.stdout
    assert (d / "feed/osv-npm.json").read_text() == before

@test("5.2 security scan mode: begin --security keeps the tier's panel, focuses the briefs and plan on security, runs the scan with --focus security, asks about the feed only through the lead, and a plain run drops the focus")
def _(d):
    write(d, "src/app.js", APP); write(d, "src/page.html", '<div style="color:red">x</div>\n<a href="https://bank.example.net/">bank.example.com</a>\n')
    out = run(S / "critic_run.py", "begin", "--security", "--files", "src/app.js", "src/page.html", "--tier", "full", cwd=d).stdout
    assert "security scan, full tier" in out and "A, B, C" in out and "--focus security" in out, out
    assert "security feed: off" in out and "set --cadence" in out and "Unattended: don't ask" in out, out
    assert not (d / "feed").exists() and not (pathlib.Path(TMP) / "no-feed" / "feed.json").exists(), "begin never switches the feed on"
    assert all("Focus: security" in (d / f".critic/briefs/brief-{x}.md").read_text() for x in "ABC")
    assert "browser integrity" in json.loads((d / ".critic/plan.json").read_text())["lenses"]
    run(S / "critic_scan.py", ".", "--root", ".", "--focus", "security", cwd=d)
    rep = json.loads((d / ".critic/scan/report.json").read_text())
    assert rep["findings"] and {x["area"] for x in rep["findings"]} <= {"safety", "deps", "supply-chain", "agent-config", "integrity", "ci"}, {x["area"] for x in rep["findings"]}
    assert any(x["rule"] == "integrity-link-mismatch" for x in rep["findings"])
    out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d).stdout
    assert not (d / ".critic/focus.json").exists() and "Focus: security" not in (d / ".critic/briefs/brief-A.md").read_text() and "--focus" not in out

@test("decision 39: a clean-twin BLOCK fails the gate only when no Critical or High in that run is labelled a real bug")
def _(d):
    EV = HERE.parent / "eval"
    def run_(name, impact, label):
        r = d / name; write(r, ".critic/teardown.md", "**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low\n\n#### 5. VERDICT\n**BLOCK**\n")
        row = {"id": "F-1", "file": "store.js", "line": 75, "category": "data", "impact": impact, "title": f"Every save overwrites the list ({name})", "quote": "x"}
        write(r, ".critic/findings.jsonl", json.dumps(row) + "\n")
        key = re.sub(r"\W+", " ", " ".join(str(row.get(k, "")) for k in ("file", "line", "category", "title", "quote", "evidence", "failing_case", "remediation")).lower())[:160]
        return str(r / ".critic/teardown.md"), key
    a, ka = run_("real", "High", "real"); b, kb = run_("trivial", "High", "nitpick")
    write(d, "labels.json", json.dumps({ka: "real", kb: "nitpick"}))
    o = lambda t: subprocess.run([sys.executable, str(EV / "score.py"), t, "--clean", "1", "--baseline", str(d / "none.json"), "--labels", str(d / "labels.json")], capture_output=True, text=True).stdout
    assert "verdict BLOCK: False" in o(a), o(a)
    assert "verdict BLOCK: True" in o(b), o(b)

if __name__ == "__main__":
    shutil.rmtree(TMP, ignore_errors=True)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} passed"); sys.exit(1 if bad else 0)
