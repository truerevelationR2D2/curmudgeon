"""Curmudgeon's script tests, part 11: release 5.9.0, the reviewers' standard (03 §5.57 item 44). Each reviewer claims
its review with the token its brief holds; writing outside its own space, touching settings or interfering with the
run cuts its review; a read the guard blocks is only listed. Run plugin/tests/run_tests.py, which defines the helpers
and runs every part. Not runnable on its own. Each test here failed on 5.8.1 (main at 9876db7)."""

def _c11(): sys.path.insert(0, str(HERE / "hooks")); import importlib, conduct; importlib.reload(conduct); return conduct

def _gs11(p, path, aid="r1", role="reviewer"):
    return run(H / "guard_state.py", cwd=p, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "x"}, "cwd": str(p), "agent_type": f"curmudgeon:curmudgeon-{role}", "agent_id": aid, "hook_event_name": "PreToolUse"})).stdout

def _proj11(d):
    p = d / "proj"; write(p, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=p)
    return p

def _tok11(p, letter):
    m = re.search(rf"critic_proctor\.py'?\s+claim {letter} ([0-9a-f]{{12}})", (p / f".critic/briefs/brief-{letter}.md").read_text(encoding="utf-8"))
    assert m, f"brief-{letter} has no claim line"; return m.group(1)

@test("5.9.0: each brief holds a claim command with its own token; the Bash guard records the claim, and refuses a wrong token, a letter another reviewer holds and a second letter")
def _(d):
    p = _proj11(d); C = _c11()
    toks = {x: _tok11(p, x) for x in "ABC"}
    assert len(set(toks.values())) == 3, toks
    for x in "ABC":
        for y in "ABC":
            if y != x: assert toks[y] not in (p / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8"), (x, y)
    ws1 = _ws(p, "r1")["payload"]; ws2 = _ws(p, "r2")["payload"]
    claim = lambda aid, ws, letter, tok: _rg(p, "Bash", aid=aid, command=f"cd {ws} && python3 {S}/critic_proctor.py claim {letter} {tok}")
    assert "deny" in claim("r1", ws1, "A", toks["B"]), "a wrong token"
    assert C.claims(p) == {}
    assert "deny" not in claim("r1", ws1, "A", toks["A"])
    assert C.claims(p) == {"r1": "review-A.json"}
    assert "deny" in claim("r2", ws2, "A", toks["A"]), "a letter another reviewer holds"
    assert "deny" in claim("r1", ws1, "B", toks["B"]), "a second letter"
    assert "deny" not in claim("r2", ws2, "B", toks["B"])
    assert C.claims(p) == {"r1": "review-A.json", "r2": "review-B.json"}
    assert len(C.listed(p, "r1", "blocked")) == 2 and C.listed(p, "r1", "cut") == [], "refused claims are listed, never cut"
    r = run(S / "critic_proctor.py", "claim", "A", toks["A"], cwd=pathlib.Path(ws1), env={"CRITIC_ROOT": ""})
    assert r.returncode == 0 and "claimed review-A.json" in r.stdout, r.stdout + r.stderr
    toks2 = (run(S / "critic_brief.py", cwd=p), {x: _tok11(p, x) for x in "ABC"})[1]
    assert toks2 == toks, "the same briefs written again keep their tokens"

@test("5.9.0: a reviewer writes its review only after claiming it, only the one it claimed, and only in its copy, notes and that review; anything else cuts it")
def _(d):
    p = _proj11(d); C = _c11(); rec = _ws(p, "r1")
    assert "deny" in _gs11(p, p / ".critic/reviews/review-A.json") and C.listed(p, "r1", "cut") == [], "no review before the claim, and no cut for it"
    claim_for(p, "r1", "A")
    for ok in (p / ".critic/reviews/review-A.json", pathlib.Path(rec["notes"]) / "probe.js", pathlib.Path(rec["payload"]) / "src/probe.js"):
        assert "deny" not in _gs11(p, ok), ok
    assert C.listed(p, "r1", "cut") == []
    bad = [p / ".critic/reviews/review-B.json", p / ".critic/briefs/brief-B.md", p / ".critic/proctor/claims/r1.json", p / "src/app.js",
           d / "elsewhere.txt", pathlib.Path(rec["notes"]) / "CLAUDE.md", pathlib.Path(rec["payload"]) / "CLAUDE.md", p / ".claude/settings.json"]
    for b in bad:
        out = _gs11(p, b); assert "deny" in out and "cut" in out, (b, out)
    assert len(C.listed(p, "r1", "cut")) == len(bad), C.listed(p, "r1", "cut")

@test("5.9.0: a reviewer's shell command that writes outside its space or stops processes cuts it; writes in its notes, 2>/dev/null and >&2 don't")
def _(d):
    p = _proj11(d); C = _c11(); rec = _ws(p, "r1"); ws = rec["payload"]
    for cmd in (f"cd {ws} && echo x > {p}/.critic/reviews/review-B.json", f"cd {ws} && cp src/app.js ../../../reviews/review-B.json",
                f"cd {ws} && pkill -f claude", f"cd {ws} && touch {p}/src/new.js", f"cd {ws} && cd ../notes && echo hi > CLAUDE.md"):
        out = _rg(p, "Bash", command=cmd); assert "deny" in out and "cut" in out, (cmd, out)
    n = len(C.listed(p, "r1", "cut")); assert n == 5, C.listed(p, "r1", "cut")
    for cmd in (f"cd {ws} && node -e 1 > ../notes/out.txt 2>/dev/null", f"cd {ws} && cd ../notes && mkdir -p t && cp ../payload/src/app.js t/ && echo done >&2",
                f"cd {ws} && grep -rn innerHTML src | tee ../notes/hits.txt"):
        out = _rg(p, "Bash", command=cmd); assert "cut" not in out, (cmd, out)  # the tripwire may still refuse a cd out of the copy; that is listed, never cut
    assert len(C.listed(p, "r1", "cut")) == n
    _rg(p, "Bash", command=f"ls {p}/.critic/reviews")
    assert C.listed(p, "r1", "blocked") and len(C.listed(p, "r1", "cut")) == n, "a blocked read is listed, never cut"

@test("5.9.0: the merge voids a review whose claiming agent broke the standard, keeps its findings only for blind verification, and lists blocked reads outside the DEGRADED line")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for aid, x in (("ra", "A"), ("rb", "B"), ("rc", "C")): claim_for(d, aid, x)
    C = _c11(); C.note(d, "rb", "wrote .critic/reviews/review-A.json, which is not the review it claimed (review-B.json)", "cut"); C.note(d, "rc", "Bash: a command that doesn't start in your workspace", "blocked")
    other = finding(impact="High", file="src/app.js", line=4, quote="const price = total * 1.0825;", title="Tax rate hard-coded into the price", category="correctness", evidence="src/app.js:4", failing_case="a 7% county gets 8.25%")
    T = _tally3(d, [finding()], [finding(), other], [finding()])
    deg = " ".join(T["degraded"])
    assert "review cut: review-B.json" in deg and "broke the reviewers' standard" in deg, T["degraded"]
    assert T["reviewers"] == 2, T["reviewers"]
    assert any(f.get("voided_only") and f["title"] == other["title"] for f in T["contested"]), ("its own finding goes to blind verification", [(k, [x.get("title") for x in T[k]]) for k in ("kept", "contested", "dropped")])
    assert "blocked" not in deg.lower(), T["degraded"]  # 5.9.0 blind round D2: the old assert could never fail
    assert T["blocked"] == {"review-C.json": [1, "Bash: a command that doesn't start in your workspace"]}, T["blocked"]

@test("5.9.0: the reviewer's instructions spell out the standard before it starts: claim first, where it may write, and what gets a review cut")
def _(d):
    t = (HERE / "agents/curmudgeon-reviewer.md").read_text(encoding="utf-8")
    sec = t.split("**The reviewers' standard.**", 1)[1].split("\n\n", 1)[0]
    for must in ("claim your review", "only the one you claimed", "your copy", "notes folder", "**cut**", "write anywhere else", "settings or instructions", "stop or signal processes", "interfere", "doesn't cut your review"):
        assert must in sec, must

@test("5.9.0 blind round: only a command named kill, pkill or killall cuts; the word in a probe's here-document, a quoted string or a grep pattern doesn't, nor a fake home's .claude/ in the notes")
def _(d):
    C = _c11(); root = str(d / "proj"); me = "r1"; ws = f"{root}/.critic/scratch/{me}/payload"
    honest = [f"cd {ws} && mkdir -p ../notes && cat > ../notes/p1.py <<'EOF'\nimport os\nos.system('kill -0 1')  # kill; pkill x\nEOF\npython3 ../notes/p1.py",
              f"cd {ws} && grep -rn kill src", f"cd {ws} && grep -n \"will kill the run\" plugin/hooks/conduct.py",
              f"cd {ws} && python3 -c \"print('pkill -f x')\"", f"cd {ws} && mkdir -p ../notes/fakehome/.claude/projects/p && echo {{}} > ../notes/fakehome/.claude/settings.json"]
    for c in honest: assert C.bash_cut(c, root, me, ws) is None, c
    for c in (f"cd {ws} && kill 123", f"cd {ws} && sleep 1; pkill -f claude", f"cd {ws} && true && killall node", f"cd {ws} && env X=1 kill -9 1"):
        assert C.bash_cut(c, root, me, ws), c

@test("5.9.0 blind round C2, C3, C4, C5, C8: a newline ends a command; a quoted '>' is no redirect; a project inside a .claude folder isn't settings; a shell write to its own claimed review is allowed; a temp folder outside is cut by the shell as by the Write tool")
def _(d):
    C = _c11(); root = d / "repo/.claude/worktrees/feat"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload")
    write(root, "src/app.js", APP); (root / ".critic").mkdir(exist_ok=True)
    assert C.bash_cut(f"cd {ws} && mkdir -p ../notes/t\npython3 {pathlib.Path.home()}/.claude/plugins/x/ast_view.py src/app.js", str(root), me, ws) is None, "C2"
    assert C.bash_cut(f"cd {ws} && grep '>' CLAUDE.md", str(root), me, ws) is None, "C8"
    assert C.bash_cut(f"cd {ws} && touch probe.js && echo x | tee ../notes/hits.txt", str(root), me, ws) is None, "C3"
    claim_for(root, me, "B")
    assert C.bash_cut(f"cd {ws} && echo '{{}}' > {root}/.critic/reviews/review-B.json", str(root), me, ws) is None, "C4"
    assert C.bash_cut(f"cd {ws} && echo '{{}}' > {root}/.critic/reviews/review-A.json", str(root), me, ws), "another review"
    assert C.bash_cut(f"cd {ws} && echo x > /tmp/scratch-probe.txt", str(root), me, ws), "C5: a temp folder outside"
    assert C.bash_cut(f"cd {ws} && echo hi > ../notes/CLAUDE.md", str(root), me, ws), "an instructions file in its own folder"

@test("5.9.0 blind round D1: each writer the shell rule knows is caught on its own (mv, cp, tee, rm, touch, truncate, mkdir, sed -i, dd of=, chmod, chown, ln, a redirect, >> and Claude Code's folder)")
def _(d):
    C = _c11(); root = str(d / "proj"); me = "r1"; ws = f"{root}/.critic/scratch/r1/payload"; out = f"{root}/src/out.js"
    for c in (f"mv a.js {out}", f"cp a.js {out}", f"echo x | tee {out}", f"rm {out}", f"touch {out}", f"truncate -s 0 {out}", f"mkdir {root}/src/newdir",
              f"sed -i s/a/b/ {out}", f"dd if=a.js of={out}", f"chmod 777 {out}", f"chown me {out}", f"ln -s a.js {out}", f"echo x > {out}", f"echo x >> {out}",
              f"echo x > {pathlib.Path.home()}/.claude/settings.json"):
        assert C.bash_cut(f"cd {ws} && {c}", root, me, ws), c
    assert "Claude Code's or Curmudgeon's own folder" in C.bash_cut(f"cd {ws} && echo x > {pathlib.Path.home()}/.claude/x", root, me, ws)

@test("5.9.0 blind round C6, D3: a claim lapses when its reviewer stops, so a replacement can claim the letter; claims and cuts from before this round started are ignored")
def _(d):
    p = _proj11(d); C = _c11(); tok = _tok11(p, "A")
    assert C.claim(p, "a1", "A", tok) is None and C.claim(p, "a2", "A", tok)
    write(p, ".critic/stops/a1.json", json.dumps({"review": "review-A.json", "at": time.time()}))
    assert C.claim(p, "a2", "A", tok) is None, "the stopped reviewer's letter is free"
    L = json.loads((p / ".critic/ledger.json").read_text(encoding="utf-8")); start = float(L["started_at"])
    write(p, ".critic/proctor/claims/old.json", json.dumps({"review": "review-C.json", "at": start - 100}))
    write(p, ".critic/proctor/cut/old.jsonl", json.dumps({"at": start - 100, "why": "an earlier round"}) + "\n")
    assert "old" not in C.claims(p) and C.listed(p, "old", "cut") == [], "earlier rounds never count"
