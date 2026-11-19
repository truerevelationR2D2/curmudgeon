#!/usr/bin/env python3
"""The reviewers' known-command list (hooks/commands.json; 03 §5.57 items 52 and 53), grown by data, never by code.

usage:
  critic_commands.py unknown [FILE ...]   the commands reviewers or verifiers ran that the list doesn't know, with how
                                          often: read from this project's blocked lists (.critic/proctor/blocked/) and
                                          from any command files given (commands separated by blank lines, as the
                                          handoff's Test 5 writes them). Prints a draft entry for each, class "unknown", for the owner
                                          to set and paste into commands.json. It changes nothing itself.
  critic_commands.py show NAME            the entry for NAME and what its class means
  critic_commands.py check                commands.json is well formed: every class it names is described

Classes the reviewers may use are commands.json's "accepted" list; the owner changes it there too."""
import json
import os
import pathlib
import re
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent / "hooks"))
import utf8io  # noqa: E402,F401  UTF-8 output on Windows too
import conduct  # noqa: E402
import allowlist  # noqa: E402


def names_in(cmd):
    out = []
    for seg in conduct.segments(conduct._tokens(cmd) or []):
        if seg[0] in ("for", "select", "case"): continue
        w = [x for x in seg if x not in allowlist.KEYWORDS]
        while w and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w[0]): w = w[1:]
        if not w or w[0] in ("<", "<<", "<<<", ">", ">>", "2>", "&>", ">&"): continue
        r = conduct.run_words(w) or w
        if r: out.append(conduct.name_of(r[0]))
    return out


def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    D = allowlist.data()
    if a[0] == "check":
        bad = sorted({e["c"] for e in D["commands"].values()} - set(D["classes"])) + sorted(set(D["accepted"]) - set(D["classes"]))
        if bad: print("classes used but not described: " + ", ".join(bad)); return 1
        print(f"commands.json: {len(D['commands'])} commands, {len(D['classes'])} classes, accepted: {', '.join(D['accepted'])}"); return 0
    if a[0] == "show" and len(a) > 1:
        e = D["commands"].get(a[1])
        if not e: print(f"{a[1]}: not on the list (a reviewer's use of it is blocked as unknown)"); return 1
        print(json.dumps({a[1]: e}), "\n" + f"class {e['c']}: {D['classes'].get(e['c'], '?')}; " + ("accepted for reviewers" if e["c"] in D["accepted"] else "blocked for reviewers")); return 0
    if a[0] == "unknown":
        seen = Counter()
        root = pathlib.Path(os.environ.get("CRITIC_ROOT") or os.getcwd())
        for f in sorted((root / ".critic" / "proctor" / "blocked").glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r'.*"why": "(\S+) is not on Curmudgeon\'s list of known commands', line)
                if m: seen[m.group(1)] += 1
        for f in a[1:]:
            text = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
            tagged = re.findall(r"^\[(?:reviewer|verifier)\] (?:\[\w+\] )?(.*?)(?=\n\n\[(?:reviewer|verifier)\]|\Z)", text, re.S | re.M)  # Test 5's form: each entry starts with its agent type, and a here-document inside may hold blank lines
            for entry in tagged or re.split(r"\n\s*\n", text):
                entry = "\n".join(x for x in entry.splitlines() if not x.startswith("#")).strip()
                if not entry: continue
                for n in names_in(entry):
                    if n not in D["commands"] and n not in ("cd", "pushd", "popd") and not re.fullmatch(r"[\w.-]+\.(?:py|js|mjs|cjs|ts|sh|rb|php|pl)|\$\w+|\$\{\w+\}", n): seen[n] += 1
        if not seen: print("every command found is on the list"); return 0
        print("unknown commands (count; draft entries to set and paste into hooks/commands.json):")
        for n, k in seen.most_common(): print(f'  {k:5d}  "{n}": {{"c": "unknown"}}')
        print("classes: " + "; ".join(f"{c} ({d})" for c, d in D["classes"].items())); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
