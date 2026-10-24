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

def max_match(eligible, fixed=None):
    """eligible: {plant: [finding index, ...]} in key order. Returns {plant: finding index}, one finding per plant and
    one plant per finding, crediting as many plants as possible (augmenting paths). Greedy first-come assignment let a
    plant with a loose pattern take the only finding another plant had (found in the 5.0.0 smoke run)."""
    owner = {}
    fixed = fixed or {}  # a plant matched in an earlier pass keeps to these candidates
    def take(p, seen):
        for f in fixed.get(p, eligible[p]):
            if f in seen: continue
            seen.add(f)
            if f not in owner or take(owner[f], seen): owner[f] = p; return True
        return False
    for p in eligible: take(p, set())
    return {p: f for f, p in owner.items()}

def serious_first(eligible, serious):
    """Like max_match, but a plant listed in serious ({plant: [its candidates rated Medium or above]}) is matched to one
    of those first and stays on one, so its credited finding is one that took it seriously. If that would credit fewer
    plants in all, plain max_match wins: recall comes before the impact check."""
    best = max_match(eligible)
    first = max_match({p: c for p, c in serious.items() if c})
    keep = {p: serious[p] for p in first}
    two = _resume(eligible, first, keep)
    return two if len(two) >= len(best) else best

def _resume(eligible, start, fixed):
    owner = {f: p for p, f in start.items()}
    def take(p, seen):
        for f in fixed.get(p, eligible[p]):
            if f in seen: continue
            seen.add(f)
            if f not in owner or take(owner[f], seen): owner[f] = p; return True
        return False
    for p in eligible:
        if p not in start: take(p, set())
    return {p: f for f, p in owner.items()}
