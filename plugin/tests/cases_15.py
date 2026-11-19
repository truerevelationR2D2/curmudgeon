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
          "python3 -m http.server 8765 >/dev/null 2>&1 & sleep 1", "grep -rn TODO . | wc -l", "find . -name '*.py' | xargs wc -l", "echo \"$(cat src/a.js)\"", "grep -n function src/a.js"]
    for c in ok: assert A.problem(f"cd {ws} && {c}", ws, notes) is None, (c, A.problem(f"cd {ws} && {c}", ws, notes))
    blocked = {"mkdir -p ../../../reviews": "outside your copy", f"rm -rf {d}/p/src": "outside your copy", "git checkout -- .": "git checkout can change",
               "bash -c 'cat src/a.js'": "command given as text", "eval cat src/a.js": "eval", "source ../notes/env.sh": "source", "find . -name x -delete": "find",
               "npm install left-pad": "npm install", "echo \"$(curl -s example.test)\"": "curl", "pip install x": "pip", "kill -9 1234": "kill",
               "f() { cat x; }; f": "a shell function", "function g { ls; }": "a shell function", "diff <(ls) <(ls src)": "process substitution", "command kill 1": "command"}
    for c, why_has in blocked.items():  # each block names what it blocked and says what to do instead (round 3, F-854d1d1a: any reason used to pass)
        why = A.problem(f"cd {ws} && {c}", ws, notes)
        assert why and why_has in why and any(k in why for k in ("instead", "use", "outside", "reviewers")), (c, why)

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

@test("5.10.0 round 2 (F-cec6dc20, F-b75d95cf, F-9e4f9a59): another reviewer's own review save that lands during a command is never charged, even before its known-write mark; a forged change to another's claimed review is still charged once that reviewer stops; a known review changed afterwards is charged")
def _(d):
    p, recs = _setup15(d, ("r1", "r2")); claim_for(p, "r2", "A"); ws = recs["r1"]["payload"]; f = p / ".critic/reviews/review-A.json"
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "q0"); _post15(p, s)
    s, _ = _call15(p, "r1", f"cd {ws} && ls src", "q1"); time.sleep(0.05); f.write_text('{"findings": []}', encoding="utf-8"); _post15(p, s)  # r1's command ends before r2's mark
    run(H / "post_tool.py", cwd=p, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(f)}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r2"}))
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "q2"); _post15(p, s)
    assert not _lines15(p, "cut", "r1") and not _lines15(p, "unattributed", "unattributed"), (_lines15(p, "cut", "r1"), _lines15(p, "unattributed", "unattributed"))
    s, _ = _call15(p, "r1", f"cd {ws} && python3 ../notes/f.py", "q3"); time.sleep(0.05); f.write_text('{"findings": ["forged"]}', encoding="utf-8"); _post15(p, s)
    assert not _lines15(p, "cut", "r1"), "it waits for r2's own save"
    write(p, ".critic/stops/r2.json", "{}")  # r2 stops without saving that content
    s, _ = _call15(p, "r1", f"cd {ws} && ls", "q4"); _post15(p, s)
    assert any("review-A.json" in w for w in _lines15(p, "cut", "r1")), ("charged once its owner stopped", _lines15(p, "cut", "r1"))

@test("5.10.0 round 2 (F-311e3be9, F-9dec388c, F-9e4f9a59): a file a command deletes is charged however long the walk takes; caches under a linked node_modules are not changes; a blocked command opens no window")
def _(d):
    O = _oc15(); p, recs = _setup15(d); ws = recs["r1"]["payload"]
    write(p, "src/gone.py", "z = 1\n"); write(p, "node_modules/pkg/index.js", "x\n")
    O.call_start(p, "r1", "w0"); O.call_end(p, "r1", "w0")
    O.call_start(p, "r1", "w1"); (p / "src/gone.py").unlink()
    real = O.watched; O.watched = lambda r: (time.sleep(0.3), real(r))[1]
    try: found = O.call_end(p, "r1", "w1")
    finally: O.watched = real
    assert any(a == "r1" and "gone.py" in (pth or "") for a, pth, w in found), ("a deletion during the walk", found)
    O.call_start(p, "r1", "w2"); write(p, "node_modules/.vite/deps/x.js", "y\n"); found = O.call_end(p, "r1", "w2")
    assert not any("node_modules" in (pth or "") for a, pth, w in found), found
    s, out = _call15(p, "r1", f"cd {ws} && eval ls", "w3"); assert "deny" in out
    time.sleep(0.05); write(p, "src/late.py", "q\n"); time.sleep(0.05)
    found = O.sweep(p)
    assert not any(a == "r1" for a, pth, w in found), ("the blocked command had no window", found)

@test("5.10.0 round 2 (F-702ecf38, F-c06b937b, F-35db7c2e, F-ba44f2df) and ruling 53's command data: grep function passes; git listing subcommands with a writing option, git reflog expire, git --output, uniq or xxd writing outside, and a command unknown to commands.json are blocked; git -C .. from a subfolder of the copy passes; a variable set to a known program runs")
def _(d):
    A = _al15(); ws = d / "p/.critic/scratch/r1/payload"; (ws / "src").mkdir(parents=True); notes = str(ws.parent / "notes"); ws = str(ws)
    for c in ["grep -n function src/a.js", "cd src && git -C .. log -3", "P=python3; $P -I app.py 1 2", "uniq src/a.txt ../notes/u.txt", "tar -tf ../notes/x.tar", "command -v node"]:
        assert A.problem(f"cd {ws} && {c}", ws, notes) is None, (c, A.problem(f"cd {ws} && {c}", ws, notes))
    for c in ["git branch --list -D main", "git tag -l -d v1", "git reflog expire --all", "git log --output=/tmp/x.txt", "uniq src/a.txt /tmp/out.txt",
              "xxd -r src/a.hex /tmp/x.bin", "pg_isready", "claude -p hi", "tar -xf ../notes/x.tar", "command kill 1", "curl -s example.test"]:
        assert A.problem(f"cd {ws} && {c}", ws, notes), c
    J = json.loads((HERE / "hooks/commands.json").read_text(encoding="utf-8"))
    assert set(J["accepted"]) <= set(J["classes"]) and all(e["c"] in J["classes"] for e in J["commands"].values()), "every class named in the data is described"

@test("5.10.0 round 2 (F-3b41c013): the stop hook's own stamp on a review is recorded as a known write, through check_contract.py itself")
def _(d):
    write(d, "src/app.js", APP); write(d, ".critic/ledger.json", json.dumps({"started_at": time.time() - 5}))
    run(S / "critic_proctor.py", "begin", cwd=d) if (S / "critic_proctor.py").is_file() else None
    claim_for(d, "r2", "A"); write(d, ".critic/reviews/review-A.json", json.dumps({"findings": [TAX9]}))
    _stop9(d, "r2", "A", ["src/app.js"])
    O = _oc15(); okay = O._known(d)
    f = str(d / ".critic/reviews/review-A.json")
    import hashlib
    assert f in okay and hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() in okay[f], ("the stamped content is a known write", list(okay))

@test("5.10.0 round 3 (F-9707272d, F-65cdbe66, F-f9ad4b76, F-9fada6f5, F-d55692bc, F-b5a681a6, F-78964562, F-6e504768, F-d782db3c): an apostrophe never hides a $( ); computed write targets, xargs into a writer, sudo, doas and exec, tar with a stray t, bundled or shortened sort -o, a shell reading its input, git -c that runs a program, and sed w, yq -i and split writing outside are blocked; an option's value is never read as npm's subcommand")
def _(d):
    A = _al15(); ws = str(d / "p/.critic/scratch/r1/payload"); notes = str(d / "p/.critic/scratch/r1/notes")
    ok = ["npm --loglevel silent test", "git -c core.pager=cat diff", "git -c color.ui=never log -1", "tar tf ../notes/x.tar", "tar -tvf ../notes/x.tar",
          "bash ../notes/s.sh", "bash ../notes/s.sh < src/in.txt", "sed -n 1,5p src/a.js", "sed 's/w/x/' src/a.js", "sort -u src/a.txt", "yq '.a' src/x.yml",
          "split -l 1 src/a ../notes/pre", "find . -name '*.js' | xargs wc -l", "echo \"it's $(ls src)\""]
    for c in ok: assert A.problem(f"cd {ws} && {c}", ws, notes) is None, (c, A.problem(f"cd {ws} && {c}", ws, notes))
    bad = {"echo \"it's $(netcat -s example.test) don't\"": "netcat", "echo \"it's\" \"$(sudo ls)\" \"don't\"": "sudo", "cp src/a \"$(echo /tmp)/x\"": "command's output", "echo /tmp/x | xargs touch": "xargs",
           "sudo cat src/a": "sudo", "doas ls": "doas", "exec ls": "exec", "npm --prefix ../x install y": "npm --prefix ../x install y", "tar xf ../notes/a.tar t": "tar only",
           "sort -uo /tmp/x src/a": "sort -o", "sort --out=/tmp/x src/a": "sort --output", "bash <<'E'\nls\nE": "its input", "echo ls | sh": "its input",
           "sh < ../notes/x": "its input", "bash -s": "its input", "git -c core.fsmonitor=../notes/x status": "core.fsmonitor", "git -c core.pager=../notes/x diff": "core.pager",
           "sed 'w /tmp/x' src/a": "/tmp/x", "sed 's/a/b/w /tmp/y' src/a": "/tmp/y", "yq -i '.a=1' /tmp/x.yml": "/tmp/x.yml", "split -l 1 src/a /tmp/pre": "/tmp/pre"}
    for c, why_has in bad.items():
        why = A.problem(f"cd {ws} && {c}", ws, notes)
        assert why and why_has in why, (c, why)

@test("5.10.0 round 3 (F-37b2b147): a call whose start hook never ran (it failed open, or timed out on a slow PC) cuts no one")
def _(d):
    O = _oc15(); p, recs = _setup15(d)
    O.call_start(p, "r1", "a0"); O.call_end(p, "r1", "a0")
    found = O.call_end(p, "r1", "no-start")
    assert not any(a == "r1" for a, pth, w in found), ("a missing start is no tampering", found)

@test("5.10.0 round 3 (F-88a7850b): a known write matches the walk's path whatever spelling it was recorded under")
def _(d):
    O = _oc15(); p, recs = _setup15(d); f = p / ".critic/reviews/review-Z.json"
    O.call_start(p, "r1", "a0"); O.call_end(p, "r1", "a0")
    O.call_start(p, "r1", "a1"); time.sleep(0.05); f.write_text("{}", encoding="utf-8")
    O.known(p, str(p / ".critic" / "reviews" / ".." / "reviews" / "review-Z.json")); found = O.call_end(p, "r1", "a1")
    assert not any("review-Z" in (pth or "") for a, pth, w in found), ("the same file, spelled another way", found)

@test("5.10.0 round 3 (F-87045c9b): Curmudgeon's own ledger save and a watch build's top-level output during a reviewer's command are not the reviewer's")
def _(d):
    O = _oc15(); p, recs = _setup15(d); env = {**os.environ, "CRITIC_ROOT": str(p)}
    assert run(S / "critic_ledger.py", "start", "review", cwd=p, env=env).returncode == 0
    O.call_start(p, "r1", "a0"); O.call_end(p, "r1", "a0")
    O.call_start(p, "r1", "a1"); time.sleep(0.05); led = (p / ".critic/ledger.json").read_bytes()
    r = run(S / "critic_ledger.py", "cost", "5", "lead", cwd=p, env=env); assert r.returncode == 0 and (p / ".critic/ledger.json").read_bytes() != led, r.stderr
    found = O.call_end(p, "r1", "a1")
    assert not any(a == "r1" for a, pth, w in found), ("Curmudgeon's own ledger save", found)
    O.call_start(p, "r1", "a2"); time.sleep(0.05); write(p, "dist/app.js", "built\n"); found = O.call_end(p, "r1", "a2")
    assert not any(a == "r1" for a, pth, w in found), ("a watch build's output", found)

@test("5.10.0 round 3 (F-6ecf9c94): past the file limit every folder is watched alone and no file is, so walk order decides nothing")
def _(d):
    O = _oc15(); q = d / "big"; [write(q, f"{s_}/f{k}.py", "x\n") for s_ in ("a", "b") for k in range(4)]
    old = O.LIMIT; O.LIMIT = 5
    try: snap, partial = O.watched(q)
    finally: O.LIMIT = old
    assert partial and not any(os.path.isfile(k) and k.startswith(str(q)) for k in snap) and str(q / "a") in snap and str(q / "b") in snap, sorted(snap)

@test("5.10.0 round 3 (F-c5891dd1): a reviewer's own claimed review, written from its shell while another reviewer's call ran, is never listed")
def _(d):
    O = _oc15(); p, recs = _setup15(d, ("r1", "r2")); claim_for(p, "r2", "A"); f = p / ".critic/reviews/review-A.json"
    O.call_start(p, "r1", "a0"); O.call_end(p, "r1", "a0")
    O.call_start(p, "r1", "b1"); O.call_start(p, "r2", "b2"); time.sleep(0.05); f.write_text('{"findings": []}', encoding="utf-8")
    old = O.PENDING_S; O.PENDING_S = 0
    try:
        found = O.call_end(p, "r2", "b2", own=[f]) + O.call_end(p, "r1", "b1"); time.sleep(0.05); O.call_start(p, "r1", "b3"); found += O.call_end(p, "r1", "b3")
    finally: O.PENDING_S = old
    assert not any("review-A" in (pth or "") for a, pth, w in found), found

@test("ruling 55, the A/B harness: --plugin-b runs each plugin arm again with the second build, the two builds' runs alternate, and --keep-records keeps a run's .critic records but never the agents' private copies", repo=True)
def _(d):
    sys.path.insert(0, str(HERE.parent / "eval")); import importlib; dm = importlib.import_module("deathmatch"); importlib.reload(dm)
    w = d / "work"; write(w, ".critic/counts.md", "Counts"); write(w, ".critic/reviews/review-A.json", "{}"); write(w, ".critic/scratch/r1/payload/app.js", "x"); write(w, ".critic/scratch/r1/notes/n.txt", "n")
    td = d / "td"; td.mkdir(); dm.keep_records(w, td)
    assert (td / "critic/counts.md").is_file() and (td / "critic/reviews/review-A.json").is_file() and (td / "critic/scratch/r1/notes/n.txt").is_file(), "the records are kept"
    assert not (td / "critic/scratch/r1/payload").exists(), "the private copy is the task itself: never kept"
    A, B = {"id": "curmudgeon"}, {"id": "curmudgeon-b"}; t1, t2 = {"id": "suite1"}, {"id": "suite2"}
    jobs = [(A, t1, 0), (A, t2, 0), (A, t1, 1), (B, t1, 0), (B, t2, 0), (B, t1, 1)]
    order = [(a["id"], t["id"], k) for a, t, k in dm.interleave(jobs)]
    assert order == [("curmudgeon", "suite1", 0), ("curmudgeon-b", "suite1", 0), ("curmudgeon", "suite2", 0), ("curmudgeon-b", "suite2", 0), ("curmudgeon", "suite1", 1), ("curmudgeon-b", "suite1", 1)], order
    seen = []
    real = dm.subprocess.run
    class R: stdout = '{"result": "", "usage": {}}'; returncode = 0; stderr = ""
    dm.subprocess.run = lambda cmd, **k: (seen.append(cmd), R())[1]
    try:
        arm = {**[x for x in dm.load_cfg()["arms"] if x["id"] == "curmudgeon"][0], "id": "curmudgeon-b", "_plugin": str(d / "buildB")}
        (d / "out").mkdir(); dm.one_run(arm, w, d / "out", None)
    finally: dm.subprocess.run = real
    assert str(d / "buildB") in seen[0] and str(dm.PLUGIN) not in seen[0], ("the second build is the one loaded", seen[0])
