"""Curmudgeon's script tests, part 12: release 5.9.1. Run plugin/tests/run_tests.py, which defines the helpers and runs
every part. Not runnable on its own. Each test here failed on 5.9.0 (main at 2d2d5b1)."""

@test("5.9.1: a command that runs another copy of Curmudgeon's scripts (the project's own copy) is refused for anyone, the lead included; the plugin's own scripts and other programs run")
def _(d):
    p = d / "proj"; write(p, "plugin/skills/review/scripts/critic_run.py", "print('old copy')\n"); write(p, "app.py", "print(1)\n")
    pre = lambda cmd, agent=None: run(H / "pre_tool.py", cwd=p, stdin=json.dumps(dict({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(p), "hook_event_name": "PreToolUse"}, **({"agent_type": agent, "agent_id": "a1"} if agent else {})))).stdout
    for cmd in ("S=plugin/skills/review/scripts; python3 $S/critic_run.py begin --tier lite", "python3 plugin/skills/review/scripts/critic_run.py begin",
                f"cd {p} && python3 ./plugin/skills/review/scripts/critic_run.py status", f"python3 {p}/plugin/skills/review/scripts/critic_run.py begin"):
        out = pre(cmd); assert "deny" in out and str(S / "critic_run.py") in out, (cmd, out)
    for cmd in (f"python3 {S}/critic_run.py status", f"S={S}; python3 $S/critic_run.py status", "python3 app.py", "python3 -c 'print(1)'", "python3 ${CLAUDE_PLUGIN_ROOT}/skills/review/scripts/critic_run.py status"):
        assert "deny" not in pre(cmd), cmd
