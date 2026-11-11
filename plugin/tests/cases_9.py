"""Curmudgeon's script tests, part 9: release 5.5.0 (03 §5.57 items 34 to 36): the approved backlog items, N5 and the
proctor. Run plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its own. Each
test here failed on 5.4.2 (main at cf5d1ca) before its fix."""

G9 = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]

def _ledger9(d): return json.loads((d / ".critic/ledger.json").read_text(encoding="utf-8"))

@test("5.5.0 P15 carry-over: a run stopped and begun again on the same files keeps the outside answer it had loaded; other files, or a run that wasn't stopped, don't")
def _(d):
    write(d, "src/app.js", APP); write(d, "src/b.js", "const b = 1;\n")
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    time.sleep(0.05); ans = write(d, ".critic/outside/outside-review.json", json.dumps([finding(impact="High")]))
    run(S / "critic_ledger.py", "abort", "owner said stop", cwd=d); time.sleep(0.05)
    r = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    assert r.returncode == 0 and "carried over the outside reviewer's answer" in r.stdout, r.stdout[-500:] + r.stderr
    assert ans.stat().st_mtime >= _ledger9(d)["started_at"], "the answer counts as loaded for the new run"
    # not stopped: a finished-or-running run is not carried
    time.sleep(0.05); r = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    assert "carried over" not in r.stdout and ans.stat().st_mtime < _ledger9(d)["started_at"], r.stdout[-300:]
    # stopped, but other files
    os.utime(ans, None); run(S / "critic_ledger.py", "abort", cwd=d); time.sleep(0.05)
    r = run(S / "critic_run.py", "begin", "--files", "src/b.js", "--tier", "lite", cwd=d)
    assert "carried over" not in r.stdout, r.stdout[-300:]

@test("5.5.0 stopped runs and the hooks: after critic_ledger.py abort, the hooks no longer treat the run as active")
def _(d):
    sys.path.insert(0, str(H)); import importlib, read_guard; importlib.reload(read_guard)
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    assert read_guard.run_active(d), "a begun run is active"
    run(S / "critic_ledger.py", "abort", "owner said stop", cwd=d)
    assert not read_guard.run_active(d), "a stopped run is not active"
    ev = {"tool_name": "Agent", "tool_input": {"subagent_type": "curmudgeon:curmudgeon-reviewer", "prompt": "review it however you like"}, "cwd": str(d)}
    out = run(H / "read_guard.py", cwd=d, stdin=json.dumps(ev)).stdout
    assert "deny" not in out, ("a stopped run no longer demands the brief", out)

@test("5.5.0 R4: the plan mentions the tier the owner chose last time for the same files, never a ledger that came with the code, and never applies it by itself")
def _(d):
    write(d, "a.py", "x = 1\n"); write(d, "b.py", "y = 2\n")
    run(S / "critic_run.py", "begin", "--files", "a.py", "--tier", "full", cwd=d)
    r = run(S / "critic_run.py", "plan", "--files", "a.py", cwd=d)
    assert "last time: you chose the full tier for these same files" in r.stdout and "plan: trivial tier" in r.stdout, r.stdout
    assert "last time" not in run(S / "critic_run.py", "plan", "--files", "b.py", cwd=d).stdout, "other files"
    assert "last time" not in run(S / "critic_run.py", "plan", "--files", "a.py", "--tier", "lite", cwd=d).stdout, "the owner already chose"
    e = d / "e"; write(e, "a.py", "x = 1\n"); run(S / "critic_run.py", "begin", "--files", "a.py", cwd=e)
    assert "last time" not in run(S / "critic_run.py", "plan", "--files", "a.py", cwd=e).stdout, "the plan's own choice is not the owner's"
    L = _ledger9(e); sys.path.insert(0, str(S)); import critic_findings
    L["tier_choices"] = {critic_findings.files_key(["a.py"]): {"tier": "full", "run": 1}}
    (e / ".critic/ledger.json").write_text(json.dumps(L), encoding="utf-8")  # not saved by critic_ledger.py: like a shipped one
    assert "last time" not in run(S / "critic_run.py", "plan", "--files", "a.py", cwd=e).stdout, "a ledger that came with the code is never read for it"

@test("5.5.0 leftover copies: begin removes private copies that earlier agents' stop hooks left behind, and says so")
def _(d):
    write(d, "a.py", "x = 1\n"); write(d, ".critic/scratch/agent-old/payload/a.py", "x = 1\n")
    r = run(S / "critic_run.py", "begin", "--files", "a.py", "--tier", "lite", cwd=d)
    assert "removed 1 private copy" in r.stdout and not (d / ".critic/scratch/agent-old/payload").exists(), r.stdout[-400:]
    assert "removed" not in run(S / "critic_run.py", "begin", "--files", "a.py", "--tier", "lite", cwd=d).stdout, "nothing left: nothing said"

@test("5.5.0 blindness reasons: the counts say whether the stop hook never recorded a reviewer or recorded that it had no private copy")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    for k in "ABC": write(d, f".critic/reviews/review-{k}.json", "[]")
    write(d, ".critic/stops/agent-A.json", json.dumps({"review": "review-A.json", "workspace": True, "at": time.time()}))
    write(d, ".critic/stops/agent-B.json", json.dumps({"review": "review-B.json", "workspace": False, "at": time.time()}))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{k}.json" for k in "ABC"], "--no-scan", cwd=d); run(S / "critic_merge.py", "apply", cwd=d)
    c = (d / ".critic/counts.md").read_text(encoding="utf-8")
    assert "review-B.json (its stop record says the agent had no private copy" in c, c[:600]
    assert "review-C.json (no stop record" in c and "for review-A.json" not in c and "review-A.json, " not in c, c[:600]

@test("5.5.0 round-2 pointer: after critic_ledger.py round the next step names the round's blind re-review, and the runner asks for the round's own briefs before starting reviewers")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    write(d, ".critic/reviews/review-A.json", "[]")
    r = run(S / "critic_ledger.py", "round", cwd=d)
    assert "review round 2 of 3" in r.stdout and "critic_run.py status" in r.stdout, r.stdout
    s = run(S / "critic_run.py", "status", cwd=d).stdout
    assert "briefs aren't written yet" in s and "critic_brief.py" in s and "critic_map.py" in s and "start 1 curmudgeon" not in s, s
    run(S / "critic_brief.py", "--letters", "A", cwd=d)
    s = run(S / "critic_run.py", "status", cwd=d).stdout
    assert "start 1 curmudgeon:curmudgeon-reviewer" in s, s

@test("5.5.0 outside-brief hand-over: critic_outside.py brief prints its own line telling the lead to give the user the brief now")
def _(d):
    write(d, "src/app.js", APP)
    subprocess.run(["git", "init", "-q"], cwd=d); subprocess.run(["git", "add", "-A"], cwd=d); subprocess.run(G9 + ["commit", "-qm", "x"], cwd=d)
    run(S / "critic_map.py", "--files", "src/app.js", cwd=d); run(S / "critic_ledger.py", "start", "review", cwd=d)
    r = run(S / "critic_outside.py", "brief", cwd=d); assert r.returncode == 0, r.stderr
    assert re.search(r"^next: give the user \.critic/outside/brief\.md now", r.stdout, re.M), r.stdout
