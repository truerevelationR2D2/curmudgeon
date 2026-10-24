"""A strict reader for the subset of YAML that CI workflows, Compose files and Kubernetes manifests use (SC-50), in
standard-library Python, so the CI, agent-config and operations lenses can read YAML without installing anything.

It refuses rather than guesses. Anchors (&), aliases (*), tags (!), directives (%), several documents in one file,
complex keys (?), multi-line quoted scalars, tabs in indentation (tabs inside a block scalar are text), duplicate keys
and nesting deeper than 64 levels all raise Refused with the line number, and the lens then reports "not checked:
<file>:<line>" instead of a finding built on a wrong reading.

Every scalar stays a string, exactly as written: `on` is "on", `yes` is "yes", `010` is "010" (PyYAML's default loader
turns the workflow key `on` into True). An empty value is "". Mappings and sequences carry the line they start on, and
each key and item its own line, for findings.

Measured against PyYAML 6.0.3's BaseLoader (which also keeps every scalar a string). The first claim here, "0 read
differently", was wrong: a blind review (24 Oct 2026) found four block-scalar cases read differently (keep and clip at
the end of the file, a folded scalar starting with a blank line, spaces past the indentation on a blank line inside a
literal, an over-indented leading blank line), plus a byte-order mark read into the first key. All are fixed or refused,
and it was measured again on 24 Oct 2026 after the fixes:
- 6,191 YAML files under 200 KB on the build machine: 2,489 read identically, 3,698 refused (3,394 of them for tags,
  mostly Google Cloud SDK files), 0 read differently, 4 PyYAML itself couldn't parse. The 114 CI, Compose and
  Kubernetes files among them were used to close gaps, so they are not held out.
- 75,000 generated documents (the reviewer's fuzzer, three seeds): 0 read differently, 0 crashes. The only inputs read
  here that PyYAML rejects hold a tab inside a plain value, which YAML 1.2 allows.
The script tests pin the behaviour with plugin/tests/yaml/*.yml and their expected output, so no PyYAML is needed to
run them."""
import re

class Refused(ValueError):
    def __init__(self, line, why): super().__init__(f"line {line}: {why}"); self.line, self.why = line, why

class YStr(str):
    line = 0
class YMap(dict):
    line = 0
    def __init__(self, *a): super().__init__(*a); self.key_lines = {}
class YSeq(list):
    line = 0
    def __init__(self, *a): super().__init__(*a); self.item_lines = []

def _s(text, line):
    v = YStr(text); v.line = line; return v

ESC = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "/": "/", " ": " ", "a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "v": "\v"}

def _quoted(text, line):
    """Parse one quoted scalar at the start of text; returns (value, rest). Single line only."""
    q = text[0]; i = 1; out = []
    while i < len(text):
        c = text[i]
        if q == "'" and c == "'":
            if text[i + 1:i + 2] == "'": out.append("'"); i += 2; continue
            return "".join(out), text[i + 1:]
        if q == '"' and c == "\\":
            n = text[i + 1:i + 2]
            if n in ESC: out.append(ESC[n]); i += 2; continue
            if n in ("x", "u", "U"):
                k = {"x": 2, "u": 4, "U": 8}[n]; h = text[i + 2:i + 2 + k]
                if len(h) == k and re.fullmatch(r"[0-9A-Fa-f]+", h): out.append(chr(int(h, 16))); i += 2 + k; continue
            raise Refused(line, f"an escape it doesn't know (\\{n})")
        if q == '"' and c == '"': return "".join(out), text[i + 1:]
        out.append(c); i += 1
    raise Refused(line, "a quoted string that continues on the next line")

def _strip_comment(text):
    """Remove a trailing comment (a # after whitespace) from a plain value."""
    m = re.search(r"(^|\s)#", text)
    return text[:m.start()].rstrip() if m else text.rstrip()

def _plain(text, line, in_flow=False):
    v = _strip_comment(text)
    if v[:1] in ("&", "*", "!"): raise Refused(line, {"&": "an anchor", "*": "an alias", "!": "a tag"}[v[0]] + " (not read, so as not to guess)")
    if v[:1] in ("@", "`", "%"): raise Refused(line, f"a plain value can't start with {v[0]}")
    if not in_flow and (v == "-" or v.startswith("- ")): raise Refused(line, "a - item where a value fits")
    if v[:1] in ("|", ">"): raise Refused(line, "a block scalar where only a plain value fits")
    if not in_flow and re.search(r":\s", v + " ") and not v.startswith(("http://", "https://")) and re.search(r":(\s|$)", v): raise Refused(line, "a colon inside a plain value (quote it)")
    return v

MAX_DEPTH = 64  # deeper nesting is refused: no real workflow, Compose file or manifest needs it, and Python's own
                # recursion limit would otherwise end the whole scan

def _flow(text, line):
    """Parse a one-line flow collection at the start of text; returns (node, rest)."""
    pos = [0]; depth = [0]
    def ws():
        while pos[0] < len(text) and text[pos[0]] in " \t": pos[0] += 1
    def item():
        ws(); c = text[pos[0]:pos[0] + 1]
        if not c: raise Refused(line, "a [ ] or { } that continues on the next line")
        if c == "[": return seq()
        if c == "{": return mp()
        if c in "'\"":
            v, rest = _quoted(text[pos[0]:], line); pos[0] = len(text) - len(rest); return _s(v, line)
        m = re.match(r"[^,\[\]{}]*", text[pos[0]:]); raw = m.group(0)
        if ":" in raw and re.search(r":(\s|$)", raw): raw = raw[:re.search(r":(\s|$)", raw).start()]
        pos[0] += len(raw)
        return _s(_plain(raw.strip(), line, in_flow=True), line)
    def seq():
        depth[0] += 1
        if depth[0] > MAX_DEPTH: raise Refused(line, f"nesting deeper than {MAX_DEPTH} levels")
        pos[0] += 1; out = YSeq(); out.line = line
        ws()
        if text[pos[0]:pos[0] + 1] == "]": pos[0] += 1; depth[0] -= 1; return out
        while True:
            v = item(); ws()
            if text[pos[0]:pos[0] + 1] == ":": raise Refused(line, "a key: value pair inside [ ] (not read)")
            out.append(v); out.item_lines.append(line)
            c = text[pos[0]:pos[0] + 1]
            if c == ",":
                pos[0] += 1; ws()
                if text[pos[0]:pos[0] + 1] == "]": pos[0] += 1; depth[0] -= 1; return out
                continue
            if c == "]": pos[0] += 1; depth[0] -= 1; return out
            raise Refused(line, "a [ ] list it can't read on one line")
    def mp():
        depth[0] += 1
        if depth[0] > MAX_DEPTH: raise Refused(line, f"nesting deeper than {MAX_DEPTH} levels")
        pos[0] += 1; out = YMap(); out.line = line
        ws()
        if text[pos[0]:pos[0] + 1] == "}": pos[0] += 1; depth[0] -= 1; return out
        while True:
            k = item(); ws()
            if text[pos[0]:pos[0] + 1] == ":": pos[0] += 1; v = item(); ws()
            else: v = _s("", line)
            if not isinstance(k, str): raise Refused(line, "a key that isn't a plain value")
            if k in out: raise Refused(line, f"duplicate key {k!r}")
            out[k] = v; out.key_lines[k] = line
            c = text[pos[0]:pos[0] + 1]
            if c == ",":
                pos[0] += 1; ws()
                if text[pos[0]:pos[0] + 1] == "}": pos[0] += 1; depth[0] -= 1; return out
                continue
            if c == "}": pos[0] += 1; depth[0] -= 1; return out
            raise Refused(line, "a { } map it can't read on one line")
    node = item(); rest = text[pos[0]:]
    if _strip_comment(rest).strip(): raise Refused(line, "text after a closing bracket")
    return node, ""

def _bracket_depth(t, st):
    """Track [ ] and { } depth across the lines of a flow collection, outside quotes and comments, so the collection is
    parsed once when it closes (st = [depth, quote, previous non-space character]); linear in the text."""
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if st[1] == "'":
            if c == "'":
                if t[i + 1:i + 2] == "'": i += 2; continue
                st[1] = None
        elif st[1] == '"':
            if c == "\\": i += 2; continue
            if c == '"': st[1] = None
        elif c == "#" and (i == 0 or t[i - 1] in " \t"): break
        elif c in "'\"" and st[2] in "[{,:": st[1] = c
        elif c in "[{": st[0] += 1
        elif c in "]}": st[0] -= 1
        if not c.isspace(): st[2] = c
        i += 1
    return st[0]

def loads(text):
    """Read one YAML document. Raises Refused for anything outside the subset."""
    if text.startswith("\ufeff"): text = text[1:]  # a byte-order mark is not part of the first key
    raw = text.split("\n")
    eof_nl = len(raw) > 1 and raw[-1] == ""
    if eof_nl: raw.pop()  # the empty string after the final line break is not a line
    lines = []  # (indent, content, lineno) for content lines; block scalars read raw lines directly
    tabs, in_block = [], set()  # lines with a tab in their indentation; lines a block scalar used (tabs are text there)
    started = ended = False
    for n, l in enumerate(raw, 1):
        if l.startswith("%"): raise Refused(n, "a directive (%)")
        s = l.rstrip()
        if ended and s.strip() and not s.lstrip().startswith("#"): raise Refused(n, "content after the end of the document (...)")
        if s in ("---", "...") or s.startswith("--- ") or s.startswith("... "):
            if s.startswith("..."): ended = True; continue
            if s.startswith("---") and started: raise Refused(n, "a second document in one file")
            if s.startswith("---") and s[3:].strip() and not s[3:].strip().startswith("#"): raise Refused(n, "content on the --- line")
            started = True; continue
        if not s.strip() or s.lstrip().startswith("#"): continue
        ind = len(s) - len(s.lstrip(" "))
        if s[ind:ind + 1] == "\t": tabs.append(n)
        lines.append([ind, s[ind:], n]); started = True
    if not lines: return _s("", 1)
    pos = [0]

    def block_scalar(header, parent_ind, n):
        m = re.fullmatch(r"([|>])([+-]?)(\d?)([+-]?)\s*(#.*)?", header.strip())
        if not m: raise Refused(n, "a block scalar header it doesn't read")
        style, chomp, digit = m.group(1), m.group(2) or m.group(4), m.group(3)
        body = []; j = n  # raw line index after the header (n is 1-based, so raw[n] is the next line)
        content_ind = parent_ind + int(digit) if digit else None
        lead_ws = 0  # the widest blank line before the first content line
        while j < len(raw):
            l = raw[j].rstrip("\r")
            if l.strip() == "":
                if content_ind is None: lead_ws = max(lead_ws, len(l)); body.append("")
                else: body.append(l[content_ind:] if len(l) > content_ind else "")  # spaces past the indentation are text
                j += 1; continue
            ind = len(l) - len(l.lstrip(" "))
            if content_ind is None:
                if ind <= parent_ind: break
                content_ind = ind
                if lead_ws > content_ind: raise Refused(j + 1, "a blank line before a block scalar's text is indented more than the text (not read, so as not to guess)")
            if ind < content_ind: break
            body.append(l[content_ind:]); j += 1
        in_block.update(range(n + 1, j + 1))
        while pos[0] < len(lines) and lines[pos[0]][2] <= j: pos[0] += 1  # skip the content lines the scalar used
        trail = len(body) - len(list(__import__("itertools").takewhile(lambda x: x == "", reversed(body))))
        core, tail = body[:trail], body[trail:]
        if style == "|": textv = "\n".join(core)
        else:  # folding, as YAML does it: leading blank lines are line breaks; a single break between two ordinary lines
            out = []; k = 0  # is a space; n blank lines between them are n breaks; a more-indented line keeps its breaks
            while k < len(core) and core[k] == "": out.append("\n"); k += 1
            prev, blank = None, 0
            for l in core[k:]:
                if l == "": blank += 1; continue
                if prev is not None:
                    if l[:1] in " \t" or prev[:1] in " \t": out.append("\n" * (blank + 1))
                    else: out.append("\n" * blank if blank else " ")
                out.append(l); prev, blank = l, 0
            textv = "".join(out)
        at_eof = j >= len(raw) and not eof_nl  # the last line of the file has no line break of its own
        if chomp == "-": pass
        elif chomp == "+": textv += "\n" * max(0, (1 if core else 0) + len(tail) - (1 if at_eof else 0))
        elif core and not (at_eof and not tail): textv += "\n"
        return _s(textv, n)

    def folded_plain(first, ind, n):
        """A plain scalar that continues on deeper lines: the lines are joined with spaces, and each blank line between
        them becomes a line break, as YAML folds them. A continuation line holding `: ` or ` #` is refused."""
        parts = [first] if first else []; last = n
        while pos[0] < len(lines) and lines[pos[0]][0] > ind:
            _, t, ln = lines[pos[0]]
            if re.search(r":(\s|$)", t) or re.search(r"(^|\s)#", t) or t[:1] in "'\"[{|>&*!": raise Refused(ln, "a multi-line value it can't read safely (quote it)")
            if any(raw[k].lstrip().startswith("#") for k in range(last, ln - 1)): raise Refused(ln, "a multi-line value broken by a comment line")
            gap = sum(1 for k in range(last, ln - 1) if not raw[k].strip())
            parts.append("\n" * gap if gap else " "); parts.append(t.rstrip()); last = ln; pos[0] += 1
        out = "".join(parts)
        return _s(out.lstrip(" ") if not first else out, n)

    def value(rest, ind, n):
        """A value after `key:` or `- ` on line n whose own indent is ind."""
        r = rest.strip()
        if r == "" or r.startswith("#"):
            if pos[0] < len(lines) and lines[pos[0]][0] == ind and re.match(r"-(\s|$)", lines[pos[0]][1]) and in_map[-1]:
                return node(ind)
            if pos[0] < len(lines) and lines[pos[0]][0] > ind:
                _, t, ln = lines[pos[0]]
                if re.match(r"-(\s|$)", t) or key_split(t, ln)[0] is not None: return node(lines[pos[0]][0])
                return folded_plain("", ind, ln)
            return _s("", n)
        if r[0] in "|>": return block_scalar(r, ind, n)
        if r[0] in "[{":
            text = r; st = [0, None, "["]; _bracket_depth(r, st)
            while True:
                if st[0] <= 0 or pos[0] >= len(lines) or lines[pos[0]][0] < ind or lines[pos[0]][0] == ind and lines[pos[0]][1][:1] not in "]}":
                    try: v, _ = _flow(text, n); return v
                    except Refused as e:
                        if "continues on the next line" not in e.why or pos[0] >= len(lines) or lines[pos[0]][0] < ind or lines[pos[0]][0] == ind and lines[pos[0]][1][:1] not in "]}": raise  # only the closing bracket may sit at the key's own column
                if lines[pos[0]][2] in tabs: raise Refused(lines[pos[0]][2], "a tab in the indentation")
                text += " " + lines[pos[0]][1]; _bracket_depth(lines[pos[0]][1], st); pos[0] += 1
        if r[0] in "'\"":
            v, tail = _quoted(r, n)
            if _strip_comment(tail).strip(): raise Refused(n, "text after a quoted value")
            if pos[0] < len(lines) and lines[pos[0]][0] > ind: raise Refused(lines[pos[0]][2], "a quoted value that continues on the next line")
            return _s(v, n)
        v = _plain(r, n)
        if pos[0] < len(lines) and lines[pos[0]][0] > ind:
            if re.search(r"(^|\s)#", r): raise Refused(lines[pos[0]][2], "a value with a comment that continues on the next line")
            return folded_plain(v, ind, n)
        return _s(v, n)

    in_map = [False]

    def key_split(text, n):
        if text[:1] in "'\"":
            k, rest = _quoted(text, n)
            r2 = rest.lstrip(" ")
            if not re.match(r":(\s|$)", r2): return None, None  # a quoted scalar, not a key
            return k, r2[1:]
        if text[:1] in ("?",): raise Refused(n, "a complex key (?)")
        if text[:1] in ("&", "*", "!"): raise Refused(n, "an anchor, alias or tag on a key")
        if text[:1] in "[{": raise Refused(n, "a flow collection as a key")
        m = re.search(r":(\s|$)", text)
        if not m: return None, None
        k = text[:m.start()].rstrip()
        if re.search(r"\s#", " " + k): raise Refused(n, "a comment inside a key")
        return k, text[m.start() + 1:]

    depth = [0]

    def deeper():
        depth[0] += 1
        if depth[0] > MAX_DEPTH: raise Refused(lines[pos[0]][2], f"nesting deeper than {MAX_DEPTH} levels")

    def mapping(ind):
        deeper()
        out = YMap(); out.line = lines[pos[0]][2]
        while pos[0] < len(lines) and lines[pos[0]][0] == ind and not re.match(r"-(\s|$)", lines[pos[0]][1]):
            _, text, n = lines[pos[0]]
            k, rest = key_split(text, n)
            if k is None: raise Refused(n, "a line that is neither key: value nor - item")
            if k in out: raise Refused(n, f"duplicate key {k!r}")
            pos[0] += 1
            in_map.append(True); v = value(rest, ind, n); in_map.pop()
            out[_s(k, n)] = v; out.key_lines[k] = n
        if pos[0] < len(lines) and lines[pos[0]][0] > ind: raise Refused(lines[pos[0]][2], "indentation it doesn't expect")
        depth[0] -= 1
        return out

    def sequence(ind):
        deeper()
        out = YSeq(); out.line = lines[pos[0]][2]
        while pos[0] < len(lines) and lines[pos[0]][0] == ind and re.match(r"-(\s|$)", lines[pos[0]][1]):
            _, text, n = lines[pos[0]]
            body = text[1:]; off = len(body) - len(body.lstrip(" ")) + 1; body = body.lstrip(" ")
            if re.match(r"-(\s|$)", body): raise Refused(n, "a nested - item on the same line")
            if body and not body.startswith("#"):
                k, _r = key_split(body, n) if body[:1] not in "[{|>" else (None, None)
                if k is not None:
                    lines[pos[0]] = [ind + off, body, n]  # "- key: v" starts a mapping at the item's own column
                    in_map.append(False); v = mapping(ind + off); in_map.pop()
                else:
                    pos[0] += 1; in_map.append(False); v = value(body, ind, n); in_map.pop()
            else:
                pos[0] += 1; in_map.append(False); v = value("", ind, n); in_map.pop()
            out.append(v); out.item_lines.append(n)
        depth[0] -= 1
        return out

    def node(ind):
        if re.match(r"-(\s|$)", lines[pos[0]][1]): return sequence(ind)
        _, text, n = lines[pos[0]]
        if key_split(text, n)[0] is None:
            if len(lines) == 1:  # a document that is one scalar
                pos[0] += 1; return value(text, -1, n)
            raise Refused(n, "a line that is neither key: value nor - item")
        return mapping(ind)

    first = lines[0][0]
    try:
        doc = node(first)
        if pos[0] < len(lines): raise Refused(lines[pos[0]][2], "indentation it doesn't expect")
    except Refused as e:
        bad = [t for t in tabs if t not in in_block and t <= e.line]
        if bad: raise Refused(bad[0], "a tab in the indentation")
        raise
    except RecursionError:
        raise Refused(1, "nesting too deep to read")
    bad = [t for t in tabs if t not in in_block]
    if bad: raise Refused(bad[0], "a tab in the indentation")
    return doc

def plain(node):
    """The same data as plain dicts, lists and strs (for comparison and JSON)."""
    if isinstance(node, dict): return {str(k): plain(v) for k, v in node.items()}
    if isinstance(node, list): return [plain(v) for v in node]
    return str(node)
