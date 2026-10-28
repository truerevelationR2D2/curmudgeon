"""More static rules for Curmudgeon scan, in our own code. Ideas from ESLint core rules, Mozilla's no-unsanitized
(more unsafe HTML sinks), Stylelint (CSS) and the WCAG 2.2 criteria no engine checks (3.3.8, 2.5.7, 2.2.1, 1.4.2).
No rule text from those projects is used."""
import re
import pathlib
import os
import scan_python, scan_tests

CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte", ".html", ".htm"}
MARKUP = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte"}
STYLE = {".css", ".scss", ".less"} | MARKUP
# the whole value must be safe: one plain literal, or one call to a named sanitiser ('<tr>' + text + '</tr>' is not)
SAFE_ARG = re.compile(r"\s*(?:'[^'$`]*'|\"[^\"$`]*\"|`[^`$]*`|(?:escapeHtml|escapeHTML|escape_html|htmlEscape|escape|sanitize|sanitizeHtml|DOMPurify\.sanitize)\((?:[^()]|\([^()]*\))*\))\s*;?\s*(?://.*)?")

LINE_RULES = [
    ("doc-write", "WARN", "safety", r"\bdocument\.write(ln)?\(", "document.write: an HTML injection sink, and it blocks parsing", CODE),
    ("contextual-fragment", "WARN", "safety", r"createContextualFragment\(", "createContextualFragment parses HTML: escape or sanitise its input", CODE),
    ("srcdoc", "WARN", "safety", r"\.srcdoc\s*=|srcdoc=\{", "iframe srcdoc from code is an HTML injection sink", CODE),
    ("js-url", "WARN", "safety", r"(?:href|src|action)\s*=\s*[\"'`]\s*javascript:", "javascript: URL (runs script; breaks under a content security policy)", CODE),
    ("dynamic-href", "NOTE", "safety", r"\.(?:href|src)\s*=\s*(?![\"'`])\w", "URL set from a variable: confirm it can't be a javascript: URL from user input", CODE),
    ("implied-eval", "WARN", "safety", r"\bset(?:Timeout|Interval)\(\s*[\"'`]", "setTimeout/setInterval with a string runs it like eval", CODE),
    ("target-blank", "NOTE", "safety", r"(?:<a\b(?![^>]*\brel=[\"'][^\"']*noopener)[^>]*|^(?![^<]*\brel=[\"'][^\"']*noopener)[^<>]*)target=[\"']_blank[\"'](?![^>]*\brel=[\"'][^\"']*noopener)", "target=_blank without rel=\"noopener\" (the new tab can control this one in old browsers)", MARKUP),
    ("loose-equality-null", "NOTE", "errors", r"[^=!]==\s*(?:undefined)\b|[^=!]!=\s*(?:undefined)\b", "loose comparison with undefined: say what you mean (=== undefined, or == null on purpose)", CODE),
    ("unsafe-finally", "WARN", "errors", r"finally\s*\{[^}]*\breturn\b", "return inside finally swallows the error or the earlier result", CODE),
    ("await-in-foreach", "WARN", "async", r"\.forEach\(\s*async\b", "forEach with an async callback: nothing waits for it, and errors are lost", CODE),
    ("promise-no-catch", "NOTE", "async", r"\.then\([^)]*\)\s*;\s*$", "promise chain with no catch: a failure is silent", CODE),
    ("paste-blocked", "WARN", "a11y", r"onpaste\s*=\s*[\"']?\s*(?:return\s+false|event\.preventDefault)|addEventListener\(\s*[\"']paste[\"'][^)]*preventDefault", "paste is blocked: password managers and pasted codes stop working (WCAG 3.3.8)", CODE),
    ("autocomplete-off-auth", "WARN", "a11y", r"<input[^>]*(?:type=[\"']password[\"']|autocomplete=[\"']one-time-code[\"']|name=[\"'](?:otp|code|pin)[\"'])[^>]*autocomplete=[\"']off[\"']|<input[^>]*autocomplete=[\"']off[\"'][^>]*type=[\"']password[\"']", "autocomplete=\"off\" on a sign-in field: blocks password managers (WCAG 3.3.8)", MARKUP),
    ("drag-only", "NOTE", "a11y", r"draggable=[\"']true[\"']|addEventListener\(\s*[\"'](?:dragstart|pointermove|mousemove)[\"']", "drag interaction: confirm a single-pointer alternative exists, such as buttons (WCAG 2.5.7)", CODE),
    ("meta-refresh", "WARN", "a11y", r"<meta[^>]*http-equiv=[\"']refresh[\"']", "meta refresh: the page changes or reloads without warning (WCAG 2.2.1)", MARKUP),
    ("autoplay", "WARN", "a11y", r"<(?:video|audio)\b(?![^>]*\bmuted\b)[^>]*\bautoplay\b", "media plays sound automatically (WCAG 1.4.2)", MARKUP),
    ("iframe-title", "WARN", "a11y", r"<iframe(?![^>]*\btitle=)[^>]*>", "iframe without a title (WCAG 4.1.2)", MARKUP),
    ("positive-tabindex", "WARN", "a11y", r"tabindex=[\"']?[1-9]", "positive tabindex scrambles the keyboard order (WCAG 2.4.3)", MARKUP),
    ("generic-link-text", "NOTE", "a11y", r">\s*(?:read more|more|here|click here|learn more|link)\s*</a>", "link text that means nothing out of context (WCAG 2.4.4)", MARKUP),
    ("user-select-none", "NOTE", "ux", r"user-select\s*:\s*none", "user-select: none stops people copying text: confirm it's needed", STYLE),
    ("huge-z-index", "NOTE", "layout", r"z-index\s*:\s*(?:\d{4,})", "z-index in the thousands: a stacking-order arms race", STYLE),
]
PY = {".py"}
LINE_RULES += [  # Python, after Bandit's ideas (Apache-2.0); our own patterns
    ("py-shell-true", "WARN", "safety", r"subprocess\.\w+\([^)]*shell\s*=\s*True", "subprocess with shell=True: any untrusted text in the command becomes a shell command", PY),
    ("py-os-system", "WARN", "safety", r"\bos\.(?:system|popen)\(", "os.system/os.popen run through the shell: prefer subprocess with a list", PY),
    ("py-eval", "FAIL", "safety", r"^(?:[^\"'#]|\"[^\"]*\"|'[^']*')*?(?<![\w.\"'])(?:eval|exec)\(", "eval/exec runs arbitrary code", PY),
    ("py-pickle", "WARN", "safety", r"\b(?:pickle|cPickle|dill|shelve)\.loads?\(", "unpickling runs code from the data: never load untrusted pickles", PY),
    ("py-yaml-load", "WARN", "safety", r"\byaml\.load\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)", "yaml.load without SafeLoader can build arbitrary objects (use yaml.safe_load)", PY),
    ("py-verify-false", "WARN", "safety", r"verify\s*=\s*False", "TLS certificate checks switched off", PY),
    ("py-bare-except-pass", "WARN", "errors", r"except\s*(?:Exception\s*)?:\s*pass\b", "every error is swallowed here (the user is never told)", PY),
    ("py-mktemp", "WARN", "safety", r"tempfile\.mktemp\(", "tempfile.mktemp is racy: use mkstemp or NamedTemporaryFile", PY),
    ("py-assert-guard", "NOTE", "errors", r"^\s*assert\s+.*(?:auth|permission|user|admin|valid)", "assert used as a guard: it disappears under python -O", PY),
    ("py-hardcoded-tmp", "NOTE", "safety", r"[\"']/tmp/[\w.-]+[\"']", "hard-coded /tmp path: other users can create it first", PY),
]
COMPILED = [(r, s, a, re.compile(x, re.I), m, e) for r, s, a, x, m, e in LINE_RULES]
# SC-65: rules about code, not text. In JavaScript and TypeScript they are matched against the code with every string
# and comment blanked (the mutation tester's own scanner), so `// never use document.write(` or a string that mentions
# `.forEach(async` is not a finding. Rules that look inside strings on purpose (javascript: URLs, string timers) and the
# markup rules are left alone.
CODE_ONLY = {"doc-write", "contextual-fragment", "srcdoc", "dynamic-href", "loose-equality-null", "unsafe-finally", "await-in-foreach", "promise-no-catch", "outerhtml"}
JS_CODE = {".js", ".mjs", ".cjs", ".ts"}
def code_lines(rel, suffix, text):
    if suffix not in JS_CODE: return None
    try:
        import scan_mutation
        return scan_mutation.code_view(pathlib.PurePath(rel), text)
    except Exception: return None

def guarded(name, fn, rel, emit, *a):
    """Run one lens on one file. A crash (a RecursionError on a hostile file, a bug) is reported as a row and the scan
    goes on: a broken lens never hides the others, and never passes silently. CRITIC_TEST_CRASH_LENS=<name> makes that
    lens crash, so the script tests can prove this."""
    try:
        if os.environ.get("CRITIC_TEST_CRASH_LENS") == name: raise RuntimeError("crash requested by CRITIC_TEST_CRASH_LENS")
        return fn(*a)
    except Exception as e:
        emit("WARN", "lens-crashed", "structure", rel, f"the {name} check crashed on this file ({type(e).__name__}: {str(e)[:80]}); its rows for this file are missing")

def scan(rel, suffix, text, emit):
    lines = text.split("\n")
    parsed = False
    if suffix in PY:
        try: scan_python.scan(rel, text, emit); parsed = True  # the parser-based checks replace the text patterns
        except (SyntaxError, ValueError, RecursionError): pass  # unparseable file: fall back to the text patterns below
        if parsed and scan_tests.is_test_file(rel):
            guarded("scan_tests", scan_tests.scan, rel, emit, rel, text, emit)  # the tests-of-the-tests lens (SC-48)
    view = code_lines(rel, suffix, text)
    for i, l in enumerate(lines, 1):
        if len(l) > 3000: continue
        cl = view[i - 1] if view is not None and i - 1 < len(view) else l
        for rid, sev, area, rx, msg, exts in COMPILED:
            if parsed and exts is PY: continue
            if suffix in exts and rx.search(cl if rid in CODE_ONLY else l): emit(sev, rid, area, f"{rel}:{i}", msg, l)
        m = re.search(r"\.outerHTML\s*\+?=\s*(.+)", l)
        if m and suffix in CODE and not SAFE_ARG.fullmatch(m.group(1)) and (view is None or re.search(r"\.outerHTML\s*\+?=", cl)): emit("WARN", "outerhtml", "safety", f"{rel}:{i}", "outerHTML set from a non-literal: escape or sanitise it", l)
    if suffix in STYLE:
        imp = len(re.findall(r"!important", text))
        if imp > 10: emit("NOTE", "important-overuse", "theming", rel, f"{imp} uses of !important: the cascade has been given up on", "")
        hovers = {h.strip() for h in re.findall(r"([^{}\n,]+?):hover\b", text)}; focuses = {h.strip() for h in re.findall(r"([^{}\n,]+?):focus(?:-visible|-within)?\b", text)}  # trimmed before comparing
        only = sorted(h.strip() for h in hovers - focuses if h.strip() and "(" not in h and not h.strip().startswith("@"))  # @media (hover:hover) is a query, not a selector
        if only: emit("NOTE", "hover-only", "a11y", rel, f"hover styles with no matching focus style: {', '.join(only[:4])} (keyboard users miss the cue)", "")
