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
# start.py, which leaves with 99 before the hook runs on a Python older than 3.9 and otherwise hands back the hook's
# own exit as 40, 41 or 42. Only those three are answers. A name that no longer starts Python (126, 127, 49 for the
# Windows Store placeholder's 9009, 99) is replaced at once; any other result is checked with the version test
# alone, and the name is replaced only if it fails: then the hook can't have run. A hook that ran, crashed or was
# killed is never run again: it must not repeat what it already did.
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
case "$0" in */*) here="${0%/*}" ;; *\\*) here="${0%\\*}" ;; *) here=. ;; esac  # no dirname: only sh's own words are sure to be there
start="$here/start.py"  # next to this file, always the plugin's own
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
go() { out="$($py "$start" "$hook" "$@")"; rc=$?; }  # the hook's printout is held until start.py says the hook ran: a wrong program's text never reaches Claude Code in front of the hook's answer (5.9.2 code review)
answer() { [ -n "$out" ] && printf '%s\n' "$out"; exit $((rc - 40)); }
py=""
if [ -n "$cache" ] && [ -f "$cache" ] && [ ! -L "$cache" ]; then
  read -r kept < "$cache"
  kept="${kept%"$(printf '\r')"}"  # a file saved with Windows line ends still names the same Python (CI on #55)
  case "$kept" in
    python3|python|"py -3") py="$kept" ;;  # only one of the three names, never a command from the file
  esac
fi
if [ -n "$py" ]; then
  go "$@"
  case "$rc" in
    40|41|42) answer ;;  # the hook ran: its own answer (42 is a block)
    99|126|127|49) py="" ;;  # it never started: too old, or no longer a working Python
    *) if [ "$rc" -ge 128 ] 2>/dev/null; then exit 1; fi  # killed: the hook may have run, so it never runs again; an error, never a block
       ok "$py" || py=""  # anything else: if the kept name no longer starts Python 3.9+, the hook can't have run, so find Python again
       [ -n "$py" ] && exit 1 ;;  # Python works but the hook didn't finish normally: an error, never run again
  esac
fi
find || exit 1
go "$@"
case "$rc" in 40|41|42) answer ;; esac
exit 1  # a kill, or a Python that still won't run the hook: an error, never a block
