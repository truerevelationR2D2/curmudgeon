#!/usr/bin/env python3
"""Turn `semgrep scan --json` output (stdin) into one list item per result, `- file:line [rule] message`, so the death
match's single scorer reads Semgrep's findings the way it reads every other arm's. Development benchmark only."""
import json, sys
try: j = json.load(sys.stdin)
except ValueError: print("semgrep produced no JSON"); sys.exit(2)
for r in j.get("results", []):
    msg = " ".join(str(r.get("extra", {}).get("message", "")).split())
    print(f"- {r.get('path')}:{r.get('start', {}).get('line')} [{str(r.get('check_id', '')).split('.')[-1]}] {msg} `{' '.join(str(r.get('extra', {}).get('lines', '')).split())[:160]}`")
if not j.get("results"): print("No issues found.")  # zero results is a clean result, not a run that wrote nothing
for e in j.get("errors", [])[:5]: print(f"(semgrep error: {str(e.get('message', e))[:160]})", file=sys.stderr)
