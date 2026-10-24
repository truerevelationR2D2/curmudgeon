"""Where a finding points, judged the same way by score.py and deathmatch.py (decision 28, Ryan 24 Oct 2026: "Yes").

An answer-key entry may carry "at": [[file, first_line, last_line], ...], the places the planted defect lives. A finding
credits that plant only when it points at one of them: it cites file:line with the line inside a range (3 lines of slack
either side, for a finding that cites the call instead of the body), or quotes the plant's "quote". An entry without
"at" is matched on its file and pattern alone, which can over-credit a loose pattern; every entry in the four answer keys
and every key the planter writes has "at", and score.py reports how many credits came from an entry without one."""
import pathlib, re

SLACK = 3

CITE = r"[`'\"*]*\s*(?::L?|#L|,?\s*\(?\s*(?:at\s+)?lines?\s+)(\d+)(?:\s*[-–]\s*L?(\d+))?"

def cited_lines(loc, name):
    """Line numbers loc cites for the file called name, in the forms people and tools write: file:12, file:12-15,
    file:L12, file#L12, file line 12, `file` line 12, file (line 12), file, line 12, file lines 12-15."""
    out = []
    for m in re.finditer(re.escape(name) + CITE, loc, re.I):
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

def max_match(eligible):
    """eligible: {plant: [finding index, ...]} in key order. Returns {plant: finding index}, one finding per plant and
    one plant per finding, crediting as many plants as possible (augmenting paths). Greedy first-come assignment let a
    plant with a loose pattern take the only finding another plant had (found in the 5.0.0 smoke run)."""
    owner = {}
    def take(p, seen):
        for f in eligible[p]:
            if f in seen: continue
            seen.add(f)
            if f not in owner or take(owner[f], seen): owner[f] = p; return True
        return False
    for p in eligible: take(p, set())
    return {p: f for f, p in owner.items()}

def serious_first(eligible, serious):
    """The matching that credits the most plants and, among those, puts the most plants listed in serious ({plant: its
    candidates rated Medium or above}) on one of those candidates: an exact maximum-weight matching (each match is
    worth more than every preference together), by successive shortest paths. Recall comes first, then the impact
    check. The sizes here are small (tens of plants and findings)."""
    plants = list(eligible); finds = sorted({f for c in eligible.values() for f in c})
    if not plants or not finds: return {}
    BIG = len(plants) + 1
    w = {(p, f): BIG + (1 if f in serious.get(p, []) else 0) for p in plants for f in eligible[p]}
    # nodes: source 0, plants 1..P, findings P+1..P+F, sink P+F+1; edges with capacity 1 and cost -weight
    P, F = len(plants), len(finds); src, snk = 0, P + F + 1; fi = {f: P + 1 + j for j, f in enumerate(finds)}
    graph = [[] for _ in range(snk + 1)]
    def add(u, v, cost):
        graph[u].append([v, 1, cost, len(graph[v])]); graph[v].append([u, 0, -cost, len(graph[u]) - 1])
    for i, p in enumerate(plants, 1):
        add(src, i, 0)
        for f in eligible[p]: add(i, fi[f], -w[(p, f)])
    for f in finds: add(fi[f], snk, 0)
    while True:  # Bellman-Ford: costs are negative, and the graph is tiny
        dist = [float("inf")] * (snk + 1); prev = [None] * (snk + 1); dist[src] = 0
        for _ in range(snk + 1):
            moved = False
            for u in range(snk + 1):
                if dist[u] == float("inf"): continue
                for k, (v, cap, cost, _r) in enumerate(graph[u]):
                    if cap and dist[u] + cost < dist[v]: dist[v] = dist[u] + cost; prev[v] = (u, k); moved = True
            if not moved: break
        if dist[snk] >= 0: break  # no augmenting path that adds weight
        v = snk
        while v != src:
            u, k = prev[v]; e = graph[u][k]; e[1] -= 1; graph[v][e[3]][1] += 1; v = u
    out = {}
    for i, p in enumerate(plants, 1):
        for v, cap, cost, _r in graph[i]:
            if P + 1 <= v <= P + F and cap == 0 and cost < 0: out[p] = finds[v - P - 1]
    return out
