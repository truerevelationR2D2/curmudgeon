"""The browser integrity lens (SC-74, 5.2 security suite), our own rules and code. It asks of a page that is not a fresh
test build: has it been altered in a way that weakens it? Ideas from the anti-phishing checks browsers and mail filters
use (a link whose shown address differs from its real one, homoglyph hosts) and from subresource integrity and CSP
guidance; no rule text copied. Markup is read with Python's own HTML parser; nothing is fetched.

  integrity-link-mismatch  FAIL  a link whose visible text is an address on one site while its href goes to another
                                 (the classic phishing link: the text says the bank, the target is a look-alike).
  integrity-lookalike-host FAIL  a link, form, script or frame host whose labels mix scripts (Latin with Cyrillic or
                                 Greek, say), written plainly or in punycode: a homoglyph look-alike of a real domain.
                                 An internationalised name in one script (münchen.de, 例え.jp) is not flagged.
  integrity-form-insecure  FAIL  a form (or a button's formaction) that posts over plain http (not localhost), however
                                 the address is written (http:host, http:/host, with tabs or backslashes).
  integrity-duplicate-attr FAIL  a link, form, script or frame tag with two different href, src, action, formaction
                                 or integrity values: the browser uses the first, a reader or tool may see the last.
  integrity-form-offsite   WARN  a form that posts to a different site from the one the page says it is (its canonical,
                                 base or og:url host).
  integrity-script-no-sri  WARN  a script from another site with no integrity= hash: if that site is altered, so is
                                 this page.
  integrity-csp-weak       WARN  a Content-Security-Policy (meta tag or a headers file: _headers, vercel.json,
                                 netlify.toml, nginx.conf, .htaccess) whose script policy allows 'unsafe-eval', or
                                 'unsafe-inline' with no nonce or hash, or any host (*, http:, https:) without
                                 'strict-dynamic'. Browsers ignore those fallbacks in the strict forms, so we do too.
  integrity-changed        FAIL  against the recorded copy (.critic/integrity-baseline.json): a link with the same
                                 text now goes to a different site, a link goes to a site the page never linked to, or
                                 a form now posts somewhere new.
  integrity-new-origin     FAIL  against the recorded copy: a script or frame from a site the recorded copy never used.
  integrity-baseline-unread NOTE the recorded copy exists but could not be read; the comparison rules did not run.

The recorded copy is written by `critic_scan.py --integrity-record` on a version the owner trusts; it holds hosts only
(no page text beyond link labels). The page's own site counts as "(this site)" in it, so writing a relative address
out in full is not a change. Without one, the comparison rules stay silent."""
import json, pathlib, re, unicodedata, urllib.parse
from html.parser import HTMLParser

MARKUP = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".php", ".erb", ".hbs", ".njk", ".astro"}
HEADER_FILES = re.compile(r"(^|/)(_headers|vercel\.json|netlify\.toml|nginx\.conf|\.htaccess)$")
SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "ne", "or"}
# hosting suffixes where every subdomain belongs to a different owner (a short list on the public-suffix idea; not copied)
SHARED_HOSTS = {"github.io", "gitlab.io", "netlify.app", "vercel.app", "pages.dev", "workers.dev", "herokuapp.com", "web.app",
                "firebaseapp.com", "appspot.com", "blogspot.com", "azurewebsites.net", "cloudfront.net", "s3.amazonaws.com", "onrender.com", "fly.dev"}
TEXT_ADDR = re.compile(r"^\s*(?:https?://)?((?:[\w-]+\.)+[a-z¡-￿]{2,}|xn--[\w-]+(?:\.[\w-]+)+)(?:[/:?#]\S*)?\s*$", re.I)
FILE_EXT = {"html", "htm", "pdf", "zip", "js", "css", "md", "txt", "png", "jpg", "jpeg", "gif", "svg", "json", "xml", "php", "csv", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "py", "sh", "exe", "dmg", "gz", "tar"}
LOCAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|0\.0\.0\.0)$", re.I)
SRI = re.compile(r"^\s*(sha256|sha384|sha512)-[A-Za-z0-9+/=_-]{20,}")
THIS_SITE = "(this site)"
BASELINE_MAX = 50_000_000

def clean_url(url):
    """A URL as the URL standard reads it before parsing: tabs and newlines anywhere dropped, leading and trailing
    control characters and spaces trimmed, backslashes read as slashes."""
    return re.sub(r"[\t\n\r]", "", url or "").strip(" \x00-\x1f").replace("\\", "/")

def host_of(url, page_scheme="https"):
    """The host a browser would contact, read the way the URL standard does: tabs and newlines anywhere are dropped,
    backslashes count as slashes, and a user:password@ part is not the host. With fewer than two slashes, a URL in
    the page's own scheme (https:docs/intro.html on an https page) is a relative path, and one in the other scheme
    (http:pay.example.net on an https page) names a host."""
    u = clean_url(url)
    m = re.match(r"(?i)^(https?:)(/*)(?=[^/])", u)
    if m and len(m.group(2)) < 2 and m.group(1).lower() == page_scheme + ":": return None  # relative to the page
    if m: u = m.group(1) + "//" + u[m.end():]  # http:host, http:/host and http:///host all name a host
    if not re.match(r"(?i)^(?:https?:)?//", u): return None
    try: h = urllib.parse.urlsplit(u if not u.startswith("//") else "https:" + u).hostname
    except ValueError: return None
    return h.rstrip(".") if h else None

def site(host):
    """The registrable part of a host, roughly: example.com, example.co.uk, mybank.github.io. Subdomains of one site
    are one site."""
    parts = (host or "").lower().split(".")
    if len(parts) >= 4 and ".".join(parts[-3:]) in SHARED_HOSTS: return ".".join(parts[-4:])
    if len(parts) >= 3 and ".".join(parts[-2:]) in SHARED_HOSTS: return ".".join(parts[-3:])
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2: return ".".join(parts[-3:])
    return ".".join(parts[-2:])

def same_place(a, b):
    """The shown and the real host are one place: the same site, or one is the other's own subdomain (gov.uk and www.gov.uk)."""
    a, b = a.lower(), b.lower()
    return site(a) == site(b) or a.endswith("." + b) or b.endswith("." + a)

def unicode_host(host):
    out = []
    for label in (host or "").split("."):
        if label.lower().startswith("xn--"):
            try: label = label.encode("ascii").decode("idna")
            except (UnicodeError, ValueError): return None  # broken punycode: not a name a person can read
        out.append(label)
    return ".".join(out)

def scripts(label):
    s = set()
    for c in label:
        if c.isalpha():
            try: s.add(unicodedata.name(c).split()[0])
            except ValueError: pass
    return s

def lookalike(host):
    """A label that mixes scripts (Latin with Cyrillic, Greek...), or punycode that doesn't decode."""
    if not host: return False
    u = unicode_host(host)
    if u is None: return True
    return any(len(scripts(label)) > 1 for label in u.split("."))

WATCHED_ATTRS = {"href", "src", "action", "formaction", "integrity"}
WATCHED_TAGS = {"a", "area", "form", "button", "input", "script", "iframe", "link", "base"}  # the tags whose target the lens judges
TEMPLATE = re.compile(r"\{[{%#]|<%|\{\{")  # a template tag ({% if %} href=a {% else %} href=b) is not a duplicate in the page a browser gets  # a second copy can make a reader (or a tool that keeps the last) see another target than the browser uses

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.forms, self.scripts, self.frames, self.csp, self.own = [], [], [], [], [], set()
        self._a = None; self.dupes = []
    def _close_a(self):
        if self._a is not None: self.links.append(self._a); self._a = None
    def handle_starttag(self, tag, attrs):
        a = {}; ln = self.getpos()[0]
        for k, v in attrs:
            k = k.lower()
            if k not in a: a[k] = v or ""  # a browser uses the first of two same-named attributes
            elif k in WATCHED_ATTRS and (v or "") != a[k] and tag in WATCHED_TAGS and not TEMPLATE.search(self.get_starttag_text() or ""):
                self.dupes.append({"tag": tag, "attr": k, "used": a[k], "other": v or "", "line": ln})
        if tag == "a":
            self._close_a()  # a new <a> ends an open one, as in a browser
            if a.get("href"): self._a = {"href": a["href"], "text": "", "line": ln}
        elif tag == "form": self.forms.append({"action": a.get("action", ""), "line": ln})
        elif tag in ("button", "input") and a.get("formaction"): self.forms.append({"action": a["formaction"], "line": ln})
        elif tag == "script" and a.get("src"): self.scripts.append({"src": a["src"], "sri": bool(SRI.match(a.get("integrity", ""))), "line": ln})
        elif tag == "iframe" and a.get("src"): self.frames.append({"src": a["src"], "line": ln})
        elif tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy": self.csp.append((a.get("content", ""), ln))
        elif tag == "meta" and a.get("property", "").lower() == "og:url" and host_of(a.get("content", "")): self.own.add(site(host_of(a["content"])))
        elif tag == "link" and "canonical" in a.get("rel", "").lower() and host_of(a.get("href", "")): self.own.add(site(host_of(a["href"])))
        elif tag == "base" and host_of(a.get("href", "")): self.own.add(site(host_of(a["href"])))
    def handle_data(self, data):
        if self._a is not None: self._a["text"] += data
    def handle_endtag(self, tag):
        if tag == "a": self._close_a()

def parse(text):
    p = Page()
    try: p.feed(text); p.close()
    except Exception: pass  # broken markup: report what was read
    p._close_a()  # an <a> never closed is still a link in a browser
    return p

def weak_csp(policy):
    """script-src decides when present; default-src stands in for it otherwise (as browsers do). A nonce or hash makes
    browsers ignore 'unsafe-inline'; 'strict-dynamic' makes them ignore host and scheme sources."""
    d = {}
    for part in policy.split(";"):
        w = part.strip().lower().split()
        if w: d.setdefault(w[0], w[1:])
    name = "script-src" if "script-src" in d else "default-src" if "default-src" in d else None
    if not name: return None
    vals = d[name]
    nonce = any(re.match(r"^'(nonce-|sha256-|sha384-|sha512-)", v) for v in vals); dynamic = "'strict-dynamic'" in vals
    bad = [v for v in vals if v == "'unsafe-eval'" or (v == "'unsafe-inline'" and not nonce) or (v in ("*", "http:", "https:") and not dynamic)]
    return f"{name} allows {', '.join(bad)}" if bad else None

def header_policies(text):
    """Each Content-Security-Policy value in a headers or server config file, with its line. The value starts after the
    first ':', '=', quote or space that follows the header name (or the next "value" in vercel.json) and ends at the
    closing quote or the end of the line: _headers, nginx add_header, .htaccess Header set, netlify.toml, vercel.json."""
    out = []
    for m in re.finditer(r"(?i)content-security-policy", text):
        rest = text[m.end():m.end() + 4000]
        v = re.match(r'"?\s*,?\s*(?:"value"\s*:\s*)?["\s:=]*', rest)  # vercel.json: "key": "Content-Security-Policy", "value": "..."
        if rest.lstrip('" ,\n\t').startswith('"value"') or re.match(r'"\s*,\s*\n?\s*"value"', rest):
            vm = re.search(r'"value"\s*:\s*"', rest); start = vm.end() if vm else 0
        else: start = v.end() if v else 0
        end = re.search(r'["\n]', rest[start:])
        pol = rest[start:start + end.start()] if end else rest[start:]
        if re.search(r"(?i)\b(default-src|script-src)\b", pol): out.append((pol, text.count("\n", 0, m.end() + start) + 1))
    return out

def mine(h, own):
    """A host as the recorded copy stores it: the page's own site is "(this site)"."""
    if not h: return THIS_SITE
    s = site(h)
    return THIS_SITE if s in own else s

def record(rel, text):
    """What the recorded copy keeps for one file: hosts only."""
    p = parse(text)
    return {"links": sorted({f"{' '.join(l['text'].split())[:80]}\t{mine(host_of(l['href']), p.own)}" for l in p.links if host_of(l["href"])}),
            "forms": sorted({mine(host_of(f["action"]), p.own) for f in p.forms}),
            "origins": sorted({mine(host_of(x["src"]), p.own) for x in p.scripts + p.frames if host_of(x["src"])})}

def load_baseline(root):
    """(files, problem): the recorded copy's files, or None and why it could not be read ((None, None) when there is none)."""
    bp = pathlib.Path(root) / ".critic" / "integrity-baseline.json"
    if not bp.exists() and not bp.is_symlink(): return None, None
    if bp.is_symlink() or not bp.is_file(): return None, "it is a link or not a file"
    if bp.stat().st_size > BASELINE_MAX: return None, f"it is over {BASELINE_MAX // 1_000_000} MB"
    try: j = json.loads(bp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e: return None, f"it is not valid JSON ({type(e).__name__})"
    if not (isinstance(j, dict) and isinstance(j.get("files"), dict)): return None, "it has no files table"
    return j["files"], None

def wants(rel):
    r = rel.replace("\\", "/")
    return pathlib.PurePosixPath(r).suffix.lower() in MARKUP or bool(HEADER_FILES.search(r))

def scan(rel, text, emit, root, baseline=None):
    r = rel.replace("\\", "/"); lines = text.split("\n")
    show = lambda ln: lines[ln - 1].strip()[:160] if 0 < ln <= len(lines) else ""
    if HEADER_FILES.search(r):
        for pol, ln in header_policies(text):
            w = weak_csp(pol)
            if w: emit("WARN", "integrity-csp-weak", "integrity", f"{rel}:{ln}", f"the Content-Security-Policy is weak: {w}, so injected script runs", show(ln))
        return
    p = parse(text)
    for l in p.links:
        h = host_of(l["href"]); shown = " ".join(l["text"].split())
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{l['line']}", f"the link goes to {h}, a host whose letters mix scripts and can imitate a real domain", show(l["line"])); continue
        m = TEXT_ADDR.match(shown)
        if h and m:
            shown_host = m.group(1).lower()
            if shown_host.rsplit(".", 1)[-1] in FILE_EXT and not re.match(r"(?i)\s*(https?://|www\.)", shown): continue  # a file name, not an address
            if lookalike(shown_host) or not (same_place(shown_host, h) or same_place(unicode_host(shown_host) or shown_host, unicode_host(h) or h)):
                emit("FAIL", "integrity-link-mismatch", "integrity", f"{rel}:{l['line']}", f"the link says {shown_host} but goes to {h}: a user who trusts the text lands on another site", show(l["line"]))
    for x in p.dupes:
        emit("FAIL", "integrity-duplicate-attr", "integrity", f"{rel}:{x['line']}", f"<{x['tag']}> has two {x['attr']}= values: the browser uses {x['used'][:60]!r}, while a reader or a tool that keeps the last one sees {x['other'][:60]!r}", show(x["line"]))
    for f in p.forms:
        h = host_of(f["action"])
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{f['line']}", f"the form posts to {h}, a host whose letters mix scripts", show(f["line"])); continue
        if re.match(r"(?i)^http:", clean_url(f["action"])) and h and not LOCAL.match(h):
            emit("FAIL", "integrity-form-insecure", "integrity", f"{rel}:{f['line']}", f"the form posts to {f['action'][:80]} over plain http: what the user types is sent unencrypted", show(f["line"]))
        elif h and p.own and site(h) not in p.own:
            emit("WARN", "integrity-form-offsite", "integrity", f"{rel}:{f['line']}", f"the form posts to {h}, not to this page's own site ({', '.join(sorted(p.own))})", show(f["line"]))
    for x in p.scripts + p.frames:
        h = host_of(x["src"])
        if lookalike(h): emit("FAIL", "integrity-lookalike-host", "integrity", f"{rel}:{x['line']}", f"a resource loads from {h}, a host whose letters mix scripts", show(x["line"]))
    for x in p.scripts:
        h = host_of(x["src"])
        if h and not x["sri"] and not LOCAL.match(h) and not (p.own and site(h) in p.own) and not lookalike(h):
            emit("WARN", "integrity-script-no-sri", "integrity", f"{rel}:{x['line']}", f"a script loads from {h} with no integrity= hash: if that site changes the file, this page runs the change", show(x["line"]))
    for policy, ln in p.csp:
        w = weak_csp(policy)
        if w: emit("WARN", "integrity-csp-weak", "integrity", f"{rel}:{ln}", f"the Content-Security-Policy is weak: {w}", show(ln))
    old = (baseline or {}).get(r)
    if old:
        was, linked = {}, set()
        for e in old.get("links", []):
            t, _, s = e.partition("\t"); was.setdefault(t, set()).add(s); linked.add(s)
        for l in p.links:
            h = host_of(l["href"]); t = " ".join(l["text"].split())[:80]
            if not h or LOCAL.match(h): continue
            now = mine(h, p.own)
            if t in was and now not in was[t]:
                emit("FAIL", "integrity-changed", "integrity", f"{rel}:{l['line']}", f"the link \"{t[:40]}\" went to {', '.join(sorted(was[t]))} in the recorded copy and now goes to {h}", show(l["line"]))
            elif t not in was and now != THIS_SITE and now not in linked:
                emit("FAIL", "integrity-changed", "integrity", f"{rel}:{l['line']}", f"the link \"{t[:40]}\" goes to {h}, a site the recorded copy of this page never linked to", show(l["line"]))
        forms_was = set(old.get("forms", []))
        for f in p.forms:
            h = host_of(f["action"]); now = mine(h, p.own)
            if h and LOCAL.match(h): continue
            if now not in forms_was and (forms_was or now != THIS_SITE):
                emit("FAIL", "integrity-changed", "integrity", f"{rel}:{f['line']}", f"the form posted to {', '.join(sorted(forms_was)) or 'nowhere (there was no form)'} in the recorded copy and now posts to {h or now}", show(f["line"]))
        origins_was = set(old.get("origins", []))
        for x in p.scripts + p.frames:
            h = host_of(x["src"])
            if h and not LOCAL.match(h) and mine(h, p.own) not in origins_was and mine(h, p.own) != THIS_SITE:
                emit("FAIL", "integrity-new-origin", "integrity", f"{rel}:{x['line']}", f"a script or frame now loads from {h}, which the recorded copy never used", show(x["line"]))
