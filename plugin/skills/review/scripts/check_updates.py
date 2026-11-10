#!/usr/bin/env python3
"""Compares the installed Curmudgeon with the latest version on GitHub's main branch, on request only
(/curmudgeon:check-updates, 03 §5.57 item 31). One HTTPS GET of the public plugin.json; nothing about the user or the
project is sent, and nothing is downloaded or installed. Prints the two versions and how to update.

usage: check_updates.py"""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import utf8io  # UTF-8 output on Windows too
import json, pathlib, re, sys, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent.parent  # plugin/skills/review/scripts -> plugin
URL = "https://raw.githubusercontent.com/truerevelationR2D2/curmudgeon/main/plugin/.claude-plugin/plugin.json"

def version(text):
    m = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", str(text or ""))
    return tuple(int(x) for x in m.groups()) if m else None

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None  # one request to the address shown, never another (5.4.0 blind round)

def main(a, url=URL):
    """url is fixed in normal use; only the tests pass another (a local file)."""
    if any(x in ("-h", "--help") for x in a): print(__doc__); return 0
    try: here = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError): here = None
    if not (url == URL or url.startswith("file:")): print("check-updates: refusing a source other than the built-in one"); return 1
    print(f"check-updates: one request to {url.split('/')[2] if url.startswith('https://') else 'a local file'} for the latest version number (nothing about you or your project is sent)")
    try:
        with urllib.request.build_opener(_NoRedirect).open(urllib.request.Request(url, headers={"User-Agent": "curmudgeon-check-updates"}), timeout=15) as r:
            latest = json.loads(r.read(65536).decode("utf-8")).get("version")
    except Exception as e:
        print(f"check-updates: couldn't read the latest version ({type(e).__name__}); installed: {here or 'unknown'}. Nothing was changed."); return 1
    h, l = version(here), version(latest)
    if l: latest = ".".join(map(str, l))  # only a plain version number is ever shown; anything else the source sent is not printed
    print(f"installed: {here or 'unknown'} · latest on GitHub (main): {latest if l else 'not a version number'}")
    if not h or not l: print("check-updates: a version number couldn't be read, so they can't be compared"); return 1
    if h >= l: print("up to date" + (" (this copy is newer than main)" if h > l else "")); return 0
    print(f"an update is available: {here} -> {latest}. What changed: https://github.com/truerevelationR2D2/curmudgeon/blob/main/CHANGELOG.md\n"
          "To update a copy installed from the marketplace, in a terminal: claude plugin marketplace update curmudgeon, then "
          "claude plugin update curmudgeon@curmudgeon (or /plugin marketplace update curmudgeon in a session). A copy uploaded "
          "to the Claude app as a .plugin file is updated by uploading the new version's file.")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
