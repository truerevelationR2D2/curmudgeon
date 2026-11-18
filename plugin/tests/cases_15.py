"""Curmudgeon's script tests, part 15: release 5.10.0, the reviewers' boundary by outcome and by command list (03 §5.57
item 52; design and case table: the Project's "Design - reviewer boundary by outcome and allow-list"). Run
plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its own."""

def _al15():
    sys.path.insert(0, str(HERE / "hooks")); import importlib, conduct, allowlist; importlib.reload(conduct); importlib.reload(allowlist); return allowlist

def _setup15(d, ids=("r1",), claim="C"):
    p = d / "proj"; write(p, "src/app.py", "x = 1\n"); write(p, ".critic/reviews/review-B.json", "{}")
    recs = {a: _ws(p, a) for a in ids}
    claim_for(p, ids[0], claim)
    return p, recs

def _call15(p, aid, cmd, tid, role="reviewer"):
    stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(p), "agent_type": f"curmudgeon:curmudgeon-{role}", "agent_id": aid, "tool_use_id": tid})
    return stdin, run(H / "pre_tool.py", cwd=p, stdin=stdin).stdout

def _post15(p, stdin): return run(H / "post_tool.py", cwd=p, stdin=stdin)

def _lines15(p, kind, aid):
    f = p / ".critic/proctor" / kind / f"{aid}.jsonl"
    return [json.loads(x)["why"] for x in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []

@test("5.10.0 command list (case table rows 1-4, 10-18): honest reading, loops, here-documents, notes and read-only git pass; writes outside the copy and notes, git that changes the repository, bash -c, eval and source are blocked with what to use instead")
def _(d):
    A = _al15(); ws = str(d / "p/.critic/scratch/r1/payload"); notes = str(d / "p/.critic/scratch/r1/notes")
    ok = ["cat src/app.js | head -50", "for f in src/*.js; do wc -l $f; done", "python3 - <<'EOF'\nprint(open('src/app.js').read()[:9])\nEOF",
          "cat > ../notes/p.py <<'EOF'\nprint(1)\nEOF\npython3 ../notes/p.py", "cp src/a.js ../notes/", "git log --oneline -5", "npm test",
          "sed -i s/a/b/ src/x.js", "node -e 'console.log(1)'", "timeout 5 python3 ../notes/p.py", "ls -la . src", "cat -n $(git ls-files | head -3)",
          "python3 -m http.server 8765 >/dev/null 2>&1 & sleep 1", "grep -rn TODO . | wc -l", "find . -name '*.py' | xargs wc -l"]
    for c in ok: assert A.problem(f"cd {ws} && {c}", ws, notes) is None, (c, A.problem(f"cd {ws} && {c}", ws, notes))
    blocked = ["mkdir -p ../../../reviews", f"rm -rf {d}/p/src", "git checkout -- .", "bash -c 'cat src/a.js'", "eval cat src/a.js", "source ../notes/env.sh",
               "find . -name x -delete", "npm install left-pad", "echo \"$(cat src/a.js)\"", "pip install x", "kill -9 1234", "f() { cat x; }; f", "diff <(ls) <(ls src)"]
    for c in blocked:
        why = A.problem(f"cd {ws} && {c}", ws, notes)
        assert why and any(k in why for k in ("instead", "use", "outside", "reviewers")), (c, why)  # each block says what to do

@test("5.10.0 outcome check (case table rows 5, 7, 19): a write into another review or the project by code a reviewer ran is cut whatever its spelling; its own notes and its claimed review are not; a change while two reviewers' commands overlap is listed for the owner and cuts no one")
def _(d):
    p, recs = _setup15(d, ("r1", "r2")); ws = recs["r1"]["payload"]
    s, out = _call15(p, "r1", f"cd {ws} && ls", "t0"); assert "deny" not in out, out; _post15(p, s)
    s, out = _call15(p, "r1", f"cd {ws} && python3 -c \"import os; open(os.path.join('..','..','..','re'+'views','review-B.json'),'w').write('x')\"", "t1")
    assert "deny" not in out, ("the spelling slips past the text rule; the outcome check is what catches it", out)
    time.sleep(0.05); (p / ".critic/reviews/review-B.json").write_text("forged", encoding="utf-8"); _post15(p, s)
    assert any("review-B.json" in w for w in _lines15(p, "cut", "r1")), ("another review changed during its command: cut", _lines15(p, "cut", "r1"))
    s, out = _call15(p, "r1", f"cd {ws} && echo hi > ../notes/x.txt", "t2"); assert "deny" not in out, out
    (pathlib.Path(ws).parent / "notes" / "x.txt").write_text("hi", encoding="utf-8"); (p / ".critic/reviews/review-C.json").write_text("{}", encoding="utf-8"); _post15(p, s)
    assert not any("x.txt" in w or "review-C" in w for w in _lines15(p, "cut", "r1")), ("its notes and its own claimed review", _lines15(p, "cut", "r1"))
    s1, _ = _call15(p, "r1", f"cd {ws} && ls", "t3"); s2, _ = _call15(p, "r2", f"cd {recs['r2']['payload']} && ls", "t4")
    time.sleep(0.05); (p / "src/app.py").write_text("x = 2\n", encoding="utf-8"); _post15(p, s1); _post15(p, s2)
    assert not any("app.py" in w for w in _lines15(p, "cut", "r1") + _lines15(p, "cut", "r2")), "overlapping commands: no one is cut"
    assert any("app.py" in w for w in _lines15(p, "unattributed", "unattributed")), "listed for the owner"

@test("5.10.0 outcome check: a blocked command never starts a window; a change between runs is never charged; caches written by honest test runs are not changes")
def _(d):
    p, recs = _setup15(d); ws = recs["r1"]["payload"]
    s, out = _call15(p, "r1", f"cd {ws} && git checkout -- .", "b1"); assert "deny" in out, out
    assert any("git checkout" in w for w in _lines15(p, "blocked", "r1")), "listed for the owner"
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "c1"); _post15(p, s)
    time.sleep(0.2); (p / "src/edit.py").write_text("y = 1\n", encoding="utf-8"); time.sleep(0.2)  # the owner edits with no command running
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "c2"); write(p, "src/__pycache__/app.cpython-313.pyc", "x"); _post15(p, s)
    assert not _lines15(p, "cut", "r1"), ("the owner's edit and a cache are no one's", _lines15(p, "cut", "r1"))

def _oc15():
    sys.path.insert(0, str(HERE / "hooks")); import importlib, conduct, outcome; importlib.reload(conduct); importlib.reload(outcome); return outcome

@test("5.10.0 round 1 (F-b4ea77d7, F-1011538f, F-a0168e24, F-8408e3b5): another reviewer saving its own review, the stop hook's stamp, and a reviewer's command that writes its own claimed review cut no one and list nothing")
def _(d):
    p, recs = _setup15(d, ("r1", "r2")); claim_for(p, "r2", "A"); ws = recs["r1"]["payload"]
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "k0"); _post15(p, s)
    s, _ = _call15(p, "r1", f"cd {ws} && ls src", "k1")
    time.sleep(0.05); f = p / ".critic/reviews/review-A.json"; f.write_text('{"findings": []}', encoding="utf-8")
    run(H / "post_tool.py", cwd=p, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(f)}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r2"}))
    _post15(p, s)
    s, _ = _call15(p, "r1", f"cd {ws} && python3 ../notes/w.py", "k2"); time.sleep(0.05)
    (p / ".critic/reviews/review-C.json").write_text('{"findings": []}', encoding="utf-8"); _post15(p, s)
    assert not _lines15(p, "cut", "r1") and not _lines15(p, "cut", "r2"), (_lines15(p, "cut", "r1"), _lines15(p, "cut", "r2"))
    assert not _lines15(p, "unattributed", "unattributed"), ("an honest run is not DEGRADED", _lines15(p, "unattributed", "unattributed"))

@test("5.10.0 round 1 (F-d00d0b9b, F-d1b2776c, F-2de49bd3, F-50ec43fc): a same-size rewrite with its mtime put back, an mtime set in the future, deleting the check's own record, and erasing one's own cut are all still cut")
def _(d):
    if os.name == "nt": raise Skip("POSIX ctime: Windows keeps only the mtime, a known limit there")
    p, recs = _setup15(d); ws = recs["r1"]["payload"]; f = p / "src/app.py"
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "m0"); _post15(p, s)
    st = f.stat(); s, _ = _call15(p, "r1", f"cd {ws} && python3 ../notes/a.py", "m1"); time.sleep(0.05)
    f.write_text("x = 9\n", encoding="utf-8"); os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns)); _post15(p, s)
    assert any("app.py" in w for w in _lines15(p, "cut", "r1")), ("same size, mtime put back", _lines15(p, "cut", "r1"))
    g = p / "src/b.py"; write(p, "src/b.py", "y = 1\n")
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "m2"); _post15(p, s)
    s, _ = _call15(p, "r1", f"cd {ws} && python3 ../notes/b.py", "m3"); time.sleep(0.05)
    g.write_text("y = 2\n", encoding="utf-8"); os.utime(g, (time.time() + 3600, time.time() + 3600)); _post15(p, s)
    assert any("b.py" in w for w in _lines15(p, "cut", "r1")), ("mtime set an hour ahead", _lines15(p, "cut", "r1"))
    O = _oc15(); st_dir = O._state(p)
    s, _ = _call15(p, "r1", f"cd {ws} && python3 ../notes/c.py", "m4"); (st_dir / "baseline.json").unlink(); _post15(p, s)
    assert any("outcome check" in w for w in _lines15(p, "cut", "r1")), ("its own record deleted", _lines15(p, "cut", "r1"))
    (p / ".critic/proctor/cut/r1.jsonl").unlink()
    C = _c11(); assert C.listed(p, "r1", "cut"), "the cut is still there, from the copy outside the project"

@test("5.10.0 round 1 (F-4a7db951, F-e909fc80, F-91c5a0d8): a call whose end was never logged stops covering time once its agent starts another; a new run never charges last run's open call; past the file limit the check says it watched only folders")
def _(d):
    p, recs = _setup15(d, ("r1", "r2")); ws1, ws2 = recs["r1"]["payload"], recs["r2"]["payload"]
    s, _ = _call15(p, "r2", f"cd {ws2} && ls", "o1")  # its end is never logged
    time.sleep(0.05); s2, _ = _call15(p, "r2", f"cd {ws2} && ls", "o2"); _post15(p, s2)
    time.sleep(0.1); s3, _ = _call15(p, "r1", f"cd {ws1} && python3 ../notes/w.py", "o3"); time.sleep(0.05)
    (p / "src/app.py").write_text("x = 5\n", encoding="utf-8"); _post15(p, s3)
    assert any("app.py" in w for w in _lines15(p, "cut", "r1")) and not _lines15(p, "cut", "r2"), (_lines15(p, "cut", "r1"), _lines15(p, "cut", "r2"))
    q, rq = _setup15(d / "q"); wq = rq["r1"]["payload"]
    s, _ = _call15(q, "r1", f"cd {wq} && ls", "n1")  # last run: its end never logged
    time.sleep(0.1); (q / "src/app.py").write_text("x = 7\n", encoding="utf-8"); time.sleep(0.1)
    led = q / ".critic/ledger.json"; L = json.loads(led.read_text(encoding="utf-8")) if led.is_file() else {}; L["started_at"] = time.time(); led.write_text(json.dumps(L), encoding="utf-8")
    time.sleep(0.05); s, _ = _call15(q, "r1", f"cd {wq} && ls", "n2"); _post15(q, s)
    assert not _lines15(q, "cut", "r1"), ("a new run starts clean", _lines15(q, "cut", "r1"))
    O = _oc15(); r = d / "big"; [write(r, f"src/f{k}.py", "x\n") for k in range(12)]
    old = O.LIMIT; O.LIMIT = 5
    try:
        O.call_start(r, "r9", "z1"); found = O.call_end(r, "r9", "z1")
    finally: O.LIMIT = old
    assert any(a is None and p_ is None and "only the project's folders" in w for a, p_, w in found), found

@test("5.10.0 round 1 (F-3fcce4f1, F-a88cbddf, F-805a751d, F-e584fb6a, nits): git branch, tag, remote and config only in their listing forms; git -C only into its own copy; read-only git after global options; ./script runs; sort -o, rg --pre, npx of a fetched package, npm x and python -mpip are blocked; writes to a sibling folder are blocked")
def _(d):
    A = _al15(); ws = str(d / "p/.critic/scratch/r1/payload"); notes = str(d / "p/.critic/scratch/r1/notes")
    ok = ["git branch", "git branch -a", "git tag --list", "git remote -v", "git config --get user.name", "git --no-pager log -3", "git -C . status",
          "git -c core.pager=cat diff", "./run_checks", "../notes/probe", "npx jest --ci", "go test ./...", "cargo test", "python3 -m pytest -q"]
    for c in ok: assert A.problem(f"cd {ws} && {c}", ws, notes) is None, (c, A.problem(f"cd {ws} && {c}", ws, notes))
    bad = ["git branch -D main", "git tag v9", "git remote add x u", "git config user.name x", f"git -C {d}/p checkout -- .", "git -C /tmp status",
           "sort -o src/a.txt src/b.txt", "rg --pre ../notes/x.sh foo", "npx left-pad", "npm x left-pad", "pnpm dlx x", "python3 -mpip install x",
           f"echo x > {d}/p/.critic/scratch/r1/notes-evil/f", "go install x@latest", "cargo install x"]
    for c in bad: assert A.problem(f"cd {ws} && {c}", ws, notes), c
