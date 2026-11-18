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
