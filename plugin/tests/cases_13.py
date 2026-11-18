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
    log.unlink(); (data / "python").write_bytes(b"python3\r\n")  # saved with Windows line ends (CI on #55)
    r = subprocess.run([sh, str(H / "run.sh"), str(hook), "x"], input="in", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=proj)
    assert r.returncode == 0 and log.read_text(encoding="utf-8").count("x") == 1, ("a kept name with a Windows line end is still trusted", log.read_text(encoding="utf-8"), r.stderr)

@test("5.9.2 (03 §5.57 item 49): a test that reads the repository around the plugin is skipped, not failed, where only the plugin folder is present, and in CI the repository is always found, so none of them is ever skipped there")
def _(d):
    if os.environ.get("GITHUB_ACTIONS") == "true": assert IN_REPO, "CI checks out the whole repository: a repository test must never be skipped there"
    if IN_REPO:
        assert (REPO / "eval" / "score.py").is_file() and (REPO / "CHANGELOG.md").is_file(), "the repository is what IN_REPO says it is"
    bare = d / "plugin"; shutil.copytree(HERE, bare, ignore=shutil.ignore_patterns("__pycache__"))
    r = subprocess.run([sys.executable, str(bare / "tests" / "run_tests.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500,
                       env=dict(os.environ, CRITIC_TEST_ONLY="the four typed fix skills are one /curmudgeon:fix", PYTHONIOENCODING="utf-8"))  # utf-8 both ways: Windows CI's console code page can't decode the em dash (CI on #55)
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
    assert "deny" not in out, out  # neither refused as a write nor as a read
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

@test("5.9.2 blind round 2: the shell rule sees a heredoc's own redirect, kill behind a wrapper with options, $HOME and set variables, cp -t, sed -Ei, a trailing backslash, and a file named 2; honest commands stay uncut")
def _(d):
    C = _c11(); root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload"); (root / ".critic/scratch/r1/payload").mkdir(parents=True); write(root, "src/app.js", APP)
    claude = pathlib.Path.home() / ".claude"
    cut = [f"cd {ws} && cat <<EOF > /tmp/probe.txt\nhi\nEOF", f"cd {ws} && cat <<'EOF' >> {claude}/settings.json\n{{}}\nEOF",
           f"cd {ws} && timeout 5 kill 1234", f"cd {ws} && env -i pkill -f claude", f"cd {ws} && sudo -n kill 1", f"cd {ws} && xargs -n 1 kill < pids",
           f"cd {ws} && echo '{{}}' > $HOME/.claude/settings.json", f"cd {ws} && D=/tmp; touch $D/q", f"cd {ws} && cp -t {claude}/ settings.json",
           f"cd {ws} && sed -Ei 's/x/y/' /tmp/shared.cfg", f"cd {ws} && touch /tmp/x \\", f"cd {root}/src && rm 2 > /dev/null", f"cd {ws} && echo hi > {root}/src/2"]
    for c in cut: assert C.bash_cut(c, str(root), me, ws), c
    honest = [f"cd {ws} && cat <<EOF > ../notes/probe.py\nimport os; os.kill(1, 9)\nEOF", f"cd {ws} && grep -rn kill src", f"cd {ws} && timeout 60 python3 -m pytest 2>&1",
              f"cd {ws} && echo x > $PWD/probe.txt", f"cd {ws} && cp -t ../notes src/app.js", f"cd {ws} && sed -E 's/a/b/' src/app.js", f"cd {ws} && ls 2>/dev/null"]
    for c in honest: assert C.bash_cut(c, str(root), me, ws) is None, (c, C.bash_cut(c, str(root), me, ws))

@test("5.9.2 code review: a program that answers to a kept Python's name and exits 2 never blocks, and its printout never reaches Claude Code; a types.py or runpy.py in the project can't stand in for a module when a hook starts")
def _(d):
    import shutil
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    real = pathlib.Path(sys.executable).as_posix(); fake = d / "bin"; fake.mkdir(); data = d / "data"; data.mkdir()
    def tool(name, body): p = fake / name; p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8"); p.chmod(0o755)
    tool("python", f'exec "{real}" "$@"'); tool("python3", f'exec "{real}" "$@"')
    tool("py", 'echo "usage: py [options] expression"; exit 2')  # another tool called py, with its own usage error
    (data / "python").write_text("py -3\n", encoding="utf-8")
    hook = d / "hook.py"; hook.write_text('import json, sys\nprint(json.dumps({"ok": len(sys.stdin.read())}))\n', encoding="utf-8")
    proj = d / "proj"; proj.mkdir()
    for planted in ("types.py", "runpy.py", "traceback.py"): (proj / planted).write_text('raise SystemExit("planted")\n', encoding="utf-8")
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}", CLAUDE_PLUGIN_DATA=str(data))
    r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="hello", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=proj)
    assert r.returncode == 0 and r.stdout.strip() == '{"ok": 5}', ("the hook ran, alone on stdout, and nothing blocked", r.returncode, r.stdout, r.stderr)
    assert (data / "python").read_text(encoding="utf-8").strip() != "py -3", "the wrong py was replaced"
    for code in (0, 1, 2):
        hook.write_text(f"import sys\nprint('x')\nsys.exit({code})\n", encoding="utf-8")
        r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=proj)
        assert r.returncode == code, (code, r.returncode, r.stderr)
    hook.write_text("raise ValueError('boom')\n", encoding="utf-8")
    r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="", capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=proj)
    assert r.returncode == 1 and "boom" in r.stderr, ("a crash is an error, never a block", r.returncode, r.stderr)

@test("5.9.2 code review: one reading of a command's writes for every agent; (echo x)>f, true;>f, rm.exe, >&f and &>>f are writes for a verifier too; mkdir is judged by its whole word as the OS sees it; a .CRITIC folder on Linux is not the way to a .critic review")
def _(d):
    C = _c11()
    for c, want in (("(echo x)>/p/x.js", "/p/x.js"), ("true;>/p/y", "/p/y"), ("rm.exe -rf /p/src", "/p/src"), ("echo hi >&/p/o", "/p/o")):
        assert os.path.normpath(want) in [os.path.normpath(t) for t in C.write_targets(c, "/w")], (c, C.write_targets(c, "/w"))
    p = d / "proj"; write(p, "src/app.js", APP); (p / ".critic/reviews").mkdir(parents=True)
    rec = _ws(p, "v1", "verifier"); w = rec["payload"]
    for c in (f"cd {w} && echo x >&{p}/src/out.txt", f"cd {w} && echo x &>>{p}/src/out.txt", f"cd {w} && (echo x)>{p}/src/x.js",
              f"cd {w} && mkdir -p {p}/src,.", f"cd {w} && mkdir -p {p}/src/newdir/..", f"cd {w} && cat <<EOF > {p}/src/h.js\nx\nEOF"):
        assert "deny" in _rg(p, "Bash", role="verifier", aid="v1", command=c), c
    assert "deny" not in _rg(p, "Bash", role="verifier", aid="v1", command=f"cd {w} && echo x > ../notes/ok.txt"), "its own notes"
    if not (p / ".CRITIC").exists():  # a case-sensitive file system
        root = d / "proj3"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload"); (root / ".critic/scratch/r1/payload").mkdir(parents=True); write(root, "src/app.js", APP)
        claim_for(root, me, "C")
        assert C.bash_cut(f"cd {ws} && mkdir -p {root}/.CRITIC/REVIEWS", str(root), me, ws), "a new .CRITIC folder is not on the way to .critic/reviews"

@test("5.9.2 blind round 3: the shell rule reads comments, line continuations, quoted or arithmetic <<, if/while/do, wrappers before a write, bash -c, eval and backticks the way the shell does; command -v, kill -l, /dev/fd and a $VAR mkdir of an existing folder cut no one; a reviewer may make the folder on the way to its own review")
def _(d):
    C = _c11(); root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload"); (root / ".critic/scratch/r1/payload").mkdir(parents=True); write(root, "src/app.js", APP)
    claude = pathlib.Path.home() / ".claude"
    cut = [f"cd {ws} && grep -n '<<EOF' deploy.sh\nrm /tmp/shared.json", f"cd {ws} && echo $((1<<3)); rm /tmp/z", f"cd {ws} && # check it's there\nrm /tmp/a",
           f"cd {ws} && rm -f \\\n  /tmp/shared.json", f"cd {ws} && if kill -9 $PID; then echo done; fi", f"cd {ws} && while true; do pkill x; done",
           f"cd {ws} && for f in a b; do touch /tmp/$f; done", f"cd {ws} && timeout 5 tee {claude}/settings.json", f"cd {ws} && nohup touch /tmp/n",
           f"cd {ws} && bash -c 'cd src && kill 1234'", f"cd {ws} && bash -c 'echo x > /tmp/probe'", f"cd {ws} && eval 'touch /tmp/e'", f"cd {ws} && echo `kill 3`",
           f"cd {ws} && sudo -u root kill 1", f"cd {ws} && export D=/tmp && touch $D/q", f"cd {ws} && rsync -a src /tmp/x", f"cd {ws} && shred /tmp/x"]
    for c in cut: assert C.bash_cut(c, str(root), me, ws), c
    honest = [f"cd {ws} && command -v kill >/dev/null && echo have kill", f"cd {ws} && kill -l", f"cd {ws} && python3 -c 1 2> /dev/fd/1",
              f"cd {ws} && mkdir -p $HOME", f"cd {ws} && R={root}; mkdir -p $R/src", f"cd {ws} && cat <<EOF > ../notes/p.sh\nkill 1; rm /tmp/x\nEOF"]
    for c in honest: assert C.bash_cut(c, str(root), me, ws) is None, (c, C.bash_cut(c, str(root), me, ws))
    p = d / "proj2"; write(p, "src/app.js", APP); rec = _ws(p); w2 = rec["payload"]; claim_for(p, "r1", "B")
    assert not (p / ".critic/reviews").exists()
    out = run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"cd {w2} && mkdir -p {p}/.critic/reviews"}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "deny" not in out, ("the folder on the way to its own claimed review, before it exists", out)
    out = run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"cd {w2} && mkdir -p {p}/.critic/reviews/review-A.json"}, "cwd": str(p), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "deny" in out, "never a folder named for another review"

@test("5.9.2 blind round 3: run.sh runs only one of the three Python names from its kept file, never a command written there, and a hook that ran and was killed is not run a second time")
def _(d):
    import shutil
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    data = d / "data"; data.mkdir(); mark = d / "MARK"
    (data / "python").write_text(f"python3 -c open({mark.as_posix()!r},'w')\n", encoding="utf-8")
    hook = d / "hook.py"; hook.write_text("print('ran')\n", encoding="utf-8")
    r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="", capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, CLAUDE_PLUGIN_DATA=str(data)), timeout=60)
    assert r.stdout.strip() == "ran" and not mark.exists(), ("a command in the kept file is never run", r.stdout, r.stderr)
    count = d / "count.txt"
    hook.write_text(f"import os\nopen({str(count)!r}, 'a').write('x')\nos._exit(137)\n", encoding="utf-8")
    for kept in ("python3", "python"):
        if not shutil.which(kept): continue
        count.unlink(missing_ok=True); (data / "python").write_text(kept + "\n", encoding="utf-8")
        r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="", capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, CLAUDE_PLUGIN_DATA=str(data)), timeout=60)
        assert r.returncode == 1 and count.read_text(encoding="utf-8") == "x", ("killed after its work: an error, run once", kept, r.returncode, count.read_text(encoding="utf-8"))
    fake = d / "bin"; fake.mkdir(); real = pathlib.Path(sys.executable).as_posix()
    (fake / "python3").write_text(f'#!/bin/sh\ncase "$1" in -c) exit 1 ;; esac\nexec "{real}" "$@"\n', encoding="utf-8"); (fake / "python3").chmod(0o755)  # runs the hook, but fails the version test afterwards
    (fake / "python").write_text(f'#!/bin/sh\nexec "{real}" "$@"\n', encoding="utf-8"); (fake / "python").chmod(0o755)
    count.unlink(missing_ok=True); (data / "python").write_text("python3\n", encoding="utf-8")
    r = subprocess.run([sh, str(H / "run.sh"), str(hook)], input="", capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, CLAUDE_PLUGIN_DATA=str(data), PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}"), timeout=60)
    assert r.returncode == 1 and count.read_text(encoding="utf-8") == "x", ("killed, even when the version test then fails: never run a second time", r.returncode, count.read_text(encoding="utf-8"))
