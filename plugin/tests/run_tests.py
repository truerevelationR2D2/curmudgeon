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
os.environ["CURMUDGEON_STATE_DIR"] = os.path.join(TMP, "state")  # in-process tests too

def run(script, *a, cwd, stdin=None, env=None):
    e = dict(os.environ, CRITIC_ROOT=str(cwd), TMPDIR=TMP, CURMUDGEON_FEED_DIR=os.path.join(TMP, "no-feed"), CURMUDGEON_STATE_DIR=os.path.join(TMP, "state")); e.update(env or {})  # a user's own feed or state never changes a test
    return subprocess.run([sys.executable, str(script), *a], cwd=cwd, capture_output=True, text=True, input=stdin, env=e, timeout=300)

def run_c(script, *a, cwd, **k):
    """run(), after recording the owner's consent for the flags the run carries (03 §5.56 item 12): a test stands in
    for the owner who said yes."""
    if "--allow-writes" in a or "--allow-live" in a:
        if not (pathlib.Path(cwd) / ".critic/ledger.json").exists(): run(S / "critic_ledger.py", "start", "review", cwd=cwd)
        if "--allow-writes" in a: run(S / "critic_ledger.py", "consent", "writes", cwd=cwd)
        if "--allow-live" in a: run(S / "critic_ledger.py", "consent", "live", a[a.index("--allow-live") + 1], cwd=cwd)
    return run(script, *a, cwd=cwd, **k)

ONLY = os.environ.get("CRITIC_TEST_ONLY", "")  # run only the tests whose name contains this text

class Skip(Exception):
    """Raised by a test that can't run here (no Playwright, say): reported as SKIP, never as PASS (round 3, F-c2e409d3)."""

def test(name):
    def deco(fn):
        if ONLY and ONLY not in name: return fn
        d = pathlib.Path(tempfile.mkdtemp(prefix="critic-test-"))
        try: fn(d); RESULTS.append((name, True, "")); print("PASS", name)
        except Skip as e: RESULTS.append((name, None, str(e))); print("SKIP", name, "—", e)
        except AssertionError as e:  # the line number too, so an assert without a message still says which one failed
            import traceback; fr = traceback.extract_tb(e.__traceback__)[-1]; ln = f"{os.path.basename(fr.filename)} line {fr.lineno}"
            RESULTS.append((name, False, f"{ln}: {e}")); print("FAIL", name, "—", f"{ln}: {e}")
        except Exception as e:
            import traceback; here = os.path.dirname(os.path.abspath(__file__))
            fr = next((f for f in reversed(traceback.extract_tb(e.__traceback__)) if os.path.dirname(os.path.abspath(f.filename)) == here), None)
            ln = f"{os.path.basename(fr.filename)} line {fr.lineno}" if fr else "?"
            RESULTS.append((name, False, f"{ln}: {e!r}")); print("FAIL", name, "—", f"{ln}: {e!r}")
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
    # high-randomness values the generic rule must catch, in pieces so no whole value sits in a file
    "@RND1@": "Zq9xR4!" + "vLm2#Tp8@wK",
    "@RND2@": "Zq9xR4vLm2" + "Tp8wKb7Yh3",
    "@RND3@": "Zq9xR4vLm2" + "Tp8wKb7Yh3Jd",
    "@RND4@": "testZq9xR4" + "vLm2Tp8wKb7Yh",
    "@RND5@": "Zq9xEXAMPLE" + "EXAMPLE7731",
    "@PGLOCAL@": "postgres://postgres:" + "postgres@localhost/app",
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

# The tests themselves live in cases_1.py to cases_3.py (split so no file passes the plugin directory's 256 KiB limit).
# Each part runs here, in this module's namespace, so the helpers above and the @test decorator are shared and every
# result lands in RESULTS. A failure names the part's own file and line.
for _part in sorted(pathlib.Path(__file__).resolve().parent.glob("cases_*.py")):
    exec(compile(_part.read_text(encoding="utf-8"), str(_part), "exec"), globals())

if __name__ == "__main__":
    shutil.rmtree(TMP, ignore_errors=True)
    bad = [r for r in RESULTS if r[1] is False]
    skipped = [r for r in RESULTS if r[1] is None]
    print(f"\n{len(RESULTS) - len(bad) - len(skipped)} of {len(RESULTS) - len(skipped)} passed" + (f"; {len(skipped)} skipped (could not run here)" if skipped else "")); sys.exit(1 if bad else 0)
