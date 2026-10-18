"""Runs rule-file rules in a separate process, so a slow or badly written pattern (a project's own .critic/rules can
come from anyone who wrote the repo) can be stopped by a time limit instead of hanging the scan. Reads one JSON job on
stdin: {"rules": [[id, sev, area, pattern, message, globs], ...], "files": [[rel, text], ...]}; writes rows to stdout."""
import fnmatch, json, pathlib, re, sys

PER_RULE, TOTAL = 50, 2000  # bounded output: a rule that matches every line can't flood memory or the report

def main():
    job = json.load(sys.stdin); out = []; count = {}
    rules = [(rid, sev, area, re.compile(pat), msg, globs) for rid, sev, area, pat, msg, globs in job["rules"]]
    for rel, text in job["files"]:
        name = pathlib.PurePath(rel).name
        for rid, sev, area, rx, msg, globs in rules:
            if globs and not any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g) for g in globs): continue
            for i, line in enumerate(text.split("\n"), 1):
                if len(line) <= 2000 and rx.search(line):
                    count[rid] = count.get(rid, 0) + 1
                    if count[rid] > PER_RULE: break
                    out.append([sev, rid, area, f"{rel}:{i}", msg, line[:160]])
                    if len(out) >= TOTAL:
                        out.append(["NOTE", "rule-file-truncated", "structure", ".critic/rules", f"rule-file results stopped at {TOTAL} rows", ""]); json.dump(out, sys.stdout); return
    for rid, n in count.items():
        if n > PER_RULE: out.append(["NOTE", "rule-file-truncated", "structure", ".critic/rules", f"{rid}: only the first {PER_RULE} matches are reported", ""])
    json.dump(out, sys.stdout)

if __name__ == "__main__": main()
