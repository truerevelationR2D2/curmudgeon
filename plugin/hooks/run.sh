#!/bin/sh
# Starts one Curmudgeon hook with a Python 3.9 or later that works on this machine (03 §5.57 item 29).
# usage: sh run.sh <full path to the hook script>
#
# No one interpreter name works everywhere: macOS and Linux have python3; a python.org install on Windows has py and
# python, and there python3 is often the Microsoft Store placeholder, which exits with an error. So this tries python3,
# then python, then py -3, and runs the hook with the first one that really starts Python 3.9+. The choice is kept in
# Claude Code's data folder for this plugin, and is checked again if that interpreter disappears.
# hooks.json starts this with sh, through Git Bash on Windows; where there is no Git Bash, sh can't start, and the
# PreToolUse hooks are marked onFailure "continue", so a guard that can't run never blocks the user's own work.
hook="$1"; shift
ok() { $1 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; }
cache=""
[ -n "$CLAUDE_PLUGIN_DATA" ] && [ -d "$CLAUDE_PLUGIN_DATA" ] && cache="$CLAUDE_PLUGIN_DATA/python"
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r py < "$cache"
  case "$py" in
    python3|python|"py -3") command -v ${py%% *} >/dev/null 2>&1 && exec $py "$hook" "$@" ;;  # only one of the three names, never a command from the file
  esac
fi
for py in python3 python "py -3"; do
  if ok "$py"; then
    [ -n "$cache" ] && printf '%s\n' "$py" > "$cache" 2>/dev/null
    exec $py "$hook" "$@"
  fi
done
echo "Curmudgeon: no Python 3.9 or later found (tried python3, python and py -3), so the hook $(basename "$hook") didn't run" >&2
exit 1
