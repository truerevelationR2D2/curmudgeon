"""Curmudgeon's script tests, part 4: the fixes from the combined review of 29 Oct 2026 (03 §5.56). Run
plugin/tests/run_tests.py, which defines the helpers and runs every part. Not runnable on its own. Each test here
failed on the code before the fix."""

def _guard(p, cwd, tool, role="reviewer", aid="r1", **ti):
    return "deny" in run(H / "read_guard.py", cwd=p, stdin=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(cwd), "agent_type": f"curmudgeon:curmudgeon-{role}", "agent_id": aid})).stdout

def _tally3(d, a, b, c, *extra):
    for L_, rows in zip("ABC", (a, b, c)): write(d, f".critic/reviews/review-{L_}.json", json.dumps(rows))
    r = run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{x}.json" for x in "ABC"], *extra, cwd=d)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((d / ".critic/tally.json").read_text())

@test("§5.56 item 1: critic_run.py feeds the scan's FAILs to the tally, waits for this run's scan, and --no-scan marks the run DEGRADED")
def _(d):
    write(d, "src/a.js", "function go(input) {\n  return eval(input);\n}\n")
    run(S / "critic_run.py", "begin", "--files", "src/a.js", "--tier", "lite", cwd=d)
    write(d, ".critic/reviews/review-A.json", "[]")
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "have not written a report" in out and not (d / ".critic/tally.json").exists(), "the tally waits for this run's scan: " + out
    run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    assert any(r["rule"] == "eval" and r["sev"] == "FAIL" for r in json.loads((d / ".critic/scan/report.json").read_text())["findings"])
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    t = json.loads((d / ".critic/tally.json").read_text())
    assert [(f["category"], f["impact"]) for f in t["kept"] + t["contested"]] == [("eval", "High")], out
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]; assert len(ids) == 1, ids
    write(d, ".critic/verdicts/v1.json", json.dumps([{"id": ids[0], "verdict": "confirmed", "reproduced": "traced", "entry": "go() is exported", "path": ["src/a.js:2 passes input to eval"]}]))
    run(S / "critic_run.py", "next", cwd=d)
    assert "Critical 0 · High 1 · Medium 0 · Low 0 · total 1" in (d / ".critic/counts.md").read_text(), (d / ".critic/counts.md").read_text()
    e = d / "noscan"; write(e, "src/a.js", "function go(input) {\n  return eval(input);\n}\n")
    run(S / "critic_run.py", "begin", "--files", "src/a.js", "--tier", "lite", cwd=e); write(e, ".critic/reviews/review-A.json", "[]")
    run(S / "critic_run.py", "next", "--no-scan", cwd=e)
    c = (e / ".critic/counts.md").read_text()
    assert c.splitlines()[2].startswith("DEGRADED: the scripted checks did not run"), c

@test("§5.56 item 2: the read guard follows each cd, so a chain of cd .. can't walk a reviewer into .critic/reviews, and ordinary work isn't refused")
def _(d):
    p = d / "proj"; write(p, "src/app.js", APP); write(p, ".critic/reviews/review-B.json", '[{"title": "SECRET-B"}]')
    run(H / "scratch_dir.py", cwd=p, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-reviewer", "agent_id": "r1", "cwd": str(p)}))
    ws = json.loads((p / ".critic/scratch/r1/workspace.json").read_text())["payload"]
    for cmd in (f"cd {ws} && cd .. && cd .. && cd .. && cd reviews && cat review-B.json",
                f"cd {ws} && cd ..; cd ..; cd ..; cat reviews/review-B.json",
                f"cd {ws} && for i in 1 2 3; do cd ..; done; cat reviews/review-B.json",
                f"cd {ws} && (cd ../../.. && cat reviews/review-B.json)",
                f"cd {ws} && pushd .. && cat x",
                f"cd {ws} && \\cd .. && \\cd .. && \\cd .. && cat reviews/review-B.json",   # round 1: spellings the shell undoes
                f"cd {ws} && c''d .. && c''d .. && c''d .. && cat reviews/review-B.json",
                f"cd {ws} && {{cd,..}} && cat x", f"cd {ws} && cd${{IFS}}..",
                f"cd {ws} && cd src && cd ../.. && cat x", f"cd {ws} && bash -c 'cd ../../.. && cat reviews/review-B.json'", f"cd {ws} && cd",
                # round 2: cd forms the guard can't follow, subshells and failed cds, ways back
                f"cd {ws} && builtin cd .. && builtin cd .. && builtin cd .. && cat reviews/review-B.json", f"cd {ws} && command cd ..", f"cd {ws} && X=1 cd ..",
                f"cd {ws} && time cd ..", f"cd {ws} && eval cd ..", f"cd {ws} && $'cd' ..", f"cd {ws} && if cd ..; then ls; fi", f"cd {ws} && while cd ..; do break; done",
                f"cd {ws} && ls\ncd ..\ncd ..\ncd ..\ncat reviews/review-B.json", f"cd {ws} && cd -P ..", f"cd {ws} && cd -- ..",
                f"cd {ws} && bash -lc 'cd ../../.. && cat reviews/review-B.json'", f"cd {ws} && sh -ec 'cat ../../../reviews/review-B.json'",
                f"cd {ws} && (cd src/a/b && ls) && cat ../../../reviews/review-B.json", f"cd {ws} && cd no/such/dir 2>/dev/null; cat ../../../reviews/review-B.json",
                f"cd {ws} && echo $(cd src) && cat ../../reviews/review-B.json", f"cd {ws} && cd ~- && cat .critic/reviews/review-B.json", f"cd {ws} && cat ~-/.critic/reviews/review-B.json"):
        assert _guard(p, p, "Bash", command=cmd), cmd
    write(pathlib.Path(ws), "deploy.sh", "cd /srv && ./run\n")
    os.symlink(p / "src", pathlib.Path(ws) / "linked")  # like node_modules: a link in the copy to the project's own folder
    for cmd in (f"cd {ws} && cat src/app.js && grep -rn innerHTML src", f"cd {ws} && grep -n 'cd ' deploy.sh", f"cd {ws} && grep -rn chdir src",
                f"cd {ws} && cd src && ls", f"cd {ws} && (cd src && ls) && cat deploy.sh", f"cd {ws} && git log --oneline | grep cd",
                f"cd {ws} && cd linked && ls", f"cd {ws} && ls ../notes", f"cd {ws} && grep -rn '$IFS' src", f"cd {ws} && grep -n 'cd ..' deploy.sh"):
        assert not _guard(p, p, "Bash", command=cmd), "ordinary work in the copy still runs: " + cmd

@test("§5.56 item 3: the quote check is strict: the cited line or one either side, case and quote marks kept, at least 12 characters with a name, never line 0")
def _(d):
    from critic_findings import quote_check, validate
    write(d, "src/m.js", "\n".join([f"const value{i} = compute({i});" for i in range(1, 6)] + ["", "  return Total.amount;", "", "  if (ok) {", "    save(item);", "  }"]) + "\n")
    q = lambda line, quote: quote_check({"file": "src/m.js", "line": line, "quote": quote}, d)
    assert q(7, "return Total.amount;") and q(6, "return Total.amount;") and q(8, "return Total.amount;"), "the cited line, or one either side"
    assert not q(3, "return Total.amount;") and not q(10, "return Total.amount;"), "four lines off is not at the cited line"
    assert not q(7, "return total.amount;"), "case counts"
    assert not q(0, "return Total.amount;"), "line 0 is never confirmed"
    assert q(9, "if (ok) {\n    save(item);\n  }") and not q(9, "save(item);\nif (ok) {"), "a multi-line quote must be in order, line after line"
    assert q(7, "return   Total.amount;"), "runs of spaces are evened out"
    bad = lambda **k: validate(dict(finding(file="src/m.js"), **k))
    assert any("too short" in e for e in bad(quote=";", line=7)), "a one-character quote proves nothing"
    assert any("too short" in e for e in bad(quote="return", line=7))
    assert any("line number" in e for e in bad(quote="return Total.amount;", line=0)), "a quoted finding needs its line"
    assert not bad(quote="return Total.amount;", line=7)

@test("§5.56 item 4: when reviewers disagree on the impact, the finding is filed at the highest and always gets a verify packet")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    t = _tally3(d, [finding(impact="Critical")], [finding(impact="Low")], [])
    k = t["kept"]; assert len(k) == 1 and k[0]["impact"] == "Critical" and k[0]["impact_split"] == ["Critical", "Low"], k
    assert (d / ".critic/verify" / f"{k[0]['id']}.json").exists(), "a split impact is verified; the verifier may lower it"

@test("§5.56 item 5: one reviewer's two findings never merge through a third finding that resembles both")
def _(d):
    write(d, "src/app.js", "\n".join(f"// line {i}" for i in range(1, 10)) + "\nfunction pay(amount, to) {\n  db.write(amount);\n  const x = 1;\n  validateLater();\n  sendPayment(to, amount);\n}\n")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    a1 = finding(category="validation", impact="High", line=11, quote="db.write(amount);", title="amount not validated before write", failing_case="amount -5 is written")
    a2 = finding(category="validation", impact="High", line=14, quote="sendPayment(to, amount);", title="recipient not validated before send", failing_case="an empty recipient is sent")
    b1 = finding(category="validation", impact="High", line=13, quote="validateLater();", title="amount and recipient not validated before write and send", failing_case="bad input is written and sent")
    from critic_findings import similar
    assert similar(a1, b1) and similar(a2, b1), "the fixture needs B's finding to resemble both of A's"
    t = _tally3(d, [a1, a2], [b1], [])
    titles = sorted(f["title"] for f in t["kept"] + t["contested"] + [x["finding"] for x in t["dropped"]])
    assert "amount not validated before write" in titles and "recipient not validated before send" in titles, titles

@test("§5.56 item 6: a reviewer's own 'executed' never makes a finding 'confirmed' when no verifier reproduced or confirmed it")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    t = _tally3(d, [finding(impact="High", verified="executed")], [], [])
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]; assert ids, t
    write(d, "v.json", json.dumps([{"id": i, "verdict": "unclear", "reproduced": "no"} for i in ids]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    f = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines() if x.strip()]
    assert [(x["verifier"], x["confidence"]) for x in f] == [("unclear", "likely")], f
    write(d, "v.json", json.dumps([{"id": i, "verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on load", "path": ["src/app.js:2 writes the title as HTML"]} for i in ids]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    f = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines() if x.strip()]
    assert f[0]["confidence"] == "confirmed", "confirmed by the verifier, executed by the reviewer: confirmed"

@test("§5.56 item 7: the tier's verification policy is enforced: not-in-tier is labelled, a missing required verdict marks the run DEGRADED, and only script-matched all-Low agreement skips verification")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=d)
    write(d, ".critic/reviews/review-A.json", json.dumps([finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="Tax rule in render code", verified="executed")]))
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", cwd=d); write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    f = [json.loads(x) for x in (d / ".critic/findings.jsonl").read_text().splitlines() if x.strip()]
    c = (d / ".critic/counts.md").read_text()
    assert f[0]["verifier"] == "not-in-tier" and f[0]["confidence"] == "likely" and "DEGRADED" not in c and "no verdict returned" not in c, (f, c)
    e = d / "full"; write(e, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    _tally3(e, [finding(impact="High")], [finding(impact="High")], []); write(e, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=e)
    c = (e / ".critic/counts.md").read_text()
    assert "DEGRADED: 1 verdict(s) the full tier requires never came back" in c, c
    g = d / "lows"; write(g, "src/app.js", APP + "const unused = 0;\n"); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=g)
    lo = dict(finding(category="style", impact="Low", line=4, quote="const price = total * 1.0825;", title="magic number for the tax rate"))
    t = _tally3(g, [lo], [dict(lo, title="tax rate written as a magic number")], [])
    assert t["kept"] and t["kept"][0]["votes_matched"] == 2 and not list((g / ".critic/verify").glob("*.json")), "agreed Lows the script matched itself still skip verification"
    x1 = finding(category="style", impact="Low", line=2, quote="list.innerHTML = `<li>${n.title}</li>`;", title="template string builds markup")
    x2 = finding(category="naming", impact="Low", line=5, quote="const unused = 0;", title="unused constant left behind")
    t = _tally3(g, [x1], [x2], [])
    raw = [it["id"] for v in json.loads((g / ".critic/dedup-candidates.json").read_text())["findings_by_file"].values() for it in v]
    write(g, ".critic/groups.json", json.dumps({"groups": [raw]}))
    t = _tally3(g, [x1], [x2], [], "--groups", ".critic/groups.json")
    assert t["kept"] and t["kept"][0]["votes"] == 2 and t["kept"][0]["votes_matched"] == 1, t["kept"]
    assert list((g / ".critic/verify").glob("*.json")), "two Lows joined only by the dedup agent are verified"

@test("§5.56 item 8: the stop hook saves a verifier's verdicts unchanged, verdict folders can't be edited directly, and stamp checks the teardown against counts.md")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    write(d, ".critic/verify/F-1.json", json.dumps({"id": "F-1", "impact": "Low"}))
    msg = 'Done.\n```json\n[{"id": "F-1", "verdict": "unclear", "reproduced": "no"}]\n```\n'
    run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v7", "cwd": str(d), "last_assistant_message": msg}))
    saved = d / ".critic/verdicts/v7.json"
    assert saved.exists() and json.loads(saved.read_text()) == [{"id": "F-1", "verdict": "unclear", "reproduced": "no"}], "the verdict list is saved as the verifier returned it"
    deny = run(H / "guard_state.py", cwd=d, stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(d / ".critic/verdicts/1.json")}, "cwd": str(d)})).stdout
    assert "deny" in deny, "a verdict can't be typed in by hand"
    t = _tally3(d, [finding(impact="High")], [finding(impact="High")], [])
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]
    write(d, "v.json", json.dumps([{"id": i, "verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on load", "path": ["src/app.js:2 writes the title as HTML"]} for i in ids]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    tear = lambda first, sec: write(d, ".critic/last-review.md", f"{first}\n\n#### 5. VERDICT\n- **BLOCK**\n- {sec}\n")
    tear("**CLEAN** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low", "Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = run(S / "critic_ledger.py", "stamp", "src", cwd=d); assert r.returncode != 0 and "CLEAN with an open Critical or High" in r.stderr + r.stdout, r.stdout + r.stderr
    tear("**BLOCK** · Counts: 0 Critical, 0 High, 0 Medium, 0 Low", "Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = run(S / "critic_ledger.py", "stamp", "src", cwd=d); assert r.returncode != 0 and "are not counts.md's" in r.stderr + r.stdout, r.stdout + r.stderr
    tear("**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low", "Counts: 0 Critical, 2 High, 0 Medium, 0 Low")
    r = run(S / "critic_ledger.py", "stamp", "src", cwd=d); assert r.returncode != 0 and "VERDICT section's Counts line" in r.stderr + r.stdout, r.stdout + r.stderr
    tear("**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low", "Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = run(S / "critic_ledger.py", "stamp", "src", cwd=d); assert r.returncode == 0, r.stdout + r.stderr
    c = (d / ".critic/counts.md").read_text(); (d / ".critic/counts.md").write_text(c.replace("# Curmudgeon merged findings\n", "# Curmudgeon merged findings\n\nDEGRADED: test\n", 1))
    tear("**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low", "Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = run(S / "critic_ledger.py", "stamp", "src", cwd=d); assert r.returncode != 0 and "DEGRADED" in r.stderr + r.stdout, r.stdout + r.stderr


@test("§5.56 round 1: a scan or outside answer that arrives after the dedup step keeps the dedup groups, and outside rows never split our agreed finding")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "full", cwd=d); run(S / "critic_scan.py", ".", "--root", ".", cwd=d)
    x1 = finding(category="domain", impact="Medium", line=4, quote="const price = total * 1.0825;", title="tax rate hard-coded in render code")
    x2 = finding(category="config", impact="Medium", line=4, quote="price = total * 1.0825", title="pricing constant duplicated instead of shared")
    for L_, rows in zip("ABC", ([x1], [x2], [])): write(d, f".critic/reviews/review-{L_}.json", json.dumps(rows))
    run(S / "critic_run.py", "next", cwd=d)
    raw = [it["id"] for v in json.loads((d / ".critic/dedup-candidates.json").read_text())["findings_by_file"].values() for it in v]
    write(d, ".critic/groups.json", json.dumps({"groups": [raw]})); run(S / "critic_run.py", "next", cwd=d)
    kept = lambda: [(f["title"], f["votes"]) for f in json.loads((d / ".critic/tally.json").read_text())["kept"]]
    assert len(kept()) == 1 and kept()[0][1] == 2, kept()
    write(d, ".critic/outside/outside-review.json", "[]"); run(S / "critic_run.py", "next", cwd=d)
    assert len(kept()) == 1 and kept()[0][1] == 2, "the rerun tally for the late outside answer kept the groups: " + str(kept())
    e = d / "split"; write(e, "src/app.js", "\n".join(f"// {i}" for i in range(1, 9)) + "\n" + APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    q = "list.innerHTML = `<li>${n.title}</li>`;"
    ours = [finding(line=10, quote=q, title=f"Title rendered as HTML ({k})") for k in "abc"]
    outs = [dict(finding(line=10, quote=q, title="Title rendered as HTML here"), source="outside", outside_id="N1"), dict(finding(line=10, quote=q, title="Title rendered as HTML again"), source="outside", outside_id="N2")]
    write(e, "o.json", json.dumps(outs))
    t = _tally3(e, [ours[0]], [ours[1]], [ours[2]], "--outside", "o.json")
    assert len(t["kept"]) == 1 and t["kept"][0]["votes_ours"] == 3, [(f["title"], f["votes"], f.get("votes_ours")) for f in t["kept"]]

@test("§5.56 round 1: stamp needs this run's teardown, written after counts.md, with the same word in section 5, either counts format, and counts.md's DEGRADED reason")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    _tally3(d, [finding(impact="High")], [finding(impact="High")], [])
    ids = [p.stem for p in (d / ".critic/verify").glob("*.json")]
    write(d, "v.json", json.dumps([{"id": i, "verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on load", "path": ["src/app.js:2 writes the title as HTML"]} for i in ids]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    stamp = lambda: run(S / "critic_ledger.py", "stamp", "src", cwd=d)
    r = stamp(); assert r.returncode != 0 and "no .critic/last-review.md" in r.stdout + r.stderr, r.stdout + r.stderr
    tear = lambda first, w5="BLOCK", c5="Counts: 0 Critical, 1 High, 0 Medium, 0 Low": write(d, ".critic/last-review.md", f"{first}\n\n#### 5. VERDICT\n- **{w5}**\n- {c5}\n- Panel: 2 reviewers\n")
    tear("**BLOCK** · Counts: Critical 0 · High 1 · Medium 0 · Low 0 · total 1", c5="Counts: Critical 0 · High 1 · Medium 0 · Low 0 · total 1")
    r = stamp(); assert r.returncode == 0, "counts.md's own format is accepted: " + r.stdout + r.stderr
    tear("**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low", w5="CLEAN")
    r = stamp(); assert r.returncode != 0 and "VERDICT section says CLEAN" in r.stdout + r.stderr, r.stdout + r.stderr
    tear("**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    old = time.time() - 60; os.utime(d / ".critic/last-review.md", (old, old))
    r = stamp(); assert r.returncode != 0 and "older than counts.md" in r.stdout + r.stderr, r.stdout + r.stderr
    c = (d / ".critic/counts.md").read_text(); (d / ".critic/counts.md").write_text(c.replace("# Curmudgeon merged findings\n", "# Curmudgeon merged findings\n\nDEGRADED: 1 verdict(s) the full tier requires never came back (F-x)\n", 1))
    tear("DEGRADED: single context (no subagents)\n**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = stamp(); assert r.returncode != 0 and "doesn't carry that reason" in r.stdout + r.stderr, r.stdout + r.stderr
    tear("**DEGRADED:** single context; 1 verdict(s) the full tier requires never came back (F-x)\n**BLOCK** · Counts: 0 Critical, 1 High, 0 Medium, 0 Low")
    r = stamp(); assert r.returncode == 0, r.stdout + r.stderr

@test("§5.56 round 1: a scripted High that reviewers call Low is a split impact; scripted measurements stay confirmed; fresh follows moved code; Unicode quotes; outside line ranges; strict relocation")
def _(d):
    from critic_findings import validate, relocate_quote
    write(d, "src/a.js", "function go(input) {\n  return eval(input);\n}\n"); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    write(d, "scan.json", json.dumps({"findings": [{"id": "S001", "rule": "eval", "sev": "FAIL", "where": "src/a.js:2", "what": "eval / new Function", "evidence": "eval(input)"}]}))
    lo = finding(category="eval", impact="Low", file="src/a.js", line=2, quote="return eval(input);", title="eval of input")
    t = _tally3(d, [lo], [dict(lo, title="input passed to eval")], [], "--scan", "scan.json")
    k = t["kept"]; assert len(k) == 1 and k[0]["impact"] == "High" and k[0]["impact_split"] == ["High", "Low"] and (d / ".critic/verify" / f"{k[0]['id']}.json").exists(), k
    e = d / "m"; write(e, "index.html", "<p>x</p>\n"); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    write(e, "scan.json", json.dumps({"findings": [{"id": "S002", "rule": "axe-color-contrast", "sev": "FAIL", "level": "runtime", "where": "index.html:1", "what": "low contrast", "evidence": "1.6:1"}]}))
    _tally3(e, [], [], [], "--scan", "scan.json"); write(e, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=e)
    f = [json.loads(x) for x in (e / ".critic/findings.jsonl").read_text().splitlines() if x.strip()]
    assert [x["confidence"] for x in f] == ["confirmed"], f
    g = d / "fresh"; write(g, "src/p.js", "function f(a) {\n  if (a > 0) {\n    db.write(a);\n  }\n}\n"); run(S / "critic_ledger.py", "start", "review", cwd=g)
    write(g, ".critic/findings.jsonl", json.dumps(dict(finding(file="src/p.js", line=2, quote="if (a > 0) {\n    db.write(a);"), id="F-1")) + "\n")
    assert run(S / "critic_ledger.py", "fresh", "F-1", cwd=g).returncode == 0
    write(g, "src/p.js", "import a from 'a';\nimport b from 'b';\nfunction f(a) {\n  if (a > 0) {\n    db.write(a);\n  }\n}\n")
    r = run(S / "critic_ledger.py", "fresh", "F-1", cwd=g); assert r.returncode == 0 and "moved to src/p.js:4" in r.stdout, r.stdout
    assert not validate(dict(finding(file="docs/ru/README.md", line=3), quote="Установка занимает пять минут")), "a quote in another script has words in it"
    h = d / "out"; write(h, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", cwd=h)
    write(h, "ans.txt", "```json\n" + json.dumps([{"id": "N1", "impact": "High", "category": "xss", "file": "src/app.js", "line": "2-3", "quote": "list.innerHTML = `<li>${n.title}</li>`;", "title": "XSS", "evidence": "e", "failing_case": "c", "verified": "traced"}]) + "\n```\n")
    run(S / "critic_outside.py", "load", "ans.txt", cwd=h)
    assert json.loads((h / ".critic/outside/outside-review.json").read_text())[0]["line"] == 2, "a line range keeps its first line"
    assert relocate_quote({"file": "src/app.js", "line": 9, "quote": "LIST.INNERHTML = `<LI>${N.TITLE}</LI>`;"}, h) is None and relocate_quote({"file": "src/app.js", "line": 9, "quote": "list.innerHTML = `<li>${n.title}</li>`;"}, h) == 2


@test("§5.56 round 2: the split follows similarity, not just line distance, a reviewer's repeat is one finding, and matched votes are counted per group")
def _(d):
    write(d, "src/app.js", "\n".join(f"// line {i}" for i in range(1, 10)) + "\nfunction pay(amount, to) {\n  db.write(amount);\n  const x = 1;\n  validateLater();\n  sendPayment(to, amount);\n}\n")
    run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    a1 = finding(category="validation", impact="High", line=11, quote="db.write(amount);", title="amount not validated before write", failing_case="amount -5 is written")
    a2 = finding(category="validation", impact="High", line=14, quote="sendPayment(to, amount);", title="recipient not validated before send", failing_case="an empty recipient is sent")
    b1 = finding(category="validation", impact="High", line=13, quote="validateLater();", title="amount and recipient not validated before write and send", failing_case="bad input is written and sent")
    c1 = dict(a2, line=10, quote="function pay(amount, to) {")
    from critic_findings import similar
    assert similar(c1, a2) and not similar(c1, a1)
    t = _tally3(d, [a1, a2], [b1], [c1])
    kept = {f["title"]: f["votes"] for f in t["kept"]}; live = kept | {f["title"]: f["votes"] for f in t["contested"]}
    assert kept.get("recipient not validated before send", 0) >= 2, kept  # C's vote goes to the finding it resembles, not the nearest line
    assert "amount not validated before write" in live, (kept, live)  # A's other finding is kept or verified, never dropped
    e = d / "dup"; write(e, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    t = _tally3(e, [finding(), finding(title="Title rendered as HTML without escaping")], [finding()], [finding()])
    ids = [f["id"] for f in t["kept"] + t["contested"]]
    assert len(ids) == 1 and t["kept"][0]["votes"] == 3, [(f["id"], f["votes"]) for f in t["kept"] + t["contested"]]

@test("§5.56 round 2: a missing outside-only verdict marks the run DEGRADED, verdicts older than the tally are never applied, rounds archive verdicts, and measurements stay confirmed with a reviewer")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=d)
    write(d, "o.json", json.dumps([dict(finding(category="domain", impact="High", line=4, quote="const price = total * 1.0825;", title="Tax applied twice"), source="outside", outside_id="N1")]))
    _tally3(d, [], [], [], "--outside", "o.json"); write(d, "v.json", "[]"); run(S / "critic_merge.py", "apply", "v.json", cwd=d)
    assert "DEGRADED: 1 verdict(s) the full tier requires" in (d / ".critic/counts.md").read_text(), (d / ".critic/counts.md").read_text()[:400]
    e = d / "stale"; write(e, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", "full", cwd=e)
    _tally3(e, [finding(impact="High")], [finding(impact="High")], [])
    fid = [p.stem for p in (e / ".critic/verify").glob("*.json")][0]
    write(e, ".critic/verdicts/old.json", json.dumps([{"id": fid, "verdict": "refuted", "refutation": "src/app.js:2 escapes the title first", "reproduced": "traced"}]))
    old = time.time() - 600; os.utime(e / ".critic/verdicts/old.json", (old, old))
    run(S / "critic_merge.py", "apply", ".critic/verdicts/old.json", cwd=e)
    c = (e / ".critic/counts.md").read_text()
    assert "High 1" in c and "not applied, older than this tally: old.json" in c, c[:600]
    run(S / "critic_ledger.py", "round", cwd=e)
    assert not (e / ".critic/verdicts").exists() and list((e / ".critic/history").glob("*/verdicts/old.json")), "a new round starts without the last round's verdicts"
    g = d / "meas"; write(g, "index.html", "<p class=\"hint\">enter a value now</p>\n"); run(S / "critic_ledger.py", "start", "review", "--tier", "lite", cwd=g)
    write(g, "scan.json", json.dumps({"findings": [{"id": "S002", "rule": "axe-color-contrast", "sev": "FAIL", "level": "runtime", "where": "index.html:1", "what": "low contrast", "evidence": "enter a value now"}]}))
    write(g, ".critic/reviews/review-A.json", json.dumps([finding(category="axe-color-contrast", impact="High", file="index.html", line=1, quote="<p class=\"hint\">enter a value now</p>", title="hint text has low contrast")]))
    run(S / "critic_merge.py", "tally", ".critic/reviews/review-A.json", "--scan", "scan.json", cwd=g)
    ids = [p.stem for p in (g / ".critic/verify").glob("*.json")]
    write(g, "v.json", json.dumps([{"id": i, "verdict": "confirmed", "reproduced": "traced", "entry": "the page loads", "path": ["index.html:1 renders the hint in #ccc"]} for i in ids]))
    run(S / "critic_merge.py", "apply", "v.json", cwd=g)
    f = [json.loads(x) for x in (g / ".critic/findings.jsonl").read_text().splitlines() if x.strip()]
    assert [x["confidence"] for x in f] == ["confirmed"], [(x.get("raised_by"), x["confidence"]) for x in f]

@test("§5.56 round 2: waiting for a scan names the command to run, the outside brief allows a two-line quote for a short line, and a variant verdict is judged against its own packet")
def _(d):
    write(d, "src/app.js", APP); run(S / "critic_run.py", "begin", "--files", "src/app.js", "--tier", "lite", cwd=d); write(d, ".critic/reviews/review-A.json", "[]")
    out = run(S / "critic_run.py", "next", cwd=d).stdout
    assert "critic_scan.py . --root ." in out, out
    assert "under 12 characters, quote it together with the next line" in (S / "critic_outside.py").read_text()
    write(d, ".critic/verify-variants/V-abc-1.json", json.dumps({"id": "V-abc-1", "impact": "Low", "category": "style", "file": "src/app.js", "line": 2}))
    msg = 'x\n```json\n[{"id": "V-abc-1", "verdict": "refuted", "refutation": "src/app.js:1 defines render() only for the admin page, which escapes every title before this line runs.", "reproduced": "traced"}]\n```\n'
    r = run(H / "check_contract.py", cwd=d, stdin=json.dumps({"agent_type": "curmudgeon:curmudgeon-verifier", "agent_id": "v9", "cwd": str(d), "last_assistant_message": msg}))
    assert '"block"' not in r.stdout, "a Low variant's refutation is held to the Low rules, not the Critical ones: " + r.stdout
    assert (d / ".critic/verdicts-variants/v9.json").exists()
