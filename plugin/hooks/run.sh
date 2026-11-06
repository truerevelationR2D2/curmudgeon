#!/bin/sh
# Starts one Curmudgeon hook with a Python 3.9 or later that works on this machine (03 §5.57 item 29).
# usage: sh run.sh <full path to the hook script>
#
# No one interpreter name works everywhere: macOS and Linux have python3; a python.org install on Windows has py and
# python, and there python3 is often the Microsoft Store placeholder, which exits with an error. So this tries python3,
# then python, then py -3, and runs the hook with the first one that really starts Python 3.9+. The choice is kept in
# Claude Code's data folder for this plugin. If the kept one stops working (removed, or now a placeholder), the hook is
# run again with the next one that works, from the same input, and the kept choice is replaced.
# hooks.json starts this with sh, through Git Bash on Windows; where there is no Git Bash, sh can't start, and the
# PreToolUse hooks are marked onFailure "continue", so a guard that can't run never blocks the user's own work.
# This never exits 2 (Claude Code's "block") on its own account: only a hook that ran may block.
hook="$1"; shift
if [ ! -f "$hook" ]; then echo "Curmudgeon: the hook $hook is missing, so it didn't run" >&2; exit 1; fi
input=$(cat; printf x); input=${input%x}  # Claude Code's input, kept so a second interpreter can be given the same
ok() { $1 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; }
run() { p_=$1; shift; printf '%s' "$input" | $p_ "$hook" "$@"; }
cache=""
[ -n "$CLAUDE_PLUGIN_DATA" ] && [ -d "$CLAUDE_PLUGIN_DATA" ] && cache="$CLAUDE_PLUGIN_DATA/python"
tried=""
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r py < "$cache"
  case "$py" in
    python3|python|"py -3")  # only one of the three names, never a command from the file
      if command -v ${py%% *} >/dev/null 2>&1; then
        run "$py" "$@"; rc=$?
        case $rc in 0|1|2) exit $rc ;; esac  # the hook ran: its own answer, a block included
        tried="$py"  # anything else (127, the Store placeholder's 9009, which Git Bash shows as 49): that interpreter doesn't work now
      fi ;;
  esac
fi
for py in python3 python "py -3"; do
  [ "$py" = "$tried" ] && continue
  if ok "$py"; then
    [ -n "$cache" ] && [ ! -L "$cache" ] && printf '%s\n' "$py" > "$cache" 2>/dev/null  # never written through a link
    run "$py" "$@"; rc=$?
    [ "$rc" -le 2 ] 2>/dev/null && exit $rc
    exit 1
  fi
done
echo "Curmudgeon: no Python 3.9 or later found (tried python3, python and py -3), so the hook $(basename "$hook") didn't run" >&2
exit 1
