"""UTF-8 output on every platform (03 §5.57 item 20). On Windows, Python writes to a pipe, which is how Claude Code
reads a hook's output, in the ANSI code page (cp1252), and a report line with an arrow or an accented name crashed
there. Importing this module reconfigures stdout and stderr to UTF-8, replacing anything that can't be written. The
same file sits in hooks/, skills/review/scripts/ and eval/, beside the scripts that import it."""
import sys

for _stream in (sys.stdout, sys.stderr):
    try: _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError): pass  # not a text stream (a test's capture, a closed pipe): left as it is
