#!/bin/sh
# Starts one Curmudgeon hook with a Python 3.9 or later that works on this machine (03 §5.57 item 29).
# usage: sh run.sh <full path to the hook script>
#
# No one interpreter name works everywhere: macOS and Linux have python3; a python.org install on Windows has py and
# python, and there python3 is often the Microsoft Store placeholder, which exits with an error. So this tries python3,
# then python, then py -3, and runs the hook with the first one that really starts Python 3.9+. The choice is kept in
# Claude Code's data folder for this plugin (made here if it isn't there yet: Claude Code makes it only when a hook
# names it). A kept choice is trusted, so a hook starts Python once, not twice (a Windows machine where each start
# took about 2 seconds had its guards stopped by Claude Code's 10-second limit; 5.9.2). The hook is started through
# start.py, which leaves with 99 before the hook runs on a Python older than 3.9. Otherwise it writes a START line
# before the hook can read its input or do anything, and an END line after the hook finished, and hands back the
# hook's own exit as 40, 41 or 42. run.sh reads those lines, never a bare exit code (5.9.2 code reviews):
#  - no START: the name isn't a working Python 3.9+, so the hook never began; the next name is tried, with the same
#    input (kept here, so a program that read it first can't leave the hook an empty one);
#  - START, then END with 40, 41 or 42: the hook's own answer (42 is a block);
#  - START and anything else (a crash, a kill): an error, never a block, and the hook is never run a second time,
#    because it may already have done its work.
# hooks.json starts this with sh, through Git Bash on Windows; where there is no Git Bash, sh can't start, and the
# PreToolUse hooks are marked onFailure "continue", so a guard that can't run never blocks the user's own work.
# This never exits 2 (Claude Code's "block") on its own account: only a hook that ran may block.
[ $# -ge 1 ] || { echo "Curmudgeon: run.sh was started without a hook to run" >&2; exit 1; }  # dash exits 2 on a failed shift (blind round)
hook="$1"; shift
if [ ! -f "$hook" ]; then echo "Curmudgeon: the hook $hook is missing, so it didn't run" >&2; exit 1; fi
cache=""
if [ -n "$CLAUDE_PLUGIN_DATA" ] && [ ! -L "$CLAUDE_PLUGIN_DATA" ]; then
  [ -e "$CLAUDE_PLUGIN_DATA" ] || mkdir -p "$CLAUDE_PLUGIN_DATA" 2>/dev/null
  [ -d "$CLAUDE_PLUGIN_DATA" ] && cache="$CLAUDE_PLUGIN_DATA/python"
fi
case "$0" in */*) here="${0%/*}" ;; *\\*) here="${0%\\*}" ;; *) here=. ;; esac  # no dirname: only sh's own words are sure to be there
start="$here/start.py"  # next to this file, always the plugin's own
nl='
'
if command -v cat >/dev/null 2>&1; then input="$(cat; printf x)"; input="${input%x}"  # the hook's input, kept whole for a second try
else input=""; while IFS= read -r line || [ -n "$line" ]; do input="$input$line$nl"; done; fi  # no cat: sh's own read
go() {
  command -v "${py%% *}" >/dev/null 2>&1 || { out=""; rc=127; return; }  # not installed: nothing to start, no error text
  out="$(printf '%s' "$input" | $py "$start" "$hook" "$@")"; rc=$?  # the printout is held until the markers say the hook ran: a wrong program's text never reaches Claude Code
}
started() { case "$out" in CURMUDGEON_HOOK_START|"CURMUDGEON_HOOK_START$nl"*) return 0 ;; esac; return 1; }  # $(...) drops the line end when nothing follows
settle() {  # the hook started: its answer if it finished, else an error; never run again
  case "$rc" in 40|41|42) ;; *) exit 1 ;; esac
  case "$out" in *"${nl}CURMUDGEON_HOOK_END") ;; *) exit 1 ;; esac
  out="${out#CURMUDGEON_HOOK_START$nl}"; out="${out%CURMUDGEON_HOOK_END}"
  while [ "${out%"$nl"}" != "$out" ]; do out="${out%"$nl"}"; done
  [ -n "$out" ] && printf '%s\n' "$out"
  exit $((rc - 40))
}
py=""
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r kept < "$cache"
  kept="${kept%"$(printf '\r')"}"  # a file saved with Windows line ends still names the same Python (CI on #55)
  case "$kept" in
    python3|python|"py -3") py="$kept" ;;  # only one of the three names, never a command from the file
  esac
fi
tried="$py"
if [ -n "$py" ]; then
  go "$@"
  started && settle
fi
for c in python3 python "py -3"; do
  [ "$c" = "$tried" ] && continue  # the kept name just failed to start
  py="$c"; go "$@"
  if started; then
    [ -n "$cache" ] && [ ! -L "$cache" ] && printf '%s\n' "$py" > "$cache" 2>/dev/null  # never written through a link
    settle
  fi
done
echo "Curmudgeon: no Python 3.9 or later found (tried python3, python and py -3), so the hook ${hook##*/} didn't run" >&2
exit 1  # an error, never a block
