# Starts one Curmudgeon hook for run.sh, and says whether it really ran (5.9.2).
# usage: <python> start.py <hook script> [args]
#
# Written so any Python can read it (no f-strings), so an old one still reaches the version test and leaves with 99
# before the hook runs. Started as a script, Python puts this folder first on its import path, never the current
# folder (the user's project), so a types.py or runpy.py there can't stand in for a module (5.9.2 code review: the
# earlier `python -c` start imported runpy from the project).
# The hook's own exit, 0 (go on), 1 (error) or 2 (block), comes back as 40, 41 or 42. Two marker lines on stdout tell
# run.sh what happened, whatever the exit code says: START is written before the hook can read its input or do
# anything, END only after it finished. Without START the hook never began, so run.sh may try another Python with the
# same input; with START it never runs the hook again; without END, or with a code other than 40 to 42, there is no
# answer, and run.sh reports an error, never a block. So no other program can block every tool call by exiting 2, and a
# hook's own exit can't be mistaken for "never started" (5.9.2 code reviews).
import sys
if sys.version_info < (3, 9):
    sys.exit(99)
import os
os.write(1, b"CURMUDGEON_HOOK_START\n")
import runpy
import traceback
hook = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path[0] = os.path.dirname(os.path.abspath(hook))
code = 0
try:
    runpy.run_path(hook, run_name="__main__")
except SystemExit as e:
    if e.code is None:
        code = 0
    elif isinstance(e.code, int):
        code = e.code
    else:
        sys.stderr.write(str(e.code) + "\n")
        code = 1
except BaseException:
    traceback.print_exc()
    code = 1
for s in (sys.stdout, sys.__stdout__):
    try:
        s.flush()
    except Exception:
        pass
os.write(1, b"\nCURMUDGEON_HOOK_END")
sys.exit(40 + code if code in (0, 1, 2) else 41)
