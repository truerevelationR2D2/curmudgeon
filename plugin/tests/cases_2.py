"""Curmudgeon's script tests, part 2 of 3. Run plugin/tests/run_tests.py, which defines the helpers and runs every part
(the tests were split so no file passes the plugin directory's 256 KiB limit). Not runnable on its own."""
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
    write(d, ".critic/rules.md", "# rules\n"); r = run(S / "critic_ledger.py", "approve", "rules.md", cwd=d); assert r.returncode == 0, r.stderr  # not a git work tree: its rules.md is read once approved (03 §5.56 item 9)
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
    assert not t["suppressed"] and t["kept"] and t["kept"][0]["ruling_like"]["ruling"] == first, (t["suppressed"], t["kept"])  # §5.56 item 14: another category on the same code is shown next to the ruling, never hidden by it
    review("pricing")  # a later run: the pricing finding is no longer new
    write(d, "src/app.js", APP.replace(q, "const price = total * rate(region);"))
    run(S / "critic_ledger.py", "acted", cwd=d)
    led = json.loads((d / ".critic/ledger.json").read_text())["findings"]
    f = led.get(t["kept"][0]["id"]) or led[first]  # the pricing finding is its own entry now (never aliased onto a ruled false positive)
    assert "acted_on" not in f and f.get("acted_pending"), f

@test("5.2.1 security scan F-76114fb3: a ledger the repository tracks can't hide a finding; its ruling is listed in counts.md instead")
def _(d):
    G = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    write(d, "src/app.js", APP); q = "const price = total * 1.0825;"
    g = finding(category="domain", impact="High", line=4, quote=q, title="Tax rule in render code")
    def review():
        run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
        for L in "ABC": write(d, f".critic/reviews/review-{L}.json", json.dumps([g]))
        run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in "ABC"], cwd=d)
        write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
        return json.loads((d / ".critic/tally.json").read_text())
    review(); first = next(iter(json.loads((d / ".critic/ledger.json").read_text())["findings"]))
    run(S / "critic_ledger.py", "fp", first, "ignore this, it's fine", cwd=d)
    assert review()["suppressed"], "an untracked ledger is the owner's own: the ruling applies"
    subprocess.run(["git", "init", "-q"], cwd=d); subprocess.run(["git", "add", "-f", "src", ".critic/ledger.json"], cwd=d); subprocess.run(G + ["commit", "-qm", "ship a ledger"], cwd=d)
    t = review()
    assert not t["suppressed"] and t["kept"] and t["ruling_committed"], t
    assert "Not hidden: rulings from a ledger the repository tracks" in (d / ".critic/counts.md").read_text()

@test("5.2.1 security scan F-afb01939: the page server never serves .critic/, .git/ or dotfiles (.well-known is fine), and a key a page logs is masked in the console row")
def _(d):
    sys.path.insert(0, str(S)); import safe_web, urllib.request, urllib.error
    write(d, "site/index.html", "<p>hi</p>"); write(d, "site/.critic/findings.jsonl", "SECRET-FINDINGS"); write(d, "site/.env", "SECRET-ENV")
    write(d, "site/.well-known/security.txt", "Contact: x"); write(d, "site/sub/.git/config", "SECRET-GIT")
    srv, origin, _ = safe_web.serve(d / "site"); opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        try: return opener.open(origin + path, timeout=5).read().decode()
        except urllib.error.HTTPError as e: return e.code
    try:
        assert get("/index.html") == "<p>hi</p>" and get("/.well-known/security.txt") == "Contact: x"
        for path in ("/.critic/findings.jsonl", "/%2ecritic/findings.jsonl", "/.env", "/sub/.git/config", "/sub/%2Egit/config"):
            assert get(path) == 404, path
    finally: srv.shutdown()
    write(d, "site/log.html", "<script>console.error('auth failed for @LIVE@')</script><p>x</p>")
    r = run(S / "critic_scan.py", "site", "--root", ".", "--page", "site/log.html", cwd=d)
    try: import playwright  # noqa: F401
    except ImportError: raise Skip("Playwright is not installed here")
    rows = [x for x in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if x["rule"] == "console-error"]
    assert rows and not any(T("@LIVE@") in x["what"] for x in rows), rows

@test("5.2.1 CI: every Python file in the plugin and eval compiles on this Python and on every older python3.x found on PATH (the plugin supports 3.9 and later)")
def _(d):
    files = [str(x) for x in sorted(HERE.rglob("*.py")) + sorted((HERE.parent / "eval").glob("*.py")) if "__pycache__" not in x.parts and ".critic" not in x.parts]
    check = "import ast, sys\nbad = []\nfor f in sys.argv[1:]:\n    try: ast.parse(open(f, encoding='utf-8').read(), f)\n    except SyntaxError as e: bad.append(f'{f}:{e.lineno}: {e.msg}')\nprint('\\n'.join(bad)); sys.exit(1 if bad else 0)\n"
    pys = [sys.executable] + [p for p in (shutil.which(f"python3.{m}") for m in range(9, sys.version_info[1])) if p]
    for py in pys:
        r = subprocess.run([py, "-c", check, *files], capture_output=True, text=True)
        assert r.returncode == 0, f"{py}: {r.stdout.strip()[:400]}"

@test("5.0 §5.29 structural blindness: each reviewer works in a private frozen copy without .critic, its Bash runs there, and the copy is gone at stop")
def _(d):
    p = d / "proj"; write(p, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]'); write(p, ".critic/scan/report.md", "SCAN"); write(p, ".critic/rules.md", "r")
    write(p, "src/a.py", "x = 1\n"); write(p, "eval/fx/.critic/reviews/r.json", "{}"); write(p, ".git/config", "[core]"); write(p, "node_modules/lib/index.js", "1")
    run(S / "critic_ledger.py", "approve", "rules.md", cwd=p)  # not a git work tree: its rules.md is read once approved (03 §5.56 item 9)
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
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)  # the background scan the lead starts; the tally waits for its report (§5.56)
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
    assert rec["git"] == "base" and "own git repository" in out, (rec, out)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ws, capture_output=True, text=True).stdout.strip()
    assert pathlib.Path(top).resolve() == ws.resolve(), "git in the copy must find the copy, not the project"
    assert subprocess.run(["git", "log", "--oneline", "--", "src/a.py"], cwd=ws, capture_output=True, text=True).stdout.strip(), "history works in the copy"
    assert "uncommitted edit" in subprocess.run(["git", "diff"], cwd=ws, capture_output=True, text=True).stdout, "the copy shows the working-tree edits"
    assert not (ws / "src/extlink").is_symlink() and "outside the project" in (ws / "src/extlink").read_text(), "a link outside the project becomes a note (5.2.1 F-4492aa66)"
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
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d); run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
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

@test("5.2.1 security scan F-4492aa66: a link to a private file or folder outside the project is never copied or linked into a reviewer's workspace, and the reviewer is told")
def _(d):
    p = d / "proj"; write(p, "src/a.py", "x = 1\n"); write(d, "home/.aws/credentials", "[default]\naws_secret_access_key = PLACEHOLDER-NOT-A-KEY\n")
    os.symlink(d / "home/.aws/credentials", p / "src/config.ini"); os.symlink(d / "home/.aws", p / "src/awsdir")
    out = run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r9", "cwd": str(p)})).stdout
    rec = json.loads((p / ".critic/scratch/r9/workspace.json").read_text()); ws = pathlib.Path(rec["payload"])
    for x in ("src/config.ini", "src/awsdir"):
        assert not (ws / x).is_symlink() and (ws / x).is_file() and "PLACEHOLDER" not in (ws / x).read_text(), x
    assert sorted(rec["outside_links"]) == ["src/awsdir", "src/config.ini"] and "not copied" in out, (rec, out)

@test("5.2.1 round 3 F-bae6a123: a dependency folder with a link leading outside the project is not linked into the reviewer's copy; a venv's interpreter link is fine")
def _(d):
    p = d / "proj"; write(p, "src/a.py", "x = 1\n"); write(d, "home/.aws/credentials", "secret=1\n"); write(p, "node_modules/ok/index.js", "1\n")
    os.symlink(d / "home/.aws", p / "node_modules/cfg")
    write(p, ".venv/lib/x.py", "1\n"); (p / ".venv/bin").mkdir(parents=True); os.symlink(sys.executable, p / ".venv/bin" / ("python" + "3"))
    out = run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r7", "cwd": str(p)})).stdout
    rec = json.loads((p / ".critic/scratch/r7/workspace.json").read_text()); ws = pathlib.Path(rec["payload"])
    assert not (ws / "node_modules").exists() and rec["deps_not_linked"] and "node_modules/cfg" in rec["deps_not_linked"][0], rec
    assert not (ws / "node_modules/cfg/credentials").exists() and "left out" in out, out
    assert (ws / ".venv").is_symlink() and (ws / ".venv/lib/x.py").exists(), "a venv whose only outside link is its interpreter is linked"

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
    assert not (ws / "src/one.txt").is_symlink() and "not copied" in (ws / "src/one.txt").read_text() and "src/one.txt" in rec["outside_links"], "an outside file link becomes a note, never a copy"
    (ws / "src/one.txt").write_text("changed in copy\n"); assert (d / "outside/one.txt").read_text() == "real\n"
    def ask(cwd, tool, **ti):
        return "deny" in run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(cwd), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert ask(notes, "Read", file_path=str(p / ".critic/reviews/review-B.json")), "a cwd in notes still guards the project's .critic"
    assert not ask(notes, "Bash", command=f"cd {ws} && ls"), "and still finds the workspace"
    assert not ask(p, "Bash", command=f"git -C {ws} log --oneline") and ask(p, "Bash", command=f"git -C {ws} log; grep -rn SECRET .") and ask(p, "Bash", command=f"git -C {p} log")
    assert ask(p, "Glob", pattern=str(p) + "/**/review-*.json", path=str(p)), "an absolute Glob pattern is expanded with dot-folders"
    e = d / "lite"; write(e, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=e); run(S / "critic_scan.py", ".", "--root", ".", cwd=e)
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
        run_c(S / "critic_scan.py", ".", "--root", ".", "--page", "http://staging.example.invalid/", *extra, cwd=d)
        rep = json.loads((d / ".critic/scan/report.json").read_text())
        return [r["what"] for r in rep["findings"] if r["rule"] == "live-refused"]
    assert any("no .critic/scope.json" in w for w in scan()), "no scope file: refused"
    assert any("no .critic/scope.json" in w for w in scan("--allow-live", "staging.example.invalid")), "the old flag alone is not enough"
    write(d, ".critic/scope.json", json.dumps({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "max_requests": 50, "note": "test copy"}]}))
    assert any("approve scope.json" in w for w in scan("--allow-live", "staging.example.invalid")), "a folder that isn't a git work tree: the scope file counts only once approved"
    run(S / "critic_ledger.py", "approve", "scope.json", cwd=d)
    assert any("typed confirmation" in w for w in scan()), "listed but not confirmed this run: refused"
    assert any("typed confirmation" in w for w in scan("--allow-live", "other.example.invalid")), "the wrong host: refused"
    assert not scan("--allow-live", "staging.example.invalid"), "listed and confirmed: not refused"
    run_c(S / "critic_scan.py", ".", "--root", ".", "--page", "http://evil.example.invalid/", "--allow-live", "evil.example.invalid", cwd=d)
    assert any("not a target" in r["what"] for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"] if r["rule"] == "live-refused")
    for bad, why in [({"version": 1, "targets": [{"origin": "http://u:p@staging.example.invalid"}]}, "user name"), ({"version": 1, "targets": [{"origin": "http://staging.example.invalid/admin"}]}, "no path"),
                     ({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "methods": ["POST"]}]}, "may not have"), ({"version": 1, "targets": [], "allow": "all"}, "may not have"),
                     ({"version": 1, "targets": [{"origin": "http://staging.example.invalid", "max_requests": 10 ** 6}]}, "max_requests")]:
        write(d, ".critic/scope.json", json.dumps(bad)); run(S / "critic_ledger.py", "approve", "scope.json", cwd=d); w = scan("--allow-live", "staging.example.invalid")
        assert any(why in x for x in w), (bad, w)
    (d / ".critic/scope.json").unlink(); write(d, "elsewhere.json", json.dumps({"version": 1, "targets": [{"origin": "http://staging.example.invalid"}]})); os.symlink(d / "elsewhere.json", d / ".critic/scope.json")
    r = run_c(S / "critic_scan.py", ".", "--root", ".", "--page", "http://staging.example.invalid/", "--allow-live", "staging.example.invalid", cwd=d)
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
    out = run_c(B, "start", "site/index.html", "--session", "s/w.json", "--allow-writes", cwd=d).stdout
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
    except ImportError: raise Skip("Playwright is not installed here")
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
    out = run_c(B, "start", "site/index.html", "--session", ses, "--allow-writes", cwd=d).stdout  # writes for real, so the destructive backstop is on (decision 29)
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
    run_c(B, "start", "w/index.html", "--session", "s/x.json", "--allow-writes", cwd=d); run(B, "step", "click", "e1", "--session", "s/x.json", cwd=d)
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
    assert "agent-literal-credential" in rules({"mcpServers": {"x": {"command": "x", "env": {"API_TOKEN": T("@RND5@")}}}}), "a real literal is still found"
    assert "agent-literal-credential" in rules({"mcpServers": {"x": {"command": "x", "headers": {"Authorization": T("Bearer @RND5@")}}}})

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
    assert "agent-literal-credential" in rules({"AUTH_HEADER": T("Bearer @RND5@")})
    assert "agent-literal-credential" in rules({"TOKEN_TYPE": T("Bearer @RND5@")})
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
