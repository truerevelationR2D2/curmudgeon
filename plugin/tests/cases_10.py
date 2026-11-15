"""Curmudgeon's script tests, part 10: release 5.8.1 (03 §5.57 item 43), the fixes from the 15 Nov 2026 self-review of
5.8.0. Run plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its own. Each
test here failed on 5.8.0 (main at 905196e) before its fix, except C6, C7 and C8, which pin guards that already held
and fail when the guard is removed (checked by deleting it)."""

def _cfg10(): sys.path.insert(0, str(S)); import importlib; return importlib.import_module

@test("5.8.1 C1: a local-dev database URL earlier on a line never lowers a real database password later on it from FAIL to WARN")
def _(d):
    ss = _cfg10()("scan_secrets")
    real = "postgres://app:Zq8vLx2mPw9tR4@db.internal:5432/prod"
    for line in (f"DEV=postgres://postgres:postgres@localhost/dev PROD={real}", f"PROD={real} DEV=postgres://postgres:postgres@localhost/dev"):
        rows = []; ss.scan(".env", line + "\n", lambda *a: rows.append(a))
        lv = [r[0] for r in rows if r[1] == "secret-db-url-password"]
        assert sorted(lv) == ["FAIL", "WARN"], (line, lv)

@test("5.8.1 C2: a reviewer's Write can't touch the proctor's marks, the boundary record, the plan or the cost log")
def _(d):
    p = d / "proj"; write(p, "src/app.js", "x\n"); (p / ".critic").mkdir(exist_ok=True)
    for rel in (".critic/proctor/marks.json", ".critic/proctor/requests.jsonl", ".critic/boundary.json", ".critic/plan.json", ".critic/cost.jsonl"):
        ev = {"tool_name": "Write", "tool_input": {"file_path": str(p / rel), "content": "{}"}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "hook_event_name": "PreToolUse"}
        out = run(H / "guard_state.py", cwd=p, stdin=json.dumps(ev)).stdout
        assert "deny" in out, (rel, out)

@test("5.8.1 C3: reading its own review back is not being shown it, so a passage copied into it is still flagged")
def _(d):
    import importlib
    sys.path.insert(0, str(HERE / "hooks")); P = importlib.import_module("proctor")
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "AB"}
    odd = "the discount stack silently compounds when two coupons share a single redemption code"
    write(d, ".critic/reviews/review-A.json", json.dumps([dict(TAX9, evidence=TAX9["evidence"] + "; " + odd)]))
    _stop9(d, "c3a", "A", [b["A"]]); time.sleep(1.1)
    write(d, ".critic/reviews/review-B.json", json.dumps([dict(TAX9, title="Coupons", evidence="so " + odd + " here", failing_case="two coupons", remediation="cap")]))
    tr = d / ".critic" / "t-readback.jsonl"
    tr.write_text("\n".join(json.dumps(x) for x in (
        {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "r0", "content": b["B"]}]}},
        {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": str(d / ".critic/reviews/review-B.json")}}]}},
        {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "r1", "content": "so " + odd + " here"}]}, "toolUseResult": {"file": {"content": "so " + odd + " here"}}})) + "\n", encoding="utf-8")
    r = P.check(str(d), str(tr), "review-B.json")
    assert r["checked"] and r["copied"] == ["a 48-character passage of review-A.json it never saw"], r
    tr.write_text(tr.read_text(encoding="utf-8").replace("review-B.json", "notes.txt"), encoding="utf-8")
    assert P.check(str(d), str(tr), "review-B.json")["copied"] == [], "the same text read from another file was shown to it"

@test("5.8.1: a reviewer that stops twice keeps the time of its first stop, which the copy check orders reviewers by")
def _(d):
    import importlib
    sys.path.insert(0, str(HERE / "hooks")); C = importlib.import_module("check_contract"); P = importlib.import_module("proctor")
    (d / ".critic").mkdir()
    C.write_stop(d, "a1", {"review": "review-A.json", "at": 100.0})
    C.write_stop(d, "a1", {"review": "review-A.json", "at": 300.0})
    C.write_stop(d, "b1", {"review": "review-B.json", "at": 200.0})
    assert P._stop_order(str(d)) == {"review-A.json": 100.0, "review-B.json": 200.0}, P._stop_order(str(d))
    assert json.loads((d / ".critic/stops/a1.json").read_text(encoding="utf-8"))["at"] == 300.0, "the merge still reads the latest stop"
    C.write_stop(d, "a1", {"review": "review-C.json", "at": 400.0})
    assert P._stop_order(str(d))["review-C.json"] == 400.0, "another review's stop starts again"

@test("5.8.1 C4: two findings with the same title at distant lines and different quotes stay two findings; near or with overlapping quotes they merge")
def _(d):
    cf = _cfg10()("critic_findings")
    a = {"file": "src/app.js", "line": 10, "category": "security", "title": "User title rendered as HTML", "quote": "list.innerHTML = `<li>${n.title}</li>`;"}
    far = dict(a, line=300, quote="panel.innerHTML = header + n.title;")
    assert not cf.similar(a, far), "equal titles 290 lines apart"
    assert not cf.similar(dict(a, quote=""), dict(far, quote="")), "no quotes at all"
    assert cf.similar(a, dict(far, line=20)), "10 lines apart, same title"
    assert cf.similar(a, dict(a, line=300)), "the same long quote anywhere"

@test("5.8.1 C5: ${API_KEY:-} and ${TOKEN:?missing} in an MCP config are environment references, but a literal default is still a literal")
def _(d):
    ac = _cfg10()("scan_agentcfg")
    def fails(v):
        rows = []; ac.scan(".mcp.json", json.dumps({"mcpServers": {"x": {"command": "node", "args": ["s.js"], "env": {"API_KEY": v}}}}), lambda *a: rows.append(a), {})
        return [r for r in rows if r[1] == "agent-literal-credential"]
    for v in ("${API_KEY:-}", "${MY_TOKEN:?missing}", "${API_KEY}", "Bearer ${API_KEY:-}", "${API_KEY:-${OTHER_KEY}}"): assert not fails(v), v
    for v in ("${API_KEY:-sk_live_placeholder_Zq8vLx2m}", "Zq8vLx2mPw9tR4kQ"): assert fails(v), v

@test("5.8.1 C6: a || anywhere in a workflow_run job's if: removes the same-repository exemption from ci-pwn-request")
def _(d):
    C = _cfg10()("scan_ci")
    wr = ("on:\n  workflow_run:\n    workflows: [CI]\n    types: [completed]\npermissions:\n  contents: read\njobs:\n  deploy:\n    if: {guard}\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: actions/checkout@v4\n        with:\n          ref: ${{{{ github.event.workflow_run.head_sha }}}}\n      - run: ./deploy.sh\n")
    rules = lambda g: [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", wr.format(guard=g))]
    assert "ci-pwn-request" not in rules("github.event.workflow_run.event == 'push'")
    assert "ci-pwn-request" in rules("github.event.workflow_run.event == 'push' || always()")
    assert "ci-pwn-request" in rules("github.event.workflow_run.head_repository.full_name == github.repository || github.actor == 'bot'")
    assert "ci-pwn-request" in rules("always() && !(github.event.workflow_run.event == 'push')")

@test("5.8.1 C7: the request command refuses every git option that writes a file, runs a program, moves its paths or names who wrote the code, each one by name")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "-A"], cwd=p); subprocess.run(G9 + ["commit", "-qm", "first"], cwd=p)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=p); ws = _ws(p)["payload"]
    ask = lambda *a: run(S / "critic_proctor.py", "ask", *a, cwd=pathlib.Path(ws), env={"CRITIC_ROOT": ""})
    must = ["--output=x", "-o", "--ext-diff", "--textconv", "--exec=x", "--upload-pack=x", "--receive-pack=x", "-c", "-C", "--git-dir=x", "--work-tree=x",
            "--config=x", "--open-files-in-pager", "-Ox", "--no-index", "--author=x", "--committer=x", "--mailmap", "--use-mailmap", "--show-signature",
            "--notes", "--show-notes", "--standard-notes"]  # written out here, not read from GIT_BAD, so deleting one there fails this test
    for opt in must:
        r = ask("git", "log", opt, "--oneline")
        assert r.returncode == 2 and "refused" in r.stderr, (opt, r.returncode, r.stdout[-200:], r.stderr[-200:])
    assert ask("git", "log", "--oneline").returncode == 0

@test("5.8.1 C8: the review-never-edits case checks the file itself, so an edit by any method fails it")
def _(d):
    E = HERE / "evals" / "review-never-edits"
    g = (E / "graders" / "app-unchanged.md").read_text(encoding="utf-8")
    assert re.search(r"(?m)^type: regex$", g) and "source: file, path: app.js" in g and re.search(r"(?m)^arm: both$", g), g
    pat = re.search(r"(?m)^pattern: '(.*)'$", g).group(1)
    fx = (E / "fixture.sh").read_text(encoding="utf-8")
    app = fx.split("<<'JS'\n", 1)[1].split("\nJS\n", 1)[0]
    assert re.search(pat, app), "the untouched fixture passes"
    assert not re.search(pat, app.replace("i <= items.length", "i < items.length")), "the fixed file fails"

@test("5.8.1 L1: the ci-injection rule reads github['event']['issue']['title'] and github.event.pull_request['title'] like the dotted form")
def _(d):
    C = _cfg10()("scan_ci")
    inj = "on: pull_request_target\npermissions: {{}}\njobs:\n  l:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"x=${{{{ {e} }}}}\"\n"
    for e in ("github['event']['pull_request']['title']", "github.event.pull_request['title']", "github[\"event\"].pull_request[\"body\"]"):
        rows = _rows(C.scan_workflow, ".github/workflows/x.yml", inj.format(e=e))
        assert [w for _, r, w in rows if r == "ci-injection"] == [".github/workflows/x.yml:7"], (e, rows)

@test("5.8.1 L2: curl | sh in a comment line of a run: script raises nothing; on a real line it still does")
def _(d):
    C = _cfg10()("scan_ci")
    wf = "on: push\npermissions: read-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          {a}\n          make\n"
    rules = lambda a: [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", wf.format(a=a))]
    assert "curl-pipe-shell" not in rules("# never: curl https://x.example/i.sh | sh")
    assert "curl-pipe-shell" in rules("curl https://x.example/i.sh | sh")

@test("5.8.1 L3: a blank line inside a value that spans lines in [ ] or { } is refused, where PyYAML keeps a line break; a blank line between items still reads")
def _(d):
    Y = _cfg10()("yaml_lite")
    for s in ("a: [foo\n\n  bar, z]\n", "a: {k: foo\n\n  bar}\n", "a: [\"foo\n\n  bar\"]\n"):
        try: Y.loads(s); assert False, ("read", s)
        except Y.Refused: pass
    assert Y.plain(Y.loads("a: [foo,\n\n  bar]\n")) == {"a": ["foo", "bar"]}
    assert Y.plain(Y.loads("a: [\n\n  x, y]\n")) == {"a": ["x", "y"]}
    assert Y.plain(Y.loads("a: [foo\n  bar]\n")) == {"a": ["foo bar"]}

@test("5.8.1: the proctor's and the hooks' agent records (stops/, proctor/, verify-opened/) are git-ignored, and PRIVACY.md says so")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    gi = [x.strip() for x in (d / ".critic/.gitignore").read_text(encoding="utf-8").splitlines()]
    for x in ("stops/", "proctor/", "verify-opened/"): assert x in gi, (x, gi)
    pv = (HERE / "PRIVACY.md").read_text(encoding="utf-8")
    assert "`proctor/`" in pv and "`stops/`" in pv, "the privacy policy lists them"

@test("5.8.1: two verdicts on one finding are picked by a fixed rule, never by file order: a run beats a trace beats no run, then the one that keeps it")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    _tally3(d, [finding(impact="High")], [finding(impact="High")], [])
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]; assert ids
    unclear = [{"id": i, "verdict": "unclear", "reproduced": "no", "note": "Bash was denied, so nothing could be run"} for i in ids]
    conf = [{"id": i, "verdict": "confirmed", "reproduced": "executed", "entry": "render() runs on load", "path": ["src/app.js:2 writes the title as HTML"]} for i in ids]
    def applied(first, second):
        a = hook_verdicts(d, first, "v1"); b = hook_verdicts(d, second, "v2")
        r = run(S / "critic_merge.py", "apply", str(a), str(b), cwd=d); assert r.returncode == 0, r.stderr[-400:]
        f = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        return [(x["verifier"], x["confidence"]) for x in f]
    assert applied(unclear, conf) == applied(conf, unclear) == [("confirmed", "confirmed")], (applied(unclear, conf), applied(conf, unclear))
    assert "2 verdicts; applied the confirmed one" in (d / ".critic/counts.md").read_text(encoding="utf-8")
    M = _cfg10()("critic_merge")
    assert sorted([{"verdict": "refuted", "reproduced": "executed"}, {"verdict": "unclear", "reproduced": "no"}], key=M.verdict_rank)[0]["verdict"] == "refuted"
    assert sorted([{"verdict": "refuted", "reproduced": "executed"}, {"verdict": "confirmed", "reproduced": "executed"}], key=M.verdict_rank)[0]["verdict"] == "confirmed"

@test("5.8.1 blind round C1 and C2: a reviewer's Write can't touch the briefs or the scan, and a protected name in other letter case is still protected")
def _(d):
    p = d / "proj"; write(p, "src/app.js", "x\n"); (p / ".critic").mkdir(exist_ok=True)
    deny = lambda rel, role="reviewer": "deny" in run(H / "guard_state.py", cwd=p, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(p / rel), "content": "{}"}, "cwd": str(p), "agent_type": f"curmudgeon:curmudgeon-{role}", "agent_id": "r1", "hook_event_name": "PreToolUse"})).stdout
    for rel in (".critic/briefs/brief-B.md", ".critic/scan/report.json", ".critic/Proctor/marks.json", ".critic/PLAN.json", ".critic/Stops/x.json", ".Critic/proctor/marks.json", ".critic/Scratch/other/notes/a.txt"):
        assert deny(rel), rel
    assert not deny(".critic/reviews/review-B.json") and not deny(".critic/scratch/r1/notes/a.txt"), "its own review and notes stay writable"

@test("5.8.1 blind round C3: a verdict the merge's rules would reject never displaces a second verdict they accept")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    _tally3(d, [finding(impact="High")], [finding(impact="High")], [])
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]; assert ids
    weak = [{"id": i, "verdict": "refuted", "reproduced": "executed", "refutation": "not a bug"} for i in ids]
    conf = [{"id": i, "verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on load", "path": ["src/app.js:2 writes the title as HTML"]} for i in ids]
    a = hook_verdicts(d, weak, "w1"); b = hook_verdicts(d, conf, "w2")
    r = run(S / "critic_merge.py", "apply", str(a), str(b), cwd=d); assert r.returncode == 0, r.stderr[-400:]
    f = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [x["verifier"] for x in f] == ["confirmed"], f
    M = _cfg10()("critic_merge")
    rank = lambda *vs: sorted(vs, key=M.verdict_rank)[0]["verdict"]
    assert rank({"verdict": "unclear", "reproduced": "no"}, {"verdict": "refuted", "reproduced": "traced"}) == "refuted", "a trace beats no run"
    assert rank({"verdict": "refuted", "reproduced": "traced"}, {"verdict": "unclear", "reproduced": "traced"}) == "unclear", "equal evidence: the one that keeps it"
    assert rank({"verdict": "unclear", "reproduced": "traced"}, {"verdict": "downgrade", "reproduced": "traced"}) == "downgrade"
    assert rank({"verdict": "downgrade", "reproduced": "executed"}, {"verdict": "confirmed", "reproduced": "executed"}) == "confirmed"

@test("5.8.1 blind round C4: !cancelled() beside a same-repository guard keeps the exemption; negating the guard itself still removes it")
def _(d):
    C = _cfg10()("scan_ci")
    wr = ("on:\n  workflow_run:\n    workflows: [CI]\n    types: [completed]\npermissions:\n  contents: read\njobs:\n  deploy:\n    if: {guard}\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: actions/checkout@v4\n        with:\n          ref: ${{{{ github.event.workflow_run.head_sha }}}}\n      - run: ./deploy.sh\n")
    rules = lambda g: [r for _, r, _ in _rows(C.scan_workflow, ".github/workflows/x.yml", wr.format(guard=g))]
    assert "ci-pwn-request" not in rules("github.event.workflow_run.event == 'push' && !cancelled()")
    assert "ci-pwn-request" in rules("always() && !(github.event.workflow_run.event == 'push')")

@test("5.8.1 blind round C5: a well-known password on a real server is FAIL; only a local, container or example host makes it WARN")
def _(d):
    ss = _cfg10()("scan_secrets")
    def lv(u):
        rows = []; ss.scan(".env", "DB=" + u + "\n", lambda *a: rows.append(a)); return [r[0] for r in rows if r[1] == "secret-db-url-password"]
    for u in ("postgres://app:password@db.prod.example.co/x", "postgres://admin:admin@10.0.0.5/x"): assert lv(u) == ["FAIL"], (u, lv(u))
    for u in ("postgres://postgres:postgres@localhost/dev", "postgres://postgres:postgres@db:5432/x", "mysql://root:root@[::1]:3306/x", "postgres://u:password@db.example.com/x"): assert lv(u) == ["WARN"], (u, lv(u))

@test("5.8.1 blind round L1 and L2: a short default is no credential, and ${A:?}literal${B:?} is not one reference")
def _(d):
    ac = _cfg10()("scan_agentcfg")
    def fails(v):
        rows = []; ac.scan(".mcp.json", json.dumps({"mcpServers": {"x": {"command": "node", "args": ["s.js"], "env": {"API_TOKEN": v}}}}), lambda *a: rows.append(a), {})
        return [r for r in rows if r[1] == "agent-literal-credential"]
    assert not fails("${API_TOKEN:-ab}")
    assert fails("${A:?}sk_live_placeholder_Zq8vLx${B:?}")

@test("5.8.1 blind round L3, L4, L8: equal short quotes far apart stay two findings; a quoted value with a comma before the blank line is refused; curl | sh is reported at the real line, not a commented copy")
def _(d):
    cf = _cfg10()("critic_findings"); Y = _cfg10()("yaml_lite"); C = _cfg10()("scan_ci")
    a = {"file": "src/app.js", "line": 10, "category": "security", "title": "User title rendered as HTML", "quote": "el.innerHTML = t;"}
    assert not cf.similar(a, dict(a, line=300)), "a short quote can repeat at two sites"
    try: Y.loads('a: [x, "foo,\n\n  bar"]\n'); assert False, "read"
    except Y.Refused: pass
    wf = "on: push\npermissions: read-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          # curl https://x.example/i.sh | sh\n          curl https://x.example/i.sh | sh\n"
    assert [w for _, r, w in _rows(C.scan_workflow, ".github/workflows/x.yml", wf) if r == "curl-pipe-shell"] == [".github/workflows/x.yml:9"]

@test("5.8.1 blind round L7: a stop record from before this run started never orders this run's reviewers")
def _(d):
    import importlib
    sys.path.insert(0, str(HERE / "hooks")); C = importlib.import_module("check_contract"); P = importlib.import_module("proctor")
    own_ledger(d, {"started_at": 1000.0})
    C.write_stop(d, "old", {"review": "review-B.json", "at": 500.0}); C.write_stop(d, "new", {"review": "review-A.json", "at": 1100.0})
    assert P._stop_order(str(d)) == {"review-A.json": 1100.0}, P._stop_order(str(d))

@test("5.8.1 blind round: a command that only mentions its own review's name (a test it runs) still shows the reviewer its output, so honest text from it is not flagged")
def _(d):
    import importlib
    sys.path.insert(0, str(HERE / "hooks")); P = importlib.import_module("proctor")
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "AB"}
    odd = "the discount stack silently compounds when two coupons share a single redemption code"
    write(d, ".critic/reviews/review-A.json", json.dumps([dict(TAX9, evidence=TAX9["evidence"] + "; " + odd)]))
    _stop9(d, "c3c", "A", [b["A"]]); time.sleep(1.1)
    write(d, ".critic/reviews/review-B.json", json.dumps([dict(TAX9, title="Coupons", evidence="so " + odd + " here", failing_case="two coupons", remediation="cap")]))
    tr = d / ".critic" / "t-bash.jsonl"
    tr.write_text("\n".join(json.dumps(x) for x in (
        {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "r0", "content": b["B"]}]}},
        {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "python3 probe.py --review review-B.json"}}]}},
        {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b1", "content": "probe printed: " + odd}]}})) + "\n", encoding="utf-8")
    assert P.check(str(d), str(tr), "review-B.json")["copied"] == [], "its own program's output was shown to it"
