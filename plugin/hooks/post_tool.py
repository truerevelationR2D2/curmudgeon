#!/usr/bin/env python3
"""PostToolUse for the stuck detector (stuck.py): calls by anything but a Curmudgeon agent, which are almost all of
them, return before stuck.py and its imports load (03 §5.56 item 22). Fails open, as stuck.py does."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import pyfind; import utf8io  # UTF-8 output on Windows too (03 §5.57 item 20)
import json, re, sys

def main():
    try: data = json.load(sys.stdin)
    except Exception: return 0
    if not re.fullmatch(r"(?:curmudgeon:)?curmudgeon-[a-z]+", str(data.get("agent_type") or "")): return 0
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import stuck
        stuck.main(data)
    except Exception: pass
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception: sys.exit(0)
