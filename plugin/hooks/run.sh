#!/bin/sh
# Starts one Curmudgeon hook with a Python 3.9 or later that works on this machine (03 §5.57 item 29).
# usage: sh run.sh <full path to the hook script>
#
# No one interpreter name works everywhere: macOS and Linux have python3; a python.org install on Windows has py and
# python, and there python3 is often the Microsoft Store placeholder, which exits with an error. So this tries python3,
# then python, then py -3, and runs the hook with the first one that really starts Python 3.9+. The choice is kept in
# Claude Code's data folder for this plugin (made here if it isn't there yet: Claude Code makes it only when a hook
# names it). A kept choice is trusted, so a hook starts Python once, not twice (a Windows machine where each start
# took about 2 seconds had its guards stopped by Claude Code's 10-second limit; 5.9.2). It is still checked, at
# no extra cost: the hook is started through a few lines that leave with code 99 before the hook runs if this Python
# is older than 3.9, and a name that no longer starts Python fails to start at all (126, 127, or 49 for the Windows
# Store placeholder's 9009). Only then is the choice found again and the hook started with the new one: the hook
# itself never ran. A hook that ran and then crashed is never run again: it must not repeat what it already did.
# hooks.json starts this with sh, through Git Bash on Windows; where there is no Git Bash, sh can't start, and the
# PreToolUse hooks are marked onFailure "continue", so a guard that can't run never blocks the user's own work.
# This never exits 2 (Claude Code's "block") on its own account: only a hook that ran may block.
[ $# -ge 1 ] || { echo "Curmudgeon: run.sh was started without a hook to run" >&2; exit 1; }  # dash exits 2 on a failed shift (blind round)
hook="$1"; shift
if [ ! -f "$hook" ]; then echo "Curmudgeon: the hook $hook is missing, so it didn't run" >&2; exit 1; fi
ok() { $1 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1; }
cache=""
if [ -n "$CLAUDE_PLUGIN_DATA" ] && [ ! -L "$CLAUDE_PLUGIN_DATA" ]; then
  [ -e "$CLAUDE_PLUGIN_DATA" ] || mkdir -p "$CLAUDE_PLUGIN_DATA" 2>/dev/null
  [ -d "$CLAUDE_PLUGIN_DATA" ] && cache="$CLAUDE_PLUGIN_DATA/python"
fi
# Started with -c, Python puts the current folder first on its import path; the hook's own folder replaces it, as
# `python hook.py` would, so a file in the user's project can never stand in for one of the hook's modules.
pre='import sys; sys.exit(99) if sys.version_info < (3, 9) else None; import os, runpy; sys.argv = sys.argv[1:]; sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[0])); runpy.run_path(sys.argv[0], run_name=__name__)'  # one line, no quotes: Git Bash passes it to a Windows python.exe intact; __name__ is "__main__" under -c
find() {
  for c in python3 python "py -3"; do
    if ok "$c"; then
      py="$c"
      [ -n "$cache" ] && [ ! -L "$cache" ] && printf '%s\n' "$py" > "$cache" 2>/dev/null  # never written through a link
      return 0
    fi
  done
  echo "Curmudgeon: no Python 3.9 or later found (tried python3, python and py -3), so the hook $(basename "$hook") didn't run" >&2
  return 1
}
py=""
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r kept < "$cache"
  case "$kept" in
    python3|python|"py -3") py="$kept" ;;  # only one of the three names, never a command from the file
  esac
fi
if [ -n "$py" ]; then
  $py -c "$pre" "$hook" "$@"; rc=$?
  case "$rc" in
    99|126|127|49) py="" ;;  # the hook never started: too old, or not a working Python any more
    *) [ "$rc" -le 2 ] 2>/dev/null && exit $rc; exit 1 ;;  # the hook's own answer (2 blocks); a crash or a kill is an error, never a block, and never run again
  esac
fi
find || exit 1
$py -c "$pre" "$hook" "$@"; rc=$?
[ "$rc" -le 2 ] 2>/dev/null && exit $rc  # the hook's own answer, a block (2) included
exit 1  # a crash or a kill (130, 137, a Windows crash code), or a Python that still won't start: an error, never a block
