"""Curmudgeon's script tests, part 6: batch 4 of the combined review of 29 Oct 2026, cost, process and platforms (03
§5.56, items 22-28). Run plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its
own. Each test here failed on the code before the change."""

@test("§5.56 item 22: one PreToolUse process runs the blindness guard and the stuck refusal; calls that aren't Curmudgeon's return at once with no output")
def _(d):
    hooks = json.loads((H / "hooks.json").read_text())["hooks"]
    cmds = [h["command"] for ev in ("PreToolUse", "PostToolUse") for m in hooks.get(ev, []) for h in m.get("hooks", [])]
    assert any("pre_tool.py" in c for c in cmds) and any("post_tool.py" in c for c in cmds), cmds
    assert not any(re.search(r"read_guard\.py|stuck\.py", c) for c in cmds), "the two old hooks are replaced, not doubled"
    write(d, ".critic/reviews/review-B.json", "[]"); (d / ".critic/scratch/me").mkdir(parents=True)
    ask = lambda agent, tool="Read", **ti: run(H / "pre_tool.py", cwd=d, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(d), "agent_type": agent, "agent_id": "me"})).stdout
    assert "deny" in ask("curmudgeon:curmudgeon-reviewer", file_path=str(d / ".critic/reviews/review-B.json"))
    assert ask("", file_path=str(d / ".critic/reviews/review-B.json")) == "" and ask("general-purpose", file_path="x") == "", "the user's own calls and other agents: nothing"
    write(d, ".critic/ledger.json", json.dumps({"started_at": time.time()}))
    assert "deny" in ask("", tool="Agent", subagent_type="fork"), "the fork check still sees the main session's Agent calls"

@test("§5.56 item 23: every design ruling the shipped code cites is in plugin/RULINGS.md, so a reviewer can look it up")
def _(d):
    cited = set()
    for f in HERE.rglob("*.py"):
        if "tests" not in f.parts: cited |= set(re.findall(r"§(5\.\d+|2)\b", f.read_text(encoding="utf-8", errors="replace")))
    idx = (HERE / "RULINGS.md").read_text()
    missing = sorted(c for c in cited if not re.search(rf"^\| §{re.escape(c)}\b", idx, re.M))
    assert cited and not missing, missing

@test("§5.56 item 24: the eval's list of unmatched findings is scratch state kept outside the source tree")
def _(d):
    src = (HERE.parent / "eval" / "score.py").read_text()
    assert ".last-unmatched.json" not in src and "CURMUDGEON_STATE_DIR" in src, "score.py writes its scratch list beside itself"

@test("§5.56 item 28: CI pins the v7 actions by commit and tests Python 3.9 to 3.14, with Windows and macOS runs")
def _(d):
    ci = (HERE.parent / ".github" / "workflows" / "ci.yml").read_text()
    for sha in ("3d3c42e5aac5ba805825da76410c181273ba90b1", "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", "949feb2413d6458794dcd2491c4babbbce0c15c1"):
        assert sha in ci, sha
    assert re.search(r'"3\.14"|3\.14\b', ci) and "macos" in ci and "Windows" in ci, "3.14, macOS and Windows"
    assert not re.search(r"uses:\s*actions/[\w-]+@v\d", ci), "every action is pinned by commit, not by tag"
