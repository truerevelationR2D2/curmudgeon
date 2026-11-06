#!/bin/sh
# Starts one Curmudgeon hook with a Python 3.9 or later that works on this machine (03 §5.57 item 29).
# usage: sh run.sh <full path to the hook script>
#
# No one interpreter name works everywhere: macOS and Linux have python3; a python.org install on Windows has py and
# python, and there python3 is often the Microsoft Store placeholder, which exits with an error. So this tries python3,
# then python, then py -3, and runs the hook with the first one that really starts Python 3.9+. The choice is kept in
# Claude Code's data folder for this plugin (made here if it isn't there yet: Claude Code makes it only when a hook
# names it). The kept choice is checked again every time, so one that stopped working, or now starts an older Python,
# is replaced before the hook runs. The hook itself runs once, never again with another interpreter: a hook that ran
# and then crashed must not repeat what it already did.
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
py=""
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r kept < "$cache"
  case "$kept" in
    python3|python|"py -3") ok "$kept" && py="$kept" ;;  # only one of the three names, never a command from the file
  esac
fi
if [ -z "$py" ]; then
  for c in python3 python "py -3"; do
    if ok "$c"; then
      py="$c"
      [ -n "$cache" ] && [ ! -L "$cache" ] && printf '%s\n' "$py" > "$cache" 2>/dev/null  # never written through a link
      break
    fi
  done
fi
if [ -z "$py" ]; then
  echo "Curmudgeon: no Python 3.9 or later found (tried python3, python and py -3), so the hook $(basename "$hook") didn't run" >&2
  exit 1
fi
$py "$hook" "$@"; rc=$?
[ "$rc" -le 2 ] 2>/dev/null && exit $rc  # the hook's own answer, a block (2) included
exit 1  # a crash or a kill (130, 137, a Windows crash code): reported as an error, never as a block, and never run again
