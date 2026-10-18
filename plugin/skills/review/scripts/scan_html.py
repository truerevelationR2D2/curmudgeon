"""HTML validity checks for Curmudgeon scan: our own parser-based checks for the problems the Nu Html Checker (MIT)
reports most often and that break accessibility. No validator is needed."""
from html.parser import HTMLParser
import re

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
INTERACTIVE = {"a", "button", "select", "textarea", "label", "details", "iframe", "audio", "video"}
PHRASING_ONLY = {"button", "a", "p", "span", "label", "h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK = {"div", "p", "ul", "ol", "table", "section", "article", "header", "footer", "nav", "form", "h1", "h2", "h3", "h4", "h5", "h6", "main", "aside"}
OPTIONAL_END = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot", "option", "optgroup", "colgroup", "caption", "rt", "rp", "html", "head", "body"}

class Checker(HTMLParser):
    def __init__(self, rel, emit):
        super().__init__(convert_charrefs=True); self.rel, self.emit = rel, emit
        self.stack, self.ids, self.label_for, self.labelled, self.has_lang, self.has_title, self.has_html = [], {}, [], set(), False, False, False
        self.headings, self.inputs = [], []
    def where(self): return f"{self.rel}:{self.getpos()[0]}"
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); ln = self.getpos()[0]
        if tag == "html": self.has_html = True; self.has_lang = bool(a.get("lang"))
        if tag == "title": self.has_title = True
        if "id" in a and a["id"]:
            if a["id"] in self.ids: self.emit("WARN", "html-duplicate-id", "html", self.where(), f"duplicate id \"{a['id']}\" (first at line {self.ids[a['id']]}); labels and ARIA references break", "")
            else: self.ids[a["id"]] = ln
        if tag == "label" and a.get("for"): self.label_for.append((a["for"], ln))
        if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button", "reset", "image"):
            self.inputs.append((a.get("id"), ln, bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title")), any(t == "label" for t, _ in self.stack)))
        if re.fullmatch(r"h[1-6]", tag): self.headings.append((int(tag[1]), ln))
        open_tags = [t for t, _ in self.stack]
        inter = tag in INTERACTIVE or (tag == "input" and a.get("type") != "hidden") or "tabindex" in a
        if inter and tag != "label":
            outer = next((t for t in reversed(open_tags) if t in ("a", "button")), None)
            if outer: self.emit("FAIL", "html-nested-interactive", "html", self.where(), f"<{tag}> inside <{outer}>: interactive elements must not nest (keyboard and screen readers break)", "")
        if tag in BLOCK:
            outer = next((t for t in reversed(open_tags) if t in PHRASING_ONLY), None)
            if outer and not (outer == "a"): self.emit("WARN", "html-content-model", "html", self.where(), f"<{tag}> inside <{outer}> is invalid HTML", "")
        if open_tags and open_tags[-1] in ("ul", "ol") and tag not in ("li", "script", "template"):
            self.emit("WARN", "html-list-child", "html", self.where(), f"<{tag}> directly inside <{open_tags[-1]}> (only <li> belongs there)", "")
        if tag == "a" and "href" not in a and not a.get("role"):
            self.emit("NOTE", "html-anchor-no-href", "html", self.where(), "<a> without href is not a link to the keyboard (use a button or add href)", "")
        if tag == "img" and "alt" not in a: self.emit("WARN", "html-img-alt", "html", self.where(), "image without alt", "")
        if tag == "button" and a.get("type") is None and any(t == "form" for t in open_tags):
            self.emit("NOTE", "html-button-type", "html", self.where(), "button inside a form has no type: it submits the form by default", "")
        if tag not in VOID: self.stack.append((tag, ln))
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag: self.stack.pop()
    def handle_endtag(self, tag):
        if tag in VOID: return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, ln in self.stack[i + 1:]:
                    if t not in OPTIONAL_END: self.emit("WARN", "html-unclosed", "html", f"{self.rel}:{ln}", f"<{t}> is never closed (closed implicitly by </{tag}>)", "")
                del self.stack[i:]; return
        self.emit("NOTE", "html-stray-end", "html", self.where(), f"</{tag}> has no matching open tag", "")
    def finish(self):
        for t, ln in self.stack:
            if t not in OPTIONAL_END: self.emit("WARN", "html-unclosed", "html", f"{self.rel}:{ln}", f"<{t}> is never closed", "")
        for target, ln in self.label_for:
            if target not in self.ids: self.emit("WARN", "html-label-for", "html", f"{self.rel}:{ln}", f"<label for=\"{target}\"> points at no element", "")
            else: self.labelled.add(target)
        for iid, ln, aria, wrapped in self.inputs:
            if not (aria or wrapped or (iid and iid in self.labelled)):
                self.emit("WARN", "html-input-label", "html", f"{self.rel}:{ln}", "form control has no label (placeholder text is not a label: WCAG 1.3.1, 3.3.2, 4.1.2)", "")
        prev = 0
        for lvl, ln in self.headings:
            if prev and lvl > prev + 1: self.emit("NOTE", "html-heading-skip", "html", f"{self.rel}:{ln}", f"heading jumps from h{prev} to h{lvl}", "")
            prev = lvl
        if self.has_html and not self.has_lang: self.emit("WARN", "html-lang", "html", self.rel, "<html> has no lang (screen readers guess the language: WCAG 3.1.1)", "")
        if self.has_html and not self.has_title: self.emit("WARN", "html-title", "html", self.rel, "page has no <title> (WCAG 2.4.2)", "")

def scan(rel, text, emit):
    c = Checker(rel, emit)
    try: c.feed(text); c.close(); c.finish()
    except Exception as e: emit("NOTE", "html-parse", "html", rel, f"HTML could not be fully parsed ({type(e).__name__})", "")
