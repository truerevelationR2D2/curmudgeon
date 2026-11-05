"""Which copy of a hook runs (03 §5.57 item 29). hooks.json lists every hook three times, once for each way an operating
system starts Python, because no single name works everywhere: a python.org install on Windows has `py` and `python`
but not `python3` (where `python3` is often the Microsoft Store placeholder), while macOS and Linux have `python3`. Each
copy is started in exec form, with no shell, and is tagged --via=py, --via=python or --via=python3. This module, imported
first by every hook, lets exactly one copy go on and ends the others before they read or write anything:
  - py:      on Windows;
  - python:  on Windows when there is no `py`, or elsewhere when there is no `python3`;
  - python3: off Windows.
A copy whose interpreter is missing simply fails to start; hooks.json marks the blocking ones onFailure "continue", so a
missing interpreter never blocks the user's own work (the run report of 5 Nov 2026, P1)."""
import os, shutil, sys

def chosen(via, nt=None, which=shutil.which):
    """True when the copy started with this interpreter is the one that should run here."""
    nt = (os.name == "nt") if nt is None else nt
    if via == "py": return nt
    if via == "python": return (nt and not which("py")) or (not nt and not which("python3"))
    if via == "python3": return not nt
    return True

def gate():
    flag = next((a for a in sys.argv[1:] if a.startswith("--via=")), None)
    if flag is None: return
    sys.argv.remove(flag)
    if chosen(flag[len("--via="):]): return
    try:
        if not sys.stdin.isatty(): sys.stdin.read()  # take Claude Code's input so it never meets a closed pipe
    except (OSError, ValueError): pass
    sys.exit(0)

gate()
