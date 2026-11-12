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

# N5 (03 §5.57 item 34): it loosens a guard, so every row of its case table is a test, refused and allowed alike.
N5_ALLOWED = [  # network words only as data, in code that can't run text
    "python3 -c 'import json; print(json.dumps({\"title\": \"uses requests and curl\", \"evidence\": \"socket in app.py\"}))'",
    "python3 - <<'EOF'\nimport json\nopen(\"out.json\", \"w\").write(json.dumps([{\"evidence\": \"urllib and http.client are used\", \"tags\": [\"requests\"]}]))\nEOF",
    "node -e 'console.log(JSON.stringify({t: \"fetch( and WebSocket and curl\"}))'",
]
N5_REFUSED = [  # still network code, or text that could become code
    "python3 -c 'import urllib.request'",
    "python3 -c '__import__(\"socket\")'",
    "python3 -c 'import importlib; importlib.import_module(\"urllib.request\")'",
    "python3 -c 'import os; os.system(\"curl http://x.invalid\")'",
    "python3 -c 'import subprocess; subprocess.run([\"curl\", \"http://x.invalid\"])'",
    "python3 -c 'exec(\"import socket\")'",
    "python3 -c 'import sys; print(sys.modules[\"socket\"])'",
    "python3 -c 'print(globals()[\"__builtins__\"]); x = \"requests\"'",
    "python3 - <<'EOF'\nprint(f\"{__import__('socket')}\")\nEOF",
    "python3 - <<'EOF'\nimport codecs\nx = codecs.decode('erdhrfgf', 'rot13')  # requests\nEOF",
    "node -e 'require(\"https\").get(\"http://x.invalid\")'",
    "node -e 'const cp = require(\"child_process\"); cp.execSync(\"curl http://x.invalid\")'",
    "node -e 'console.log(`${\"curl\"}`)'",
    "node -e 'globalThis[\"eval\"](\"fetch(1)\"); const s = \"curl\"'",
    "ruby -e 'puts \"#{Net::HTTP.get(u)}\"'",
    "perl -e 'my $u = \"curl\"; system($u)'",
    "node -e \"x = 'requests\"",
    # 5.5.0 blind round: a comment in front (the lines reach the guard joined), resolvers by name, builtins by key
    "python3 - <<'EOF'\n# no requests or sockets here\nprint(1)\nEOF",
    "python3 - <<'EOF'\n# check the endpoint\nimport urllib.request\nurllib.request.urlopen('http://x.invalid/')\nEOF",
    "python3 -c 'import pkgutil; pkgutil.resolve_name(\"urllib.request:urlopen\")(\"http://x.invalid/\")'",
    "python3 -c 'import pydoc; pydoc.locate(\"urllib.request.urlopen\")(\"http://x.invalid/\")'",
    "python3 -c \"__builtins__.__dict__.get('__import__')('urllib.request').urlopen('http://x.invalid/')\"",
]

@test("5.5.0 N5: the offline tripwire lets a reviewer's script carry network words as data, and still refuses network code and anything that could turn text into code")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); ws = _ws(p)["payload"]
    for cmd in N5_ALLOWED:
        assert "deny" not in _rg(p, "Bash", command=f"cd {ws} && {cmd}"), ("allowed", cmd)
    for cmd in N5_REFUSED:
        assert "deny" in _rg(p, "Bash", command=f"cd {ws} && {cmd}"), ("refused", cmd)
    for role in ("verifier",):
        w2 = _ws(p, aid="v1", role=role)["payload"]
        assert "deny" not in _rg(p, "Bash", role=role, aid="v1", command=f"cd {w2} && {N5_ALLOWED[0]}"), role
        assert "deny" in _rg(p, "Bash", role=role, aid="v1", command=f"cd {w2} && {N5_REFUSED[1]}"), role

# The proctor (03 §5.57 item 35). Transcript rows use the shape recorded from a real reviewer agent on 10 Nov 2026
# (Claude Code's app, entrypoint remote_cowork): a user entry whose content is a list holding one tool_result, with the
# output as a string (Read, Bash) or as a list of text parts (SubagentHandback's own result).

def _tr9(d, name, outputs, report, wrote=None):
    rows = [{"type": "user", "message": {"role": "user", "content": "the brief, as the prompt"}}]
    if wrote: rows.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "w", "name": "Write", "input": {"file_path": str(d / ".critic" / "reviews" / f"review-{wrote}.json"), "content": "[]"}}]}})
    for i, o in enumerate(outputs):
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"toolu_{i}", "name": "Read", "input": {"file_path": "x"}}]}})
        body = o if i % 2 == 0 else [{"type": "text", "text": o}]
        rows.append({"parentUuid": "p", "isSidechain": True, "type": "user", "message": {"role": "user", "content": [{"tool_use_id": f"toolu_{i}", "type": "tool_result", "content": body}]}, "uuid": f"u{i}", "entrypoint": "remote_cowork"})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "h", "name": "SubagentHandback", "input": {"message": report}}]}})
    rows.append({"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "h", "type": "tool_result", "content": [{"type": "text", "text": "{\"success\":true,\"message\":\"Report delivered to your caller.\"}"}]}]}})
    p = pathlib.Path(TMP) / "transcripts" / d.name / name; p.parent.mkdir(parents=True, exist_ok=True)  # outside the project, as Claude Code keeps them
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"); return p

def _stop9(d, aid, letter, outputs, transcript=True, report=None, wrote=True, ws=True):
    if ws: run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": aid, "cwd": str(d)}))
    ev = {"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": aid, "cwd": str(d), "stop_hook_active": False,
          "last_assistant_message": "Report delivered." if transcript else f"Wrote .critic/reviews/review-{letter}.json."}
    if transcript: ev["agent_transcript_path"] = str(_tr9(d, f"t-{aid}.jsonl", outputs, report or f"Wrote .critic/reviews/review-{letter}.json.", wrote=letter if wrote else None))
    run(H / "check_contract.py", cwd=d, stdin=json.dumps(ev))
    return json.loads((d / f".critic/stops/{aid}.json").read_text(encoding="utf-8")).get("proctor")

TAX9 = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rate hard-coded in the price",
               evidence="src/app.js:4 multiplies by a literal 1.0825, so a rate change in any state ships wrong prices until redeployed",
               failing_case="the state rate becomes 8.5%; every price is still computed at 8.25% and nothing reports it", remediation="read the rate from config")

@test("5.5.0 proctor: a reviewer whose tool output showed another brief, the scan report or another review is voided, by the run marks alone; its own brief and review, the code, and output another reviewer also quoted don't count")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    run(S / "critic_scan.py", ".", "--root", ".", "--only", ".critic/scan-only.txt", cwd=d)
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "ABC"}
    assert all("<!-- run mark cm-" in b[x] for x in "ABC") and len({re.search(r"cm-[0-9a-f]+", b[x]).group(0) for x in "ABC"}) == 3, "each brief its own mark"
    scan_md = (d / ".critic/scan/report.md").read_text(encoding="utf-8"); assert "run mark cm-" in scan_md
    write(d, ".critic/reviews/review-B.json", json.dumps([TAX9]))
    code = (d / "src/app.js").read_text(encoding="utf-8")
    assert _stop9(d, "a1", "A", [b["A"], code, "1\timport statistics"]) == {"checked": True, "saw": []}, "its own brief and the code"
    assert _stop9(d, "a2", "A", [code, b["B"]])["saw"] == ["the mark of brief-B"]
    assert _stop9(d, "a3", "A", ["1\t" + scan_md.replace("\n", "\n2\t")])["saw"] == ["the mark of the scan report"]
    _stop9(d, "b1", "B", [b["B"]])  # B's stop stamps its review: a mark on every line
    raw = (d / ".critic/reviews/review-B.json").read_text(encoding="utf-8"); mk = re.search(r"cm-[0-9a-f]{24}", raw).group(0)
    assert all(mk in line for line in raw.splitlines() if line.strip()), ("every line of a stamped review carries its mark", raw)
    assert _stop9(d, "a4", "A", [raw])["saw"] == ["the mark of review-B.json"], "read the other review as a file"
    one = next(l for l in raw.splitlines() if "Tax rate" in l)
    assert _stop9(d, "a5", "A", ["12:" + one])["saw"] == ["the mark of review-B.json"], "or grepped one finding out of it"
    assert _stop9(d, "a6", "A", [TAX9["failing_case"], "Traceback (most recent call last): ZeroDivisionError"])["saw"] == [], "the same words, or the same output, with no mark: never voided (5.5.0 blind round)"
    assert _stop9(d, "a7", "A", [], transcript=False) == {"checked": False, "why": "no readable transcript"}
    write(d, ".critic/reviews/review-A.json", "[]"); _stop9(d, "a8", "A", [b["A"]])
    own = (d / ".critic/reviews/review-A.json").read_text(encoding="utf-8")
    assert _stop9(d, "a9", "A", [own, b["A"]])["saw"] == [], "its own review and brief"
    _stop9(d, "a10", "A", [b["A"]], report="Wrote .critic/reviews/review-A.json. I saw .critic/reviews/review-B.json by accident and didn't read it.")
    assert json.loads((d / ".critic/stops/a10.json").read_text(encoding="utf-8"))["review"] == "review-A.json", "the review it wrote, not one it mentioned"
    assert [f["title"] for f in json.loads(raw)["findings"]] == [TAX9["title"]]
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-B.json", "--no-scan", cwd=d)
    rows = [f for k in ("kept", "contested", "dropped") for f in json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))[k] for f in ([f["finding"]] if "finding" in f else [f])]
    assert rows and not any("mark" in f for f in rows), ("the merge drops a review's marks from its findings (5.5.0 blind round 2)", rows)

@test("5.5.0 proctor: a voided review's votes don't count; a finding only it raised is kept only when a blind verifier reproduces it by running it, labelled, with no vote; a missing transcript marks the run DEGRADED")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "ABC"}
    high = finding(impact="High")
    write(d, ".critic/reviews/review-A.json", json.dumps([high, TAX9])); write(d, ".critic/reviews/review-B.json", json.dumps([high])); write(d, ".critic/reviews/review-C.json", "[]")
    _stop9(d, "ra", "A", [b["C"]]); _stop9(d, "rb", "B", [b["B"]]); _stop9(d, "rc", "C", [b["C"]], transcript=False)
    rv = [f".critic/reviews/review-{x}.json" for x in "ABC"]
    r = run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d); assert r.returncode == 0, r.stderr
    t = json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))
    assert t["reviewers"] == 2 and any("review voided by the proctor: review-A.json" in x for x in t["degraded"]), t["degraded"]
    assert any("the proctor couldn't check review-C.json" in x for x in t["degraded"]), t["degraded"]
    xss = [f for f in t["kept"] + t["contested"] if f["category"] == "xss"][0]
    assert xss["votes"] == 1 and xss["of"] == 2, ("only the honest reviewer's vote", xss)
    tax = [f for f in t["contested"] if f.get("voided_only")]
    assert len(tax) == 1 and tax[0]["votes"] == 0 and (d / f".critic/verify/{tax[0]['id']}.json").is_file(), ("verified blind", t["contested"])
    assert '"mark": "cm-' in (d / f".critic/verify/{tax[0]['id']}.json").read_text(encoding="utf-8") and t.get("mark", "").startswith("cm-")
    traced = {"id": tax[0]["id"], "verdict": "confirmed", "reproduced": "traced", "entry": "price is computed on every order",
              "path": "src/app.js:4 multiplies total by the literal 1.0825, so the rate can't change without a redeploy"}
    run(S / "critic_merge.py", "apply", str(hook_verdicts(d, [traced], "v1")), cwd=d)
    final = [json.loads(l) for l in (d / ".critic/findings.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert not any(f["category"] == "domain" for f in final), ("traced is not reproduced", final)
    run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d)
    tid = [f for f in json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))["contested"] if f.get("voided_only")][0]["id"]
    ran = dict(traced, id=tid, reproduced="executed")
    run(S / "critic_merge.py", "apply", str(hook_verdicts(d, [ran], "v2")), cwd=d)
    final = [json.loads(l) for l in (d / ".critic/findings.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [f for f in final if f["category"] == "domain"]
    assert len(kept) == 1 and kept[0]["voided_only"] and kept[0]["votes"] == 0 and kept[0]["impact"] in ("Medium", "Low"), ("reproduced by running it: kept, labelled", kept)
    c = (d / ".critic/counts.md").read_text(encoding="utf-8")
    assert "## From voided reviews" in c and f"{tid} " in c.split("## From voided reviews")[1] and "<!-- run mark cm-" in c, c[-900:]

@test("5.5.0 proctor request command: from its copy a reviewer gets files elsewhere and the project's history, never .critic, Curmudgeon's or Claude's own folders, or an answer holding a run mark; every request is logged")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); write(p, ".critic/secret.md", "RUN-SECRET\n")
    subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "-A", "-f"], cwd=p); subprocess.run(G9 + ["commit", "-qm", "first"], cwd=p)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=p)
    ws = _ws(p)["payload"]; other = write(d, "elsewhere/lib.py", "def helper():\n    return 1\n")
    ask = lambda *a, cwd=ws: run(S / "critic_proctor.py", "ask", *a, cwd=pathlib.Path(cwd), env={"CRITIC_ROOT": ""})
    r = ask("read", str(other)); assert r.returncode == 0 and "def helper" in r.stdout, r.stderr
    assert ask("read", str(p / ".critic/secret.md")).returncode == 2 and ask("read", str(p / ".CRITIC" / "secret.md")).returncode == 2
    try: os.symlink(p / ".critic", d / "sneaky", target_is_directory=True); linked = True
    except (OSError, NotImplementedError): linked = False
    if linked: assert ask("list", str(d / "sneaky")).returncode == 2, "a link into .critic"
    assert ask("read", os.path.join(os.environ["CURMUDGEON_STATE_DIR"], "x")).returncode == 2
    assert ask("list", str(pathlib.Path.home() / ".claude")).returncode == 2
    r = ask("git", "log", "--oneline"); assert r.returncode == 0 and "first" in r.stdout, r.stderr
    r = ask("git", "show", "--stat", "HEAD"); assert r.returncode == 0 and "src/app.js" in r.stdout and ".critic" not in r.stdout, r.stdout
    for bad in (["git", "show", "HEAD:.critic/secret.md"], ["git", "diff", "--output=/tmp/x"], ["git", "push"], ["git", "log", "--", ".critic"]):
        assert ask(*bad).returncode == 2, bad
    brief = write(d, "elsewhere/copied-brief.md", (p / ".critic/briefs/brief-A.md").read_text(encoding="utf-8"))
    r = ask("read", str(brief)); assert r.returncode == 3 and "brief" not in r.stdout, ("a run mark in the answer: withheld", r.stdout[:200])
    log = (p / ".critic/proctor/requests.jsonl").read_text(encoding="utf-8")
    assert "refused: a .critic folder" in log and "withheld" in log and "given" in log, log[-600:]
    out = _rg(p, "Bash", command=f"cd {ws} && {sys.executable} {S / 'critic_proctor.py'} ask read {other}")
    assert "deny" not in out, ("the guard lets a reviewer ask the proctor", out)

@test("5.5.0 blind round on the proctor: two voided reviews' same finding is one finding; a fresh reviewer's clean record replaces a voided one's; a voided-only packet asks for a run; the scan marks every file it writes and every row")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    run(S / "critic_scan.py", ".", "--root", ".", "--only", ".critic/scan-only.txt", cwd=d)
    sc = d / ".critic/scan"; rep_ = json.loads((sc / "report.json").read_text(encoding="utf-8"))
    assert rep_["mark"] and all(x.get("mark") == rep_["mark"] for x in rep_["findings"]), "every scan row carries the mark"
    assert rep_["mark"] in (sc / "scan.sarif").read_text(encoding="utf-8") and (sc / "report.md").read_text(encoding="utf-8").startswith("<!-- run mark ")
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "ABC"}
    high = finding(impact="High")
    write(d, ".critic/reviews/review-A.json", json.dumps([high])); write(d, ".critic/reviews/review-B.json", json.dumps([TAX9])); write(d, ".critic/reviews/review-C.json", json.dumps([high]))
    _stop9(d, "ra", "A", [b["B"]]); _stop9(d, "rb", "B", [b["B"]]); _stop9(d, "rc", "C", [b["B"]])
    rv = [f".critic/reviews/review-{x}.json" for x in "ABC"]
    run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d)
    t_ = json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))
    xss = [f for f in t_["contested"] if f.get("voided_only")]
    assert len(xss) == 1, ("one finding, not two", [f["id"] for f in xss])
    assert "running it" in json.loads((d / f".critic/verify/{xss[0]['id']}.json").read_text(encoding="utf-8")).get("needs_a_run", ""), "the verifier is told a trace won't keep it"
    time.sleep(0.05); _stop9(d, "ra2", "A", [b["A"]])  # a fresh reviewer for A, clean
    run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d)
    deg = json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))["degraded"]
    assert not any("review voided by the proctor: review-A.json" in x for x in deg) and any("review-C.json" in x and "voided" in x for x in deg), deg

@test("5.5.0 blind round on the request command: blame and path-limited history work, REV:PATH works only alone, and CRITIC_ROOT can't point it elsewhere")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); write(p, ".critic/secret.md", "RUN-SECRET\n")
    subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "-A", "-f"], cwd=p); subprocess.run(G9 + ["commit", "-qm", "first"], cwd=p)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=p); ws = _ws(p)["payload"]
    ask = lambda *a, env=None: run(S / "critic_proctor.py", "ask", *a, cwd=pathlib.Path(ws), env=dict({"CRITIC_ROOT": ""}, **(env or {})))
    r = ask("git", "blame", "--", "src/app.js"); assert r.returncode == 0 and "render" in r.stdout, r.stderr
    r = ask("git", "log", "--oneline", "--", "src/app.js"); assert r.returncode == 0 and "first" in r.stdout, r.stderr
    r = ask("git", "show", "HEAD:src/app.js"); assert r.returncode == 0 and "render" in r.stdout, r.stderr
    for bad in (["git", "show", "HEAD:src/app.js", "HEAD"], ["git", "log", "--", ":(top)"], ["git", "blame", "--", ".critic/secret.md"], ["git", "show", "HEAD:"]):
        r = ask(*bad); assert r.returncode == 2 and "RUN-SECRET" not in r.stdout, bad
    other = d / "other"; write(other, "x.txt", "x\n")
    r = ask("read", str(p / ".critic/briefs/brief-A.md"), env={"CRITIC_ROOT": str(other)})
    assert r.returncode == 2, "CRITIC_ROOT is ignored: .critic stays refused"
    assert "brief-A" not in (other / ".critic/proctor/requests.jsonl").read_text(encoding="utf-8") if (other / ".critic/proctor/requests.jsonl").exists() else True

N5_REFUSED_R2 = [  # 5.5.0 blind round 2
    "python3 -c 'import os; os.posix_spawnp(\"curl\", [\"curl\", \"http://x.invalid\"], {})'",
    "python3 -c 'import asyncio; asyncio.run(asyncio.create_subprocess_exec(\"curl\", \"http://x.invalid\"))'",
    "python3 -c 'import timeit; timeit.timeit(\"import urllib.request\", number=1)'",
    "python3 -c 'import cProfile; cProfile.run(\"import socket\")'",
    "python3 -c 'import code; code.InteractiveInterpreter().runsource(\"import socket\")'",
    "python3 -c 'open(\"m.py\", \"w\").write(\"import socket\"); import m'",
    "node - <<'EOF'\n// don't worry, it's fine\nfetch('http://x.invalid/')\nEOF",
]

@test("5.5.0 blind round 2: the guard keeps refusing text that can run, N5's comment and runner gaps closed, and reviewers can't read another brief")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=p); ws = _ws(p)["payload"]
    for cmd in N5_REFUSED_R2:
        assert "deny" in _rg(p, "Bash", command=f"cd {ws} && {cmd}"), cmd
    assert "deny" in _rg(p, "Read", file_path=str(p / ".critic/briefs/brief-B.md")), "a reviewer reads no brief: its own is its prompt"
    tr_ = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")) / "projects" / "x" / "lead.jsonl"
    assert "deny" in _rg(p, "Read", file_path=str(tr_)), "nor a session transcript (the lead's holds other reviewers' reports)"
    assert "deny" not in _rg(p, "Read", file_path=str(pathlib.Path(os.path.expanduser("~/.claude")) / "plugins" / "x" / "references" / "rubrics.md")), "the plugin's references stay readable"
    assert "brief-A.md" in run(S / "critic_brief.py", "--letters", "A", cwd=p).stdout, "critic_brief.py prints the brief paths again"

@test("5.5.0 blind round 2: one stop record per review (a writer's first), the tally's second check, the contract on the file the reviewer wrote, voided repeats, the marks lock, git blame's options, and the counts' last line")
def _(d):
    write(d, "src/app.js", APP)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d)
    b = {x: (d / f".critic/briefs/brief-{x}.md").read_text(encoding="utf-8") for x in "ABC"}
    high = finding(impact="High")
    write(d, ".critic/reviews/review-A.json", json.dumps([TAX9, TAX9])); write(d, ".critic/reviews/review-B.json", json.dumps([high])); write(d, ".critic/reviews/review-C.json", "[]")
    _stop9(d, "a1", "A", [b["B"]]); _stop9(d, "rb", "B", [b["B"]])
    rv = [f".critic/reviews/review-{x}.json" for x in "ABC"]
    pr = d / ".critic/proctor/marks.json"; kept = pr.read_text(encoding="utf-8"); pr.write_text('{"marks": {}}', encoding="utf-8")
    assert _stop9(d, "rc", "C", [b["A"]]) == {"checked": True, "saw": []}, "no marks known at its stop"
    pr.write_text(kept, encoding="utf-8")
    time.sleep(0.05); _stop9(d, "a2", "A", [b["A"]], wrote=False)  # never wrote review-A: can't clear A's void
    run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d)
    t_ = json.loads((d / ".critic/tally.json").read_text(encoding="utf-8")); deg = t_["degraded"]
    assert any("voided by the proctor: review-A.json" in x for x in deg), ("a record from an agent that didn't write the file doesn't clear the void", deg)
    assert any("voided by the proctor: review-C.json" in x for x in deg), ("checked again at the tally, against the marks known then", deg)
    assert len([f for f in t_["contested"] if f.get("voided_only")]) == 1, "a voided review's repeated finding is one finding"
    assert list(t_)[0] == "mark" and list(t_)[-1] == "mark_end"
    time.sleep(0.05); _stop9(d, "a3", "A", [b["A"]], ws=False)  # a fresh reviewer that wrote review-A, with no private copy
    run(S / "critic_merge.py", "tally", *rv, "--no-scan", cwd=d)
    deg = json.loads((d / ".critic/tally.json").read_text(encoding="utf-8"))["degraded"]
    assert not any("voided by the proctor: review-A.json" in x for x in deg) and any("review-A.json (its stop record says the agent had no private copy" in x for x in deg), deg
    run(S / "critic_merge.py", "apply", cwd=d)
    assert (d / ".critic/counts.md").read_text(encoding="utf-8").rstrip().splitlines()[-1].startswith("<!-- run mark cm-"), "the counts end with their mark"
    write(d, ".critic/reviews/review-A.json", '[{"impact": "High"}]')
    ev = {"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "a4", "cwd": str(d), "stop_hook_active": False, "last_assistant_message": "x",
          "agent_transcript_path": str(_tr9(d, "t-a4.jsonl", [], "Wrote .critic/reviews/review-A.json; I saw .critic/reviews/review-B.json by accident.", wrote="A"))}
    run(H / "scratch_dir.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "a4", "cwd": str(d)}))
    assert '"block"' in run(H / "check_contract.py", cwd=d, stdin=json.dumps(ev)).stdout, "the contract checks the file the reviewer wrote, not the valid one it mentioned"
    code = "import sys; sys.path.insert(0, %r); import critic_findings as c; [c.proctor_mark(%r, 'race') for _ in range(10)]" % (str(S), str(d))
    procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(4)]
    for p_ in procs: p_.wait()
    assert sum(1 for v in json.loads(pr.read_text(encoding="utf-8"))["marks"].values() if v["what"] == "race") == 40, "four writers at once lose no mark"
    g = d / "g"; write(g, "src/app.js", APP); subprocess.run(["git", "init", "-q"], cwd=g); subprocess.run(["git", "add", "-A"], cwd=g); subprocess.run(G9 + ["commit", "-qm", "x"], cwd=g)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=g); wsg = _ws(g)["payload"]
    secret = write(d, "outside-secret.txt", "TOP-SECRET\n")
    r = run(S / "critic_proctor.py", "ask", "git", "blame", "--contents", str(secret), "--", "src/app.js", cwd=pathlib.Path(wsg), env={"CRITIC_ROOT": ""})
    assert r.returncode == 2 and "TOP-SECRET" not in r.stdout, "git blame --contents is refused"

# 5.6.0: the sandbox switch (03 §5.57 items 17 and 20).

@test("5.6.0 sandbox switch: begin asks for the two-step probe; the probe prints a code, recorded outside the sandbox against the token: the token's hash is tripwire-only, MISSING or REFUSED with the token there is os-enforced, once per run; a shipped folder can't forge it")
def _(d):
    write(d, "src/app.js", APP); (d / ".critic/proctor/probe.txt").mkdir(parents=True)  # a repository ships a folder where the token goes
    out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d).stdout
    assert re.search(r"boundary check, now, in two commands\. First, exactly as written .*: cd \S+ && \S+ \S*critic_run\.py probe; then, without a cd", out), out
    assert (d / ".critic/proctor/probe.txt").is_file(), "begin replaces whatever stood where the token goes"
    r = run(S / "critic_run.py", "probe", cwd=d); code = re.search(r"boundary probe: (SAW [0-9a-f]{16}|MISSING|REFUSED)", r.stdout).group(1)
    assert code.startswith("SAW ") and f"boundary-record {code}" in r.stdout and not (d / ".critic/boundary.json").exists(), r.stdout
    assert run(S / "critic_run.py", "boundary-record", "SAW 0000000000000000", cwd=d).returncode != 0, "a code that isn't the token's"
    r = run(S / "critic_run.py", "boundary-record", *code.split(), cwd=d); assert "boundary: tripwire-only" in r.stdout, r.stdout + r.stderr
    assert run(S / "critic_run.py", "boundary-record", "MISSING", cwd=d).returncode != 0, "one record per run: tripwire-only stays"
    write(d, ".critic/reviews/review-A.json", "[]"); run(S / "critic_run.py", "next", "--no-scan", cwd=d); run(S / "critic_run.py", "next", "--no-scan", cwd=d)
    assert "Boundary: tripwire-only" in (d / ".critic/counts.md").read_text(encoding="utf-8")
    time.sleep(0.05); run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d)
    assert "boundary: os-enforced" in run(S / "critic_run.py", "boundary-record", "MISSING", cwd=d).stdout, "the sandbox's empty folder on Linux and WSL2"
    ws = _ws(d)["payload"]
    assert run(S / "critic_run.py", "probe", cwd=pathlib.Path(ws), env={"CRITIC_ROOT": ""}).returncode != 0, "a reviewer's copy can't run the probe"
    for cmd in (f"cd {ws} && python3 {S / 'critic_run.py'} probe", f"cd {ws} && python3 {S / 'critic_run.py'} boundary-record MISSING", f"cd {ws} && python3 {S / 'critic_ledger.py'} boundary off"):
        assert "deny" in _rg(d, "Bash", command=cmd), cmd
    w = d / "w"; write(w, "x.txt", "x\n")
    try: os.symlink(w / "x.txt", d / ".claude" / ".settings.planted.tmp") if (d / ".claude").mkdir() is None else None; linked = True
    except (OSError, NotImplementedError): linked = False
    write(d, ".claude/settings.local.json.tmp", "planted\n")
    assert run(S / "critic_ledger.py", "boundary", "write", cwd=d).returncode == 0 and (w / "x.txt").read_text(encoding="utf-8") == "x\n", "a planted temp file or link is never written through"

@test("5.6.0 sandbox switch: require holds every reviewer until the boundary is os-enforced; off skips the check; the settings are printed with absolute paths and written only by boundary write, merged into what is there")
def _(d):
    write(d, "src/app.js", APP)
    assert run(S / "critic_ledger.py", "boundary", "require", cwd=d).returncode == 0
    out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d).stdout
    assert "requires the OS boundary" in out and "start 1 curmudgeon" not in out, out
    s = run(S / "critic_run.py", "status", cwd=d).stdout; assert "hasn't been checked" in s and "start 1" not in s, s
    run(S / "critic_run.py", "boundary-record", "REFUSED", cwd=d)
    assert "start 1 curmudgeon:curmudgeon-reviewer" in run(S / "critic_run.py", "status", cwd=d).stdout
    time.sleep(0.05); out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d).stdout
    assert "requires the OS boundary" in out, ("an earlier run's os-enforced record doesn't open this run", out)
    run(S / "critic_ledger.py", "boundary", "off", cwd=d)
    out = run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d).stdout
    assert "boundary check" not in out and "start 1 curmudgeon" in out, out
    st = run(S / "critic_run.py", "boundary-settings", cwd=d).stdout
    j = json.loads(st[st.index("{"):])["sandbox"]
    assert j["enabled"] is True and j["allowUnsandboxedCommands"] is False and j["autoAllowBashIfSandboxed"] is False and "./.critic" in j["filesystem"]["denyRead"], j
    assert "*/skills/review/scripts/critic_*.py *" in j["excludedCommands"] and "*/skills/review/scripts/security_feed.py *" in j["excludedCommands"], j["excludedCommands"]
    assert "a new Claude Code session" in st and "only after the user says yes" in st and "theirs included" in st
    write(d, ".claude/settings.local.json", json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "sandbox": {"filesystem": {"denyRead": ["~/.aws"]}}}))
    assert run(S / "critic_ledger.py", "boundary", "write", cwd=d).returncode == 0
    w = json.loads((d / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert w["permissions"] == {"allow": ["Bash(ls)"]} and w["sandbox"]["filesystem"]["denyRead"][:2] == ["~/.aws", "./.critic"] and w["sandbox"]["enabled"] is True, w
    write(d, ".claude/settings.local.json", "{not json")
    assert run(S / "critic_ledger.py", "boundary", "write", cwd=d).returncode != 0 and (d / ".claude/settings.local.json").read_text(encoding="utf-8") == "{not json"

@test("5.6.0 blind round: the request command fails closed when it can't read the run marks (Claude Code's sandbox hides .critic/): files and listings are refused, git still works")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); subprocess.run(["git", "init", "-q"], cwd=p); subprocess.run(["git", "add", "-A"], cwd=p); subprocess.run(G9 + ["commit", "-qm", "first"], cwd=p)
    run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=p); ws = _ws(p)["payload"]; other = write(d, "elsewhere/lib.py", "x = 1\n")
    (p / ".critic/proctor/marks.json").rename(p / ".critic/proctor/marks.hidden")  # as the sandbox's empty folder shows it
    ask = lambda *a: run(S / "critic_proctor.py", "ask", *a, cwd=pathlib.Path(ws), env={"CRITIC_ROOT": ""})
    assert ask("read", str(other)).returncode == 2 and ask("list", str(d / "elsewhere")).returncode == 2
    r = ask("git", "log", "--oneline"); assert r.returncode == 0 and "first" in r.stdout, r.stderr
