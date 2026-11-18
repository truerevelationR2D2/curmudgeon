"""Curmudgeon's script tests, part 13: release 5.9.2. Run plugin/tests/run_tests.py, which defines the helpers and runs
every part. Not runnable on its own. Each test here failed on 5.9.1 (main at a539002)."""

@test("5.9.2 (03 §5.57 item 48, the Qodo replay's #26): a reviewer's mkdir of a folder that already exists, or of a folder on the way to its own claimed review, is no write; a new folder anywhere else still cuts it")
def _(d):
    C = _c11()
    root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload")
    write(root, "src/app.js", APP); (root / ".critic/scratch/r1/payload").mkdir(parents=True); (root / ".critic/reviews").mkdir(parents=True)
    claim_for(root, me, "C")
    assert C.bash_cut(f"cd {ws} && mkdir -p ../../../reviews 2>/dev/null; python3 - <<'EOF'\nprint(1)\nEOF", str(root), me, ws) is None, "#26: the reviews folder already exists"
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/reviews", str(root), me, ws) is None, "the same folder by its full path"
    assert C.bash_cut(f"cd {ws} && mkdir {root}/src", str(root), me, ws) is None, "any folder that already exists changes nothing"
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/reviews/review-A.json", str(root), me, ws), "a folder named for another reviewer's review would block its save"
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/src/newdir", str(root), me, ws), "a new folder in the project"
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/proctor/x", str(root), me, ws), "a new folder among Curmudgeon's records"
    assert C.bash_cut(f"cd {ws} && touch {root}/.critic/reviews", str(root), me, ws), "touch is still a write, existing or not"
    (root / ".critic/reviews").rmdir()
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/reviews", str(root), me, ws) is None, "not there yet, but on the way to its own claimed review"
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/other", str(root), me, ws), "not on the way to its review"
    claim = root / ".critic/proctor/claims" / f"{me}.json"; claim.unlink()
    assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.critic/reviews", str(root), me, ws), "with no claim there is no review to make a folder for"

@test("5.9.2 (hook timeouts on a slow Windows machine): the guards that run on every tool call get 60 seconds, not 10, and a hook with a kept Python starts Python once, not twice; a project file never stands in for a hook's module")
def _(d):
    import shutil
    hooks = json.loads((H / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    limits = {h["command"].rsplit("/", 1)[-1].rstrip('"'): h.get("timeout") for gs in hooks.values() for g in gs for h in g["hooks"]}
    for name in ("guard_state.py", "pre_tool.py", "post_tool.py"): assert limits[name] >= 60, (name, limits[name])
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    fake = d / "bin"; fake.mkdir(); log = d / "starts.txt"
    p = fake / "python3"; p.write_text(f'#!/bin/sh\necho x >> "{log.as_posix()}"\nexec "{pathlib.Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8"); p.chmod(0o755)
    data = d / "data"; data.mkdir(); (data / "python").write_text("python3\n", encoding="utf-8")
    hooks_dir = d / "hk"; hooks_dir.mkdir()
    (hooks_dir / "helper.py").write_text("WHO = 'hook folder'\n", encoding="utf-8")
    hook = hooks_dir / "hook.py"; hook.write_text("import sys, helper\nprint(helper.WHO, sys.argv[1:], sys.stdin.read())\n", encoding="utf-8")
    proj = d / "proj"; proj.mkdir(); (proj / "helper.py").write_text("WHO = 'project'\n", encoding="utf-8")
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}", CLAUDE_PLUGIN_DATA=str(data))
    r = subprocess.run([sh, str(H / "run.sh"), str(hook), "x"], input="in", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=proj)
    assert r.returncode == 0 and r.stdout.strip() == "hook folder ['x'] in", (r.returncode, r.stdout, r.stderr)
    assert log.read_text(encoding="utf-8").count("x") == 1, ("one Python start per hook", log.read_text(encoding="utf-8"))

@test("5.9.2 (03 §5.57 item 49): a test that reads the repository around the plugin is skipped, not failed, where only the plugin folder is present, and in CI the repository is always found, so none of them is ever skipped there")
def _(d):
    if os.environ.get("GITHUB_ACTIONS") == "true": assert IN_REPO, "CI checks out the whole repository: a repository test must never be skipped there"
    if IN_REPO:
        assert (REPO / "eval" / "score.py").is_file() and (REPO / "CHANGELOG.md").is_file(), "the repository is what IN_REPO says it is"
    bare = d / "plugin"; shutil.copytree(HERE, bare, ignore=shutil.ignore_patterns("__pycache__"))
    r = subprocess.run([sys.executable, str(bare / "tests" / "run_tests.py")], capture_output=True, text=True, encoding="utf-8", timeout=1500,
                       env=dict(os.environ, CRITIC_TEST_ONLY="the four typed fix skills are one /curmudgeon:fix"))
    assert "SKIP" in r.stdout and "needs the repository" in r.stdout and "FAIL" not in r.stdout and r.returncode == 0, (r.returncode, r.stdout[-600:], r.stderr[-600:])

@test("5.9.2 blind round F-ed8caba6, F-1fd5e8e6: a stream number (2>/dev/null, 2>&1) or a mkdir mode is no folder or file, from any folder; and the read guard neither refuses nor lists a mkdir of a folder that already exists")
def _(d):
    C = _c11(); root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload")
    write(root, "src/app.js", APP); (root / ".critic/scratch/r1/payload").mkdir(parents=True); (root / ".critic/reviews").mkdir(parents=True); claim_for(root, me, "C")
    for c in (f"cd {root}/src && mkdir -p {root}/.critic/reviews 2>/dev/null", f"cd {root}/src && mkdir -m 755 {root}/src 2>&1", f"cd {root}/src && ls 1>&2",
              f"cd {ws} && touch probe.js 2>&1", f"cd {root} && cat src/app.js 2> /dev/null"):
        assert C.bash_cut(c, str(root), me, ws) is None, (c, C.bash_cut(c, str(root), me, ws))
    assert C.bash_cut(f"cd {ws} && echo x >&{root}/src/out.txt", str(root), me, ws), ">&file still writes the file"
    assert C.bash_cut(f"cd {ws} && mkdir -m 755 {root}/src/new", str(root), me, ws), "a new folder after a mode is still cut"
    p = d / "proj2"; write(p, "src/app.js", APP); (p / ".critic/reviews").mkdir(parents=True); rec = _ws(p); w2 = rec["payload"]
    out = run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"cd {w2} && mkdir -p ../../../reviews 2>/dev/null"}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "a write into the real project" not in out, out
    out = run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"cd {w2} && mkdir -p {p}/src/newdir"}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "deny" in out, ("a new folder in the real project is still refused", out)

@test("5.9.2 blind round F-8bc1ae34, F-2a054ca6: a kept Python that no longer starts (py -3 with no runtime exits 1) is replaced, not taken as the hook's answer; a Python older than 3.9 is stopped by run.sh's own start line before the hook runs")
def _(d):
    import shutil
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    real = pathlib.Path(sys.executable).as_posix(); fake = d / "bin"; fake.mkdir(); data = d / "data"; data.mkdir()
    def tool(name, body): p = fake / name; p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8"); p.chmod(0o755)
    tool("python", f'exec "{real}" "$@"')
    count = d / "count.txt"
    hook = d / "hook.py"; hook.write_text(f"import sys\nopen({str(count)!r}, 'a').write('x')\nprint('ran', len(sys.stdin.read()))\n", encoding="utf-8")
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}", CLAUDE_PLUGIN_DATA=str(data))
    go = lambda: subprocess.run([sh, str(H / "run.sh"), str(hook)], input="hello", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    tool("py", 'echo "No suitable Python runtime found" >&2; exit 1')
    (data / "python").write_text("py -3\n", encoding="utf-8")
    r = go()
    assert r.returncode == 0 and r.stdout.strip() == "ran 5" and (data / "python").read_text(encoding="utf-8").strip() != "py -3" and count.read_text(encoding="utf-8") == "x", (r.returncode, r.stdout, r.stderr)
    old = d / "old"; old.mkdir(); (old / "sitecustomize.py").write_text("import sys\nsys.version_info = (3, 8, 18, 'final', 0)\n", encoding="utf-8")  # a real Python that says it is 3.8
    tool("python3", f'PYTHONPATH="{old.as_posix()}" exec "{real}" "$@"')
    (data / "python").write_text("python3\n", encoding="utf-8"); count.unlink()
    r = go()
    assert r.returncode == 0 and r.stdout.strip() == "ran 5" and count.read_text(encoding="utf-8") == "x" and (data / "python").read_text(encoding="utf-8").strip() == "python", ("the old Python never ran the hook; python did, once", r.returncode, r.stdout, r.stderr, count.read_text(encoding="utf-8"))
