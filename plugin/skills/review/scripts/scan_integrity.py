"""The browser integrity lens (SC-74, 5.2 security suite), our own rules and code. It asks of a page that is not a fresh
test build: has it been altered in a way that weakens it? Ideas from the anti-phishing checks browsers and mail filters
use (a link whose shown address differs from its real one, punycode and homoglyph hosts) and from subresource integrity
and CSP guidance; no rule text copied. Markup is read with Python's own HTML parser; nothing is fetched.

  integrity-link-mismatch  FAIL  a link whose visible text is an address on one site while its href goes to another
                                 (the classic phishing link: the text says the bank, the target is a look-alike).
  integrity-lookalike-host FAIL  a link, form, script or frame host written in punycode (xn--) or with non-ASCII
                                 letters: a homoglyph look-alike of a real domain.
  integrity-form-insecure  FAIL  a form that posts to http:// (not localhost): what the user types goes out in clear.
  integrity-form-offsite   WARN  a form that posts to a different site from the one the page says it is (its canonical,
                                 base or og:url host).
  integrity-script-no-sri  WARN  a script from another site with no integrity= hash: if that site is altered, so is
                                 this page.
  integrity-csp-weak       WARN  a Content-Security-Policy (meta tag or a headers file) whose script-src allows
                                 'unsafe-inline', 'unsafe-eval' or any host (*).
  integrity-changed        FAIL  against the recorded copy (.critic/integrity-baseline.json): a link with the same
                                 text now goes to a different site, or a form now posts somewhere new.
  integrity-new-origin     FAIL  against the recorded copy: a script or frame from a site the recorded copy never used.

The recorded copy is written by `critic_scan.py --integrity-record` on a version the owner trusts; it holds hosts only
(no page text beyond link labels). Without one, the two comparison rules stay silent."""
import json, pathlib, re
from html.parser import HTMLParser

MARKUP = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".php", ".erb", ".hbs", ".njk", ".astro"}
HEADER_FILES = re.compile(r"(^|/)(_headers|vercel\.json|netlify\.toml|nginx\.conf|\.htaccess)$")
SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "ne", "or"}
TEXT_ADDR = re.compile(r"^\s*(?:https?://)?((?:[\w-]+\.)+[a-z¡-￿]{2,}|xn--[\w-]+(?:\.[\w-]+)+)(?:[/:?#]\S*)?\s*$", re.I)
FILE_EXT = {"html", "htm", "pdf", "zip", "js", "css", "md", "txt", "png", "jpg", "jpeg", "gif", "svg", "json", "xml", "php", "csv", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "py", "sh", "exe", "dmg", "gz", "tar"}
LOCAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|\[::1\]|0\.0\.0\.0)$", re.I)

def host_of(url):
    m = re.match(r"(?i)^\s*(?:https?:)?//([^/?#:\s]+)", url or "")
    return m.group(1).lower().rstrip(".") if m else None

def site(host):
    """The registrable part of a host, roughly: example.com, example.co.uk. Subdomains of one site are one site."""
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2: return ".".join(parts[-3:])
    return ".".join(parts[-2:])

def lookalike(host):
    return bool(host) and (any(p.startswith("xn--") for p in host.split(".")) or any(ord(c) > 127 for c in host))

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.forms, self.scripts, self.frames, self.csp, self.own = [], [], [], [], [], set()
        self._a = None
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}; ln = self.getpos()[0]
        if tag == "a" and a.get("href"): self._a = {"href": a["href"], "text": "", "line": ln}
        elif tag == "form": self.forms.append({"action": a.get("action", ""), "line": ln})
        elif tag == "script" and a.get("src"): self.scripts.append({"src": a["src"], "sri": "integrity" in a, "line": ln})
        elif tag == "iframe" and a.get("src"): self.frames.append({"src": a["src"], "line": ln})
        elif tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy": self.csp.append((a.get("content", ""), ln))
        elif tag == "meta" and a.get("property", "").lower() == "og:url" and host_of(a.get("content", "")): self.own.add(site(host_of(a["content"])))
        elif tag == "link" and "canonical" in a.get("rel", "").lower() and host_of(a.get("href", "")): self.own.add(site(host_of(a["href"])))
        elif tag == "base" and host_of(a.get("href", "")): self.own.add(site(host_of(a["href"])))
    def handle_data(self, data):
        if self._a is not None: self._a["text"] += data
    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None: self.links.append(self._a); self._a = None

def parse(text):
    p = Page()
    try: p.feed(text); p.close()
    except Exception: pass  # broken markup: report what was read
    return p

def weak_csp(policy):
    """script-src decides when present; default-src stands in for it otherwise (as browsers do)."""
    d = {}
    for part in policy.split(";"):
        w = part.strip().lower().split()
        if w: d.setdefault(w[0], w[1:])
    name = "script-src" if "script-src" in d else "default-src" if "default-src" in d else None
    if not name: return None
    bad = [v for v in d[name] if v in ("'unsafe-inline'", "'unsafe-eval'", "*", "http:", "https:")]
    return f"{name} allows {', '.join(bad)}" if bad else None

def record(rel, text):
    """What the recorded copy keeps for one file: hosts only."""
    p = parse(text)
    return {"links": sorted({f"{' '.join(l['text'].split())[:80]}\t{site(host_of(l['href']))}" for l in p.links if host_of(l["href"])}),
            "forms": sorted({site(host_of(f["action"])) if host_of(f["action"]) else "(this site)" for f in p.forms}),
            "origins": sorted({site(host_of(x["src"])) for x in p.scripts + p.frames if host_of(x["src"])})}

def load_baseline(root):
    bp = pathlib.Path(root) / ".critic" / "integrity-baseline.json"
    if not bp.is_file() or bp.is_symlink() or bp.stat().st_size > 2_000_000: return None
    try: j = json.loads(bp.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None
    return j.get("files") if isinstance(j, dict) and isinstance(j.get("files"), dict) else None

def wants(rel):
    r = rel.replace("\\", "/")
    return pathlib.PurePosixPath(r).suffix.lower() in MARKUP or bool(HEADER_FILES.search(r))

def scan(rel, text, emit, root, baseline=None):
    r = rel.replace("\\", "/"); lines = text.split("\n")
    show = lambda ln: lines[ln - 1].strip()[:160] if 0 < ln <= len(lines) else ""
    if HEADER_FILES.search(r):
        for i, l in enumerate(lines, 1):
            if re.search(r"(?i)content-security-policy", l):
                w = weak_csp(l.split(":", 1)[-1] if ":" in l else l)
                if w: emit("WARN", "integrity-csp-weak", "integrity", f"{rel}:{i}", f"the Content-Security-Policy is weak: {w}, so injected script runs", show(i))
        return
    p = parse(text)
    for l in p.links:
        h = host_of(l["href"]); shown = " ".join(l["text"].split())
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{l['line']}", f"the link goes to {h}, a punycode or non-ASCII host that can imitate a real domain", show(l["line"])); continue
        m = TEXT_ADDR.match(shown)
        if h and m:
            shown_host = m.group(1).lower()
            if shown_host.rsplit(".", 1)[-1] in FILE_EXT and not re.match(r"(?i)\s*(https?://|www\.)", shown): continue  # a file name, not an address
            if lookalike(shown_host) or site(shown_host) != site(h):
                emit("FAIL", "integrity-link-mismatch", "integrity", f"{rel}:{l['line']}", f"the link says {shown_host} but goes to {h}: a user who trusts the text lands on another site", show(l["line"]))
    for f in p.forms:
        h = host_of(f["action"])
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{f['line']}", f"the form posts to {h}, a punycode or non-ASCII host", show(f["line"])); continue
        if re.match(r"(?i)^\s*http://", f["action"]) and h and not LOCAL.match(h):
            emit("FAIL", "integrity-form-insecure", "integrity", f"{rel}:{f['line']}", f"the form posts to {f['action'][:80]} over plain http: what the user types is sent unencrypted", show(f["line"]))
        elif h and p.own and site(h) not in p.own:
            emit("WARN", "integrity-form-offsite", "integrity", f"{rel}:{f['line']}", f"the form posts to {h}, not to this page's own site ({', '.join(sorted(p.own))})", show(f["line"]))
    for x in p.scripts + p.frames:
        h = host_of(x["src"])
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{x['line']}", f"a resource loads from {h}, a punycode or non-ASCII host", show(x["line"])); continue
    for x in p.scripts:
        h = host_of(x["src"])
        if h and not x["sri"] and not LOCAL.match(h) and not (p.own and site(h) in p.own):
            emit("WARN", "integrity-script-no-sri", "integrity", f"{rel}:{x['line']}", f"a script loads from {h} with no integrity= hash: if that site changes the file, this page runs the change", show(x["line"]))
    for policy, ln in p.csp:
        w = weak_csp(policy)
        if w: emit("WARN", "integrity-csp-weak", "integrity", f"{rel}:{ln}", f"the Content-Security-Policy is weak: {w}", show(ln))
    old = (baseline or {}).get(r)
    if old:
        was = {}
        for e in old.get("links", []):
            t, _, s = e.partition("\t"); was.setdefault(t, set()).add(s)
        for l in p.links:
            h = host_of(l["href"]); t = " ".join(l["text"].split())[:80]
            if h and t in was and site(h) not in was[t]:
                emit("FAIL", "integrity-changed", "integrity", f"{rel}:{l['line']}", f"the link \"{t[:40]}\" went to {', '.join(sorted(was[t]))} in the recorded copy and now goes to {h}", show(l["line"]))
        forms_was = set(old.get("forms", []))
        for f in p.forms:
            h = host_of(f["action"]); now = site(h) if h else "(this site)"
            if forms_was and now not in forms_was:
                emit("FAIL", "integrity-changed", "integrity", f"{rel}:{f['line']}", f"the form posted to {', '.join(sorted(forms_was))} in the recorded copy and now posts to {now}", show(f["line"]))
        origins_was = set(old.get("origins", []))
        for x in p.scripts + p.frames:
            h = host_of(x["src"])
            if h and site(h) not in origins_was and not LOCAL.match(h):
                emit("FAIL", "integrity-new-origin", "integrity", f"{rel}:{x['line']}", f"a script or frame now loads from {h}, which the recorded copy never used", show(x["line"]))
