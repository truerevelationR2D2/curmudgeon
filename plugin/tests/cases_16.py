"""Curmudgeon's script tests, part 16: release 5.10.2, winning back the recall the vote stage lost (ruling 61; evidence:
the Project's "Milestones 24 Nov 2026 - 4.2.2 to 5.10.1"). Run plugin/tests/run_tests.py, which defines the helpers
and runs every part. Not runnable on its own."""

def _tally16(e, rows_by_letter, tier="full"):
    write(e, "src/app.js", APP); run(S / "critic_ledger.py", "start", "review", "--tier", tier, cwd=e)
    letters = "ABC" if tier == "full" else "A"
    for L in letters: write(e, f".critic/reviews/review-{L}.json", json.dumps(rows_by_letter.get(L, [])))
    run(S / "critic_merge.py", "tally", *[f".critic/reviews/review-{L}.json" for L in letters], cwd=e)
    return json.loads((e / ".critic/tally.json").read_text(encoding="utf-8"))

def _apply16(e, t, verdict):
    rows = [dict(verdict, id=t["contested"][0]["id"])] if verdict else []
    vp = hook_verdicts(e, rows); run(S / "critic_merge.py", "apply", str(vp), cwd=e)
    return [json.loads(x) for x in (e / ".critic/findings.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

LOW16 = dict(category="domain", impact="Low", line=4, quote="const price = total * 1.0825;", title="Tax rate hard-coded in render code")

@test("ruling 61 (1): a Low only one of three reviewers raised, with a checked quote, goes to one blind verifier instead of being dropped, and is kept only if it confirms")
def _(d):
    t = _tally16(d / "a", {"A": [finding(**LOW16)]})
    assert not t["dropped"], ("a quoted single-vote Low is no longer dropped unverified (the milestones lost planted bugs this way)", t["dropped"])
    assert len(t["contested"]) == 1 and t["contested"][0].get("single_vote"), t["contested"]
    assert (d / "a/.critic/verify" / f"{t['contested'][0]['id']}.json").exists(), "it gets a verifier packet"
    good = {"verdict": "confirmed", "reproduced": "traced", "entry": "render() runs on every update", "path": ["src/app.js:4 multiplies by a hard-coded rate"]}
    assert len(_apply16(d / "a", t, good)) == 1, "confirmed: kept"
    for name, v in (("b", {"verdict": "unclear", "reproduced": "no"}), ("c", None), ("e", {"verdict": "refuted", "guard": "src/app.js:4"})):
        t = _tally16(d / name, {"A": [finding(**LOW16)]})
        assert _apply16(d / name, t, v) == [], (name, "anything but a confirmation drops it: no Low is kept on one vote alone")
    t = _tally16(d / "f", {"A": [finding(**dict(LOW16, line=0, quote=""))]})
    assert not t["contested"] and t["dropped"], ("a single-vote Low with nothing the script could check (no quote) is still dropped", t)
    t = _tally16(d / "g", {"A": [finding(**LOW16)], "B": [finding(**LOW16)]})
    assert t["kept"] and not t["contested"], ("a Low two reviewers agree on is kept by the vote, as before", t)
    t = _tally16(d / "h", {"A": [finding(**LOW16)]}, tier="lite")
    assert t["kept"] and not t["contested"], ("the lite tier's one reviewer is unchanged: its Low is kept by its vote", t)

@test("ruling 61 (1b): at a reviewer's stop, a review that meets the contract but has a title joining two clauses is sent back once to be split; a second stop, a clean title or a reviewer that already handed back is let through")
def _(d):
    def stop(p, active=False, transcript=None):
        data = {"agent_type": "curmudgeon:curmudgeon-reviewer", "cwd": str(p), "last_assistant_message": "Wrote .critic/reviews/review-A.json", "stop_hook_active": active}
        if transcript: data["agent_transcript_path"] = str(transcript)
        o = run(H / "check_contract.py", cwd=p, stdin=json.dumps(data)).stdout.strip()
        return json.loads(o) if o else {}
    two = finding(**dict(LOW16, title="Tax rate hard-coded in render code, and the price is never rounded"))
    one = finding(**LOW16)
    a = d / "a"; write(a, "src/app.js", APP); write(a, ".critic/reviews/review-A.json", json.dumps({"findings": [one, two]}))
    o = stop(a)
    assert o.get("decision") == "block" and "finding 2 " in o.get("reason", "") and "once" in o.get("reason", ""), ("asked to split finding 2, by number", o)
    assert "never rounded" not in o.get("reason", ""), "numbers only, never a title, in the message"
    assert stop(a, active=True).get("decision") != "block", "asked once: the second stop goes through, the reviewer's choice stands"
    b = d / "b"; write(b, "src/app.js", APP); write(b, ".critic/reviews/review-A.json", json.dumps([one]))
    assert stop(b).get("decision") != "block", "a title with one clause is never held"
    c = d / "c"; write(c, "src/app.js", APP); write(c, ".critic/reviews/review-A.json", json.dumps([two]))
    tr = write(c, "t.jsonl", json.dumps({"message": {"role": "assistant", "content": [{"type": "tool_use", "name": "SubagentHandback", "input": {"report": "Wrote .critic/reviews/review-A.json"}}]}}) + "\n")
    assert stop(c, transcript=tr).get("decision") != "block", "a reviewer that already handed back can't act on the question, so it isn't asked"
    e = d / "e"; write(e, "src/app.js", APP); write(e, ".critic/reviews/review-A.json", json.dumps([dict(two, impact="Severe")]))
    o = stop(e)
    assert o.get("decision") == "block" and "contract" in o.get("reason", ""), ("a contract problem is reported as before, not as the split question", o)
