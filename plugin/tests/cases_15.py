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
