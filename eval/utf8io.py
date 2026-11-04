"""UTF-8 input and output on every platform (03 §5.57 item 20). On Windows, Python reads and writes a pipe, which is
how Claude Code talks to a hook, in the ANSI code page (cp1252). A report line with an arrow crashed there, and a
hook's input naming a folder with an accented name (Ásgeir) failed to decode, so the hook let the call through.
Importing this module reconfigures stdin, stdout and stderr to UTF-8, replacing anything that can't be read or
written. The same file sits in hooks/, skills/review/scripts/ and eval/, beside the scripts that import it."""
import sys

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try: _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError): pass  # not a text stream (a test's capture, a closed pipe): left as it is
