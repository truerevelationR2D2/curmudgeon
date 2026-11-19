"""Curmudgeon's script tests, part 14: release 5.9.2, the second Claude Code review (ruling 50). Run
plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its own. Each test here
failed on 171ee48, the commit that review read."""

def _runsh(d, hook, data, path_extra=None, stdin=""):
    import shutil
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(data))
    if path_extra: env["PATH"] = f"{path_extra}{os.pathsep}{os.environ.get('PATH', '')}"
    return subprocess.run([sh, str(H / "run.sh"), str(hook)], input=stdin, capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

@test("5.9.2 code review 2, V4, V-M8, V-M9: a hook that started is never run twice whatever it exits with; a retry gets the whole input; a program that only exits 40-42 is no hook's answer")
def _(d):
    real = pathlib.Path(sys.executable).as_posix(); fake = d / "bin"; fake.mkdir(); data = d / "data"; data.mkdir()
    def tool(name, body): p = fake / name; p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8"); p.chmod(0o755)
    tool("python3", f'exec "{real}" "$@"'); tool("python", f'exec "{real}" "$@"')
    count = d / "count.txt"
    for own in (127, 126, 99, 49):  # V4: the hook's own exit, after its work, looked like "never started"
        count.unlink(missing_ok=True); (data / "python").write_text("python3\n", encoding="utf-8")
        hook = d / "hook.py"; hook.write_text(f"import os\nopen({str(count)!r}, 'a').write('x')\nos._exit({own})\n", encoding="utf-8")
        r = _runsh(d, hook, data, fake, "payload")
        assert r.returncode == 1 and count.read_text(encoding="utf-8") == "x", ("ran once, an error", own, r.returncode, count.read_text(encoding="utf-8"))
    hook = d / "hook.py"; hook.write_text("import sys\nprint('got', len(sys.stdin.read()))\n", encoding="utf-8")
    tool("py", 'cat >/dev/null; echo "usage: py expr"; exit 2')  # V-M8: another py eats the input, then fails
    (data / "python").write_text("py -3\n", encoding="utf-8")
    r = _runsh(d, hook, data, fake, "hello")
    assert r.returncode == 0 and r.stdout.strip() == "got 5", ("the retry got the whole input", r.returncode, r.stdout, r.stderr)
    for code in (40, 41, 42):  # V-M9: a wrong program's exit is never the hook's answer, and its text never reaches Claude Code
        tool("py", f'echo impostor; exit {code}'); (data / "python").write_text("py -3\n", encoding="utf-8")
        r = _runsh(d, hook, data, fake, "hello")
        assert r.returncode == 0 and r.stdout.strip() == "got 5" and "impostor" not in r.stdout, (code, r.returncode, r.stdout, r.stderr)
        assert (data / "python").read_text(encoding="utf-8").strip() != "py -3", "the wrong py was replaced"

def _rg14(p, cmd, aid="r1", role="reviewer"):
    return run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(p), "agent_type": f"curmudgeon:curmudgeon-{role}", "agent_id": aid})).stdout

@test("5.9.2 code review 2, holes 5.9.1 did not have: $_ after a mkdir, a folder named for a review then .., a kill inside { } or function f { }, a kill after an escaped space and #, install -d -m, a variable that holds $HOME; all cut or refused")
def _(d):
    C = _c11(); root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload")
    write(root, "src/app.js", APP); (root / ".critic/scratch/r1/payload").mkdir(parents=True); (root / ".critic/reviews").mkdir(parents=True)
    claim_for(root, me, "C"); claude = pathlib.Path.home() / ".claude"
    cut = [f"cd {ws} && function f {{ kill 1; }}", f"cd {ws} && coproc {{ kill 1; }}", f"cd {ws} && {{ kill 1; }}",  # V-M5
           f"cd {ws} && echo a\\ #; kill -9 1", f"cd {ws} && touch notes\\ #; rm -rf /tmp/shared",  # V2
           f"cd {ws} && install -d -m 777 /tmp/dirx", f"cd {ws} && install -dm 777 /tmp/dirx",  # V3
           f"cd {ws} && D=$HOME/.claude; echo x > $D/settings.json", f"cd {ws} && export D=$HOME/.claude && touch $D/settings.json",  # V-G1
           f"cd {ws} && mkdir -p {root}/.critic/reviews/review-A.json/..",  # V-M4: mkdir -p makes review-A.json first
           f"cd {ws} && mkdir -p ../../../reviews && echo x > $_/review-B.json", f"cd {ws} && mkdir -p /tmp && touch $_/q"]  # V-M1
    for c in cut: assert C.bash_cut(c, str(root), me, ws), c
    p = d / "proj2"; write(p, "src/app.js", APP); write(p, ".critic/reviews/review-B.json", "{}"); rec = _ws(p); w2 = rec["payload"]; claim_for(p, "r1", "C")
    vrec = _ws(p, "v1", "verifier"); wv = vrec["payload"]
    for c in (f"cd {w2} && mkdir -p ../../../reviews && cat $_/review-B.json", f"cd {w2} && mkdir -p ../../.. && grep -r x $_"):  # V-M1
        assert "deny" in _rg14(p, c), c
    for c in (f"cd {wv} && mkdir -p ../../../reviews && cat $_/review-B.json", f"cd {wv} && mkdir -p {p}/.critic/reviews && cat $_/review-B.json"):
        assert "deny" in _rg14(p, c, "v1", "verifier"), c

@test("5.9.2 code review 2, false cuts 5.9.1 did not make: cd \"$_\" after mkdir, cd con, > inside (( )) [[ ]] $(( )), if kill -0, here-documents after an apostrophe or a quoted <<, rsync -t, < and <<< inputs, $(pwd)/.. and a wrapped mkdir of the reviews folder; each cuts and refuses no one")
def _(d):
    C = _c11(); root = d / "proj"; me = "r1"; ws = str(root / ".critic/scratch/r1/payload")
    write(root, "src/app.js", APP); (root / ".critic/scratch/r1/payload").mkdir(parents=True); (root / ".critic/scratch/r1/notes").mkdir(parents=True); (root / ".critic/reviews").mkdir(parents=True)
    claim_for(root, me, "C")
    honest = [f"cd {ws} && mkdir -p ../notes/run1 && cd \"$_\" && echo ok > result.txt", f"cd {ws} && cd con; echo x > a.txt",  # V1, V8
              f"cd {ws} && if (( n > 0 )); then echo y; fi", f"cd {ws} && [[ $a > 1 ]] && echo y", f"cd {ws} && echo $((3>2))",  # V5
              f"cd {ws} && if kill -0 $pid; then echo up; fi", f"cd {ws} && while kill -0 $pid; do sleep 1; done",  # V10
              f"cd {ws} && cat > ../notes/a.txt <<'EOF'\ndoesn't\nEOF\ncat > ../notes/p.sh <<'EOF2'\nkill -9 $pid\nEOF2",  # V-M2
              f"cd {ws} && grep -rn '<<EOF' src; cat > ../notes/p.sh <<'EOF'\nkill -9 $pid\nEOF",  # V-M3
              f"cd {ws} && rsync -t {root}/src/app.js ../notes/app.js",  # V-M6
              f"cd {ws} && tee ../notes/copy.txt < {root}/src/app.js", f"cd {ws} && tee ../notes/p.txt <<< {root}/src/app.js",  # V-M7
              f"cd {ws} && mkdir -p \"$(pwd)/../../../reviews\"", f"cd {ws} && mkdir -p $(pwd)/../../../reviews", f"cd {ws} && mkdir -p {ws}/../../../reviews",  # V7a
              f"cd {ws} && timeout 5 mkdir -p ../../../reviews"]
    old = os.environ.get("_"); os.environ["_"] = "/usr/bin/python3"  # what the hook's own process has in $_ (V1)
    try:
        for c in honest: assert C.bash_cut(c, str(root), me, ws) is None, (c, C.bash_cut(c, str(root), me, ws))
    finally:
        if old is None: os.environ.pop("_", None)
        else: os.environ["_"] = old
    assert C.bash_cut(f"cd {ws} && if kill 1; then echo; fi", str(root), me, ws), "a real kill after if still cuts"
    assert C.bash_cut(f"cd {ws} && if (( 1 )); then kill 2; fi", str(root), me, ws), "a real kill after (( )) still cuts"
    assert C.bash_cut(f"cd {ws} && cat > ../notes/a.txt <<'EOF'\ndoesn't\nEOF\nrm -rf /tmp/shared", str(root), me, ws), "a command after the here-document still counts"
    p = d / "proj2"; write(p, "src/app.js", APP); (p / ".critic/reviews").mkdir(parents=True); rec = _ws(p); w2 = rec["payload"]; claim_for(p, "r1", "C")
    vrec = _ws(p, "v1", "verifier"); wv = vrec["payload"]
    assert "deny" not in _rg14(p, f"cd {w2} && timeout 5 mkdir -p ../../../reviews"), "V7b: a wrapped mkdir of the existing reviews folder"
    assert "deny" not in _rg14(p, f"cd {wv} && tee ../notes/copy.txt < {p}/src/app.js", "v1", "verifier"), "V-M7: an input is no write"
    import time as _t
    many = f"cd {ws} && " + "".join(f"cat > ../notes/f{k}.txt <<'EOF'\n" + "it's a line\n" * 50 + "EOF\n" for k in range(80))
    t0 = _t.perf_counter(); C._tokens(many); took = _t.perf_counter() - t0
    assert took < 0.5, ("K-B3: here-documents are read in one pass, not once per here-document", took)

@test("5.9.2 Windows acceptance run (03 §5.57 item 53): a passage made only of the code a reviewer quotes and Curmudgeon's own instructions is no copy")
def _(d):
    sys.path.insert(0, str(HERE / "hooks")); import importlib, proctor; importlib.reload(proctor)
    root = d / "proj"; write(root, "app.py", "import sys\ntotal = float(sys.argv[1]) if len(sys.argv) > 1 else 0\n")
    pool = proctor._allowed(str(root), "A", time.time() + 20)
    g = proctor._norm("total = float(sys.argv[1]) if len(sys.argv) > 1 no data, no settings. what does the user see")
    assert g not in pool and proctor._explained(g, pool), "a quote of the code beside the sandbox scenario's own words"
    assert not proctor._explained(proctor._norm("a negative count prints a meaningless average to the user"), pool), "a reviewer's own words are still compared"

@test("5.9.2 Windows acceptance run (03 §5.57 item 53): run.sh starts no Python for a call that can't concern Curmudgeon, and still checks every call that can")
def _(d):
    root = d / "proj"; write(root, "app.py", "print(1)\n")
    import shutil
    sh = shutil.which("sh")
    if not sh: raise Skip("needs sh (Git Bash on Windows)")
    real = pathlib.Path(sys.executable).as_posix(); fake = d / "bin"; fake.mkdir(); log = d / "starts.txt"
    p = fake / "python3"; p.write_text(f'#!/bin/sh\necho x >> "{log.as_posix()}"\nexec "{real}" "$@"\n', encoding="utf-8"); p.chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}", CLAUDE_PLUGIN_DATA=str(d / "data"))
    def go(hook, payload):
        log.unlink(missing_ok=True)
        r = subprocess.run([sh, str(H / "run.sh"), str(H / hook)], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=root)
        return r.returncode, log.read_text(encoding="utf-8").count("x") if log.is_file() else 0
    assert go("pre_tool.py", {"tool_name": "Read", "tool_input": {"file_path": "src/a.js"}, "cwd": str(root)}) == (0, 0), "the user's own Read: no Python"
    assert go("pre_tool.py", {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(root)}) == (0, 0), "the user's own ls: no Python"
    assert go("post_tool.py", {"tool_name": "Grep", "tool_input": {"pattern": "x"}, "cwd": str(root)}) == (0, 0)
    assert go("pre_tool.py", {"tool_name": "Bash", "tool_input": {"command": "python3 tools/x.py"}, "cwd": str(root)})[1] >= 1, "a command that runs a .py file is checked"
    assert go("pre_tool.py", {"tool_name": "Read", "tool_input": {"file_path": "a"}, "cwd": str(root), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})[1] >= 1, "a reviewer's call is checked"
    assert go("pre_tool.py", {"tool_name": "Agent", "tool_input": {"prompt": "x"}, "cwd": str(root)})[1] >= 1, "a new agent is checked"

@test("5.9.2 Windows acceptance run (03 §5.57 item 53): a reviewer's test loop over 11 argument lists is not refused; a path built from 40 values still is")
def _(d):
    q = d / "q"; write(q, "app.py", "print(1)\n"); rec = _ws(q); w = rec["payload"]
    loop = f"cd {w} && for a in " + " ".join(f'"{k} {k + 1}"' for k in range(11)) + "; do echo \"== [$a]\"; python3 app.py $a; done"
    out = run(H / "read_guard.py", cwd=q, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": loop}, "cwd": str(q), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "deny" not in out, ("11 argument lists for a test loop", out)
    many = f"cd {w} && for a in " + " ".join(f"x{k}" for k in range(40)) + "; do cat ../$a/f; done"
    out = run(H / "read_guard.py", cwd=q, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": many}, "cwd": str(q), "agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1"})).stdout
    assert "deny" in out, "past the limit a path built from many values is still refused"
