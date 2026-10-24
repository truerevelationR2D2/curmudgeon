"""Where a finding points, judged the same way by score.py and deathmatch.py (decision 28, Ryan 24 Oct 2026: "Yes").

An answer-key entry may carry "at": [[file, first_line, last_line], ...], the places the planted defect lives. A finding
credits that plant only when it points at one of them: it cites file:line with the line inside a range (3 lines of slack
either side, for a finding that cites the call instead of the body), or quotes the plant's "quote". An entry without
"at" (an issue with no single place, such as a missing empty state) is matched on its file and pattern alone, which can
over-credit a loose pattern, so those matches are counted as loose in the report."""
import pathlib, re

SLACK = 3

def cited_lines(loc, name):
    """Line numbers loc cites for the file called name (file:12, file:12-15, file line 12)."""
    out = []
    for m in re.finditer(re.escape(name) + r"\s*(?::|,?\s+line\s+)(\d+)(?:\s*[-–]\s*(\d+))?", loc, re.I):
        a = int(m.group(1)); b = int(m.group(2) or a)
        out.extend(range(a, min(b, a + 200) + 1))
    return out

def points_at(k, loc):
    """True when loc (the finding's location text) points at the plant k; True for an entry with no "at"."""
    at = k.get("at")
    if not at and k.get("lines") and k.get("file"): at = [[k["file"], *k["lines"]]]
    if not at: return True
    if k.get("quote") and k["quote"] in loc: return True
    for f, a, b in at:
        name = pathlib.PurePosixPath(f).name
        if any(a - SLACK <= n <= b + SLACK for n in cited_lines(loc, name)): return True
    return False
