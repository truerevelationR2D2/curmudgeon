#!/usr/bin/env python3
"""PreToolUse for Read, Grep, Glob, Bash, LSP, Agent and Task: the blindness guard (read_guard.py) and the stuck
refusal (stuck.py) in one process, so a session pays for one Python start per tool call, not two (03 §5.56 item 22).
Calls that neither can act on, which are almost all of them (the user's own session, any agent that isn't Curmudgeon's,
except an Agent or Task call, which the fork check sees), return before anything else is imported. Each part fails
open, as it did as its own hook."""
import json, re, sys

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    ours = re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")) is not None
    if not ours and data.get("tool_name") not in ("Agent", "Task"): return 0
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import read_guard
        read_guard.main(data)
        if read_guard.DENIED: return 0
    except Exception: pass
    if ours:
        try:
            import stuck
            stuck.main(data)
        except Exception: pass
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
