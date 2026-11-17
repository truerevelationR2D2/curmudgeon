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

@test("5.9.1 review C1, C2, L1, L2, L3: only running a copy laid out like the plugin's is refused (cd, -m, bash -c, $PWD, PowerShell, an agent, a link); a project's own scope.py, and reading or adding a copy, run")
def _(d):
    p = d / "proj"; write(p, "plugin/skills/review/scripts/critic_run.py", "print('old copy')\n"); write(p, "src/scope.py", "print(1)\n")
    def pre(cmd, tool="Bash", agent=None):
        ev = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(p), "hook_event_name": "PreToolUse"}
        if agent: ev.update(agent_type=agent, agent_id="a1")
        return run(H / "pre_tool.py", cwd=p, stdin=json.dumps(ev)).stdout
    refused = ["cd plugin/skills/review/scripts && python3 critic_run.py begin", "(cd plugin/skills/review/scripts && python3 critic_run.py)",
               "cd plugin/skills/review/scripts && python3 -m critic_run", "bash -c 'python3 plugin/skills/review/scripts/critic_run.py begin'",
               "python3 $PWD/plugin/skills/review/scripts/critic_run.py", "python3 -u plugin/skills/review/scripts/critic_run.py"]
    for c in refused: assert "deny" in pre(c), c
    assert "deny" in pre("python3 plugin/skills/review/scripts/critic_run.py begin", tool="PowerShell"), "PowerShell"
    assert "deny" in pre("python3 plugin/skills/review/scripts/critic_run.py begin", agent="curmudgeon:curmudgeon-reviewer"), "an agent"
    try:
        (p / "vendor").mkdir(); (p / "vendor" / "cur").symlink_to(p / "plugin", target_is_directory=True)
        assert "deny" in pre("python3 vendor/cur/skills/review/scripts/critic_run.py"), "through a link"
    except (OSError, NotImplementedError): pass
    for c in ("python3 src/scope.py", "git add src/scope.py", "cat plugin/skills/review/scripts/critic_run.py", "grep -n x plugin/skills/review/scripts/critic_run.py",
              "git add plugin/skills/review/scripts/critic_run.py", f"python3 {S}/critic_run.py status"):
        assert "deny" not in pre(c), c
