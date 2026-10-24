#!/usr/bin/env python3
"""SubagentStop: record what each Curmudgeon agent cost, in tokens, while a review run is active. Reads the agent's own
transcript (agent_transcript_path), sums input, cache-write, cache-read and output tokens per request (a request's
rows repeat while it streams, so each request counts once, at its largest values), and appends one line to
.critic/cost.jsonl. `critic_ledger.py tokens` totals them by role. Nothing is sent anywhere; it never blocks an agent,
and when the host gives no transcript the cost is reported as unavailable, never guessed."""
import json, os, pathlib, sys, time

FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
MAX_BYTES = 200_000_000

def usage(path):
    p = pathlib.Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size > MAX_BYTES: return None
    per, models = {}, set()
    with open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"usage"' not in line: continue
            try: j = json.loads(line)
            except ValueError: continue
            m = j.get("message") if isinstance(j, dict) else None
            if not isinstance(m, dict) or not isinstance(m.get("usage"), dict): continue
            key = j.get("requestId") or m.get("id") or j.get("uuid")
            got = per.setdefault(key, dict.fromkeys(FIELDS, 0))
            for k in FIELDS:
                v = m["usage"].get(k)
                if isinstance(v, int) and v > got[k]: got[k] = v
            if m.get("model"): models.add(str(m["model"]))
    total = dict.fromkeys(FIELDS, 0)
    for got in per.values():
        for k in FIELDS: total[k] += got[k]
    return dict(total, requests=len(per), models=sorted(models))

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    root = pathlib.Path(data.get("cwd") or os.getcwd()); c = root / ".critic"
    if c.is_symlink() or not (c / "ledger.json").is_file() or (c / "ledger.json").is_symlink(): return 0
    try: led = json.loads((c / "ledger.json").read_text())
    except Exception: return 0
    if not led.get("started_at"): return 0  # no review run is active
    if (c / "cost.jsonl").is_symlink(): return 0
    kind = str(data.get("agent_type") or "")
    role = kind.split(":")[-1].replace("curmudgeon-", "") or "unknown"
    u = usage(data["agent_transcript_path"]) if data.get("agent_transcript_path") else None
    row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "run": led.get("run"), "round": led.get("round"), "role": role,
           "agent_id": str(data.get("agent_id") or "")[:64]}
    row.update(u if u else {"unavailable": "the host gave no readable transcript for this agent"})
    with open(c / "cost.jsonl", "a", encoding="utf-8") as fh: fh.write(json.dumps(row) + "\n")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
