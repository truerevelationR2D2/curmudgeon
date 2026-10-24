#!/usr/bin/env python3
"""SubagentStop: when a reviewer or verifier finishes, keep its scratch notes in .critic/scratch/<agent_id>/notes/ and
delete its private workspace (workspace.py). Never blocks the agent's stop."""
import json, os, pathlib, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    root = pathlib.Path(data.get("cwd") or os.getcwd())
    workspace.remove(root, data.get("agent_id"))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
