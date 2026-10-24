#!/usr/bin/env python3
"""Curmudgeon scripted checks (v4): the free checks that would otherwise cost reading time. Nothing needs installing beyond
Python (and Playwright + Chromium for the runtime half; axe-core if present).

usage: critic_scan.py SRC [--root DIR] [--page PAGE.html|URL] [--out DIR] [--axe axe.min.js]
                          [--exclude GLOB ...] [--no-interact] [--allow-live] [--online]
                          [--mutate FILE ...] [--test-cmd CMD] [--project-checks] [--no-project-rules] [--baseline save|compare] [--budget-kb N]

Modules (all our own code; the tools named are where the idea came from): secrets (gitleaks), HTML validity (Nu Html
Checker), structure: layers, cycles, dead code, copy-paste (dependency-cruiser, knip, jscpd), extra JS/CSS and WCAG 2.2
rules (ESLint, no-unsanitized, Stylelint), dependencies with an optional OSV lookup (OSV-Scanner), mutation testing
(Stryker), WCAG 2.2 + incomplete axe results, focus hidden behind other content (2.4.11, Tab and Shift+Tab),
a screen-reader view (accessibility tree), speed budget (Lighthouse-style), visual baselines (screenshot diff), and
results from earlier CI runs (SARIF and JUnit files already in the project) read as evidence.

SRC may be a folder or a single file. ROOT (default: CRITIC_ROOT, else the current folder) is where .critic/ lives;
rows are keyed by path relative to ROOT so recorded false positives match whichever SRC is scanned.

Every row has an evidence id (S001…) and a rule id. Every check family reports pass, fail, unavailable (tool missing),
blocked (could not run) or n/a (nothing for it to look at: no page given, no manifest), derived from its own rows.
Only blocked and unavailable make a run DEGRADED. A false positive recorded with
`critic_ledger.py fp RULE_ID WHERE "why"` suppresses only that rule at that exact place, and is listed, never hidden.

Safety: the click probe never sends anything. Every non-GET request and every request to another origin is aborted
and reported as "would have sent", controls named like destructive actions are not clicked, and pages that aren't
on localhost or a file are refused unless --allow-live is given."""
import argparse, fnmatch, json, os, pathlib, re, signal, subprocess, sys, time, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scan_secrets, scan_html, scan_graph, scan_deps, scan_rules_extra, scan_mutation
from critic_findings import log_run, refuse_linked_state

CODE = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte", ".html", ".htm"}
MARKUP = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte"}
STYLE = {".css", ".scss", ".less"} | MARKUP
SCAN_EXT = CODE | STYLE | {".py"}
CONFIG_EXT = {".yml", ".yaml", ".sql", ".toml"}  # read by rule files and by line rules that name these types; never by code rules
def is_config(p, rel):
    n = p.name.lower()
    return p.suffix.lower() in CONFIG_EXT or n == "dockerfile" or n.startswith("dockerfile.") or n.endswith(".dockerfile") or rel.startswith(".github/")
SKIP = {"node_modules", "dist", "build", "vendor", ".git", "__pycache__", ".next", "coverage", ".critic", ".venv", "venv"}
MAX_BYTES = 2_000_000
SELF = pathlib.Path(__file__).resolve()
R, CHECKS, SUPPRESSED, FP = [], {}, [], []

def f(sev, rule, area, where, what, ev=""):
    for x in FP:
        if x.get("rule") in (rule, rule[5:] if rule.startswith("rule-") else None) and str(x.get("where")) == str(where):  # rulings saved before rule- ids still apply
            SUPPRESSED.append({"rule": rule, "where": where, "what": what, "why": x.get("why", "")}); return
    level = "runtime" if area.startswith(("a11y-", "runtime", "ux", "responsive", "perf-rt", "visual")) else ("ci" if area == "ci" else "source")
    R.append({"sev": sev, "rule": rule, "area": area, "where": str(where), "what": what, "evidence": ev.strip()[:160], "level": level})

NA = "n/a"  # not applicable: nothing for this check to look at (no page given, no manifest). Never DEGRADED.
def state(name, s, note=""): CHECKS[name] = {"state": s, "note": note}
def family_state(areas, note=""):
    rows = [x for x in R if x["area"] in areas]
    return ("fail" if any(x["sev"] == "FAIL" for x in rows) else "pass"), note

# (rule id, severity, area, regex, message, extensions, flags)
RULES = [
    ("eval", "FAIL", "safety", r"\beval\(|new Function\(", "eval / new Function", CODE, 0),
    ("raw-html", "WARN", "safety", r"dangerouslySetInnerHTML|v-html=|insertAdjacentHTML\(", "raw HTML injection point", CODE, 0),
    ("url-unencoded", "WARN", "safety", r"fetch\(\s*`[^`]*\?[^`]*\$\{(?!\s*(?:encodeURIComponent|new URLSearchParams|\w*(?:[pP]arams|qs)(?:\.toString\(\))?\s*\}))", "URL query built from raw values (no encodeURIComponent / URLSearchParams)", CODE, 0),
    ("empty-catch", "WARN", "errors", r"catch\s*(\(\s*\w*\s*\))?\s*\{\s*\}", "empty catch swallows the error", CODE, 0),
    ("log-only-catch", "NOTE", "errors", r"catch\s*\(\s*(\w+)\s*\)\s*\{\s*console\.(log|error)\(\s*\1\s*\)\s*;?\s*\}", "catch only logs; the user is never told", CODE, 0),
    ("fire-forget", "WARN", "errors", r"^\s*fetch\(", "fetch result never awaited or handled (fire and forget)", CODE, 0),
    ("storage-no-try", "WARN", "state", r"^(?!.*\btry\b).*\b(localStorage|sessionStorage)\.(getItem|setItem|removeItem)\(", "storage call outside try (throws in private mode or when full)", CODE, 0),
    ("parse-no-try", "WARN", "state", r"^(?!.*\btry\b).*\bJSON\.parse\(", "JSON.parse outside try (bad data crashes the load)", CODE, 0),
    ("time-id", "NOTE", "state", r"\bid\s*[:=]\s*(String\()?Date\.now\(\)", "id from Date.now() (collides on fast actions)", CODE, 0),
    ("await-loop", "NOTE", "async", r"\b(for|while)\s*\(.*\)\s*\{[^}]*\bawait\b", "await inside a loop (serial; consider batching)", CODE, 0),
    ("interval", "NOTE", "async", r"\bsetInterval\(", "setInterval: confirm it is cleared", CODE, 0),
    ("per-keystroke", "NOTE", "async", r"\.oninput\s*=\s*(async\s*)?\w+\s*;|addEventListener\(\s*[\"']input[\"']\s*,\s*(async\s*)?\w+\s*\)", "request-per-keystroke candidate: confirm debounce and stale-response guard", CODE, 0),
    ("html-append", "NOTE", "perf", r"\.innerHTML\s*\+=", "innerHTML += (re-parses the whole container each time; quadratic in a loop)", CODE, 0),
    ("outline-none", "WARN", "a11y", r"outline\s*:\s*(none|0)\b", "focus outline removed: confirm a :focus-visible replacement", STYLE, 0),
    ("click-div", "WARN", "a11y", r"<(div|span)[^>]*\bon[Cc]lick=", "clickable div/span (not focusable, no role)", MARKUP, 0),
    ("img-alt", "WARN", "a11y", r"<img(?![^>]*\balt=)[^>]*>", "image without alt", MARKUP, 0),
    ("zoom-off", "FAIL", "a11y", r"user-scalable\s*=\s*no|maximum-scale\s*=\s*1(\.0)?\b", "zoom disabled in the viewport (WCAG 1.4.4)", MARKUP, 0),
    ("fixed-width", "WARN", "layout", r"(?<![-\w])(min-)?width\s*:\s*([6-9]\d\d|[1-9]\d{3,})px", "fixed width of 600 px or more (sideways scroll on phones, WCAG 1.4.10)", STYLE, 0),
    ("domain-math", "NOTE", "domain", r"\b(tax|vat|discount|surcharge|tier|loyalty)\b.*[*/]\s*\d|\d\.\d+\s*[*/].*\b(total|price|amount|revenue)\b", "pricing arithmetic: confirm it lives in the domain layer, not in render code", CODE, re.I),
    ("todo", "NOTE", "hygiene", r"\b(TODO|FIXME|XXX|HACK)\b", "leftover TODO/FIXME", CODE | {".py"}, 0),
    ("console-log", "NOTE", "hygiene", r"\bconsole\.log\(", "leftover console.log", CODE, 0),
    ("placeholder", "WARN", "anti-ai", r"lorem ipsum|John Doe|Jane Doe|Acme(?: Corp)?\b|example\.com|Your (text|title) here", "placeholder content left in", CODE | STYLE, re.I),
    ("generic-copy", "NOTE", "anti-ai", r">\s*Click here\s*<|Welcome to (my|our|the) ", "generic copy (\"Click here\", \"Welcome to…\")", MARKUP, re.I),
    ("ai-palette", "NOTE", "anti-ai", r"#6366f1|#4f46e5|#8b5cf6|#7c3aed|#a855f7|indigo-(500|600)|from-(purple|violet|indigo)-\d+", "stock indigo/violet palette", STYLE | CODE, re.I),
    ("cream-look", "NOTE", "anti-ai", r"#F4F1EA|#D97757", "cream-and-terracotta look (a current AI default)", STYLE | CODE, re.I),
    ("default-font", "NOTE", "anti-ai", r"font-family\s*:\s*['\"]?(Inter|Roboto|Geist|Space Grotesk|Plus Jakarta Sans|Fraunces)\b", "overused default typeface", STYLE, re.I),
    ("gradient-text", "NOTE", "anti-ai", r"background-clip\s*:\s*text", "gradient text", STYLE, 0),
    ("bounce", "NOTE", "anti-ai", r"cubic-bezier\([^)]*,\s*(1\.[1-9]|[2-9])", "bounce / elastic easing", STYLE, 0),
    ("eyebrow", "NOTE", "anti-ai", r"[A-Z]{3,}\s+—\s+[A-Z]{3,}|class=[\"'](eyebrow|kicker|overline)", "template chrome: eyebrow / 'WORD — fragment' label", MARKUP, 0),
    ("arrow-cta", "NOTE", "anti-ai", r"<(button|a)\b[^>]*>[^<]*→", "arrow appended to button or link text", MARKUP, 0),
    ("narrating-comment", "NOTE", "anti-ai", r"^\s*//\s*(Render|Main|Handle|Load|Init|Setup|Get|Set|Create|Update|API client|Helper)s?\b[\w ]{0,30}$", "comment that narrates the obvious", {".js", ".mjs", ".ts", ".jsx", ".tsx"}, re.I),
]
SAFE_EXPR = re.compile(r"^\s*([\w.$]*\b(esc|escape|escapeHtml|escAttr|sanitize|DOMPurify\.sanitize|encodeURIComponent|Number|parseInt|parseFloat)\(|[\w.]+\.(length|size|toFixed\(\d*\)|toLocaleString\(\))\s*$|\d+\s*$|\w+\s*\?\s*[\"'][^\"']*[\"']\s*:\s*[\"'][^\"']*[\"']\s*$)")

def unescaped_html(rel, lines):
    for i, l in enumerate(lines, 1):
        if not re.search(r"(innerHTML|outerHTML)\s*\+?=\s*`|insertAdjacentHTML\([^,]+,\s*`", l): continue
        bad = [e for e in re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", l) if not SAFE_EXPR.match(e)]
        if bad: f("WARN", "unescaped-html", "safety", f"{rel}:{i}", f"HTML built from a template with unescaped value(s): {', '.join(b.strip()[:30] for b in bad[:3])}", l)

def in_try(lines, i):
    for j in range(i - 1, max(0, i - 9), -1):
        l = lines[j - 1]
        if re.search(r"\bcatch\b|\bfinally\b", l) and j != i: return False
        if re.search(r"\btry\s*\{|\btry:", l): return True
    return False

def css_detector(rel, text):
    from collections import Counter
    radii = [r.strip() for r in re.findall(r"border-radius\s*:\s*([^;}]+)", text)]; shadows = [s.strip() for s in re.findall(r"box-shadow\s*:\s*([^;}]+)", text)]
    px = [r for r in radii if "%" not in r]
    if len(radii) >= 4 and px:
        top, k = Counter(px).most_common(1)[0]
        if k >= 0.75 * len(radii): f("NOTE", "one-radius", "anti-ai", rel, f"one border-radius ({top}) on {k} of {len(radii)} rules: no hierarchy")
    if len(shadows) >= 2 and len(set(shadows)) == 1: f("NOTE", "one-shadow", "anti-ai", rel, f"the same shadow ({shadows[0]}) on every surface")
    if re.search(r"animation[^;]*\binfinite\b", text) and "prefers-reduced-motion" not in text: f("WARN", "motion", "a11y", rel, "infinite animation with no prefers-reduced-motion rule (WCAG 2.2.2 / 2.3.3)")
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        sel, body = m.group(1).strip()[-40:], m.group(2)
        if re.search(r"overflow\s*:\s*hidden", body) and re.search(r"white-space\s*:\s*nowrap", body) and "text-overflow" not in body:
            f("WARN", "clipped-text", "layout", f"{rel} {sel}", "text clipped with no ellipsis or way to read it")
        fs = re.search(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", body)
        if fs and float(fs.group(1)) < 12: f("NOTE", "tiny-text", "type", f"{rel} {sel}", f"tiny text ({fs.group(1)}px, under 12px)")
        ls = re.search(r"letter-spacing\s*:\s*(\d*\.?\d+)em", body)
        if ls and float(ls.group(1)) >= 0.1: f("NOTE", "wide-tracking", "anti-ai", f"{rel} {sel}", "wide tracking on small labels (the all-caps eyebrow look)")
    if re.search(r"(?<!-)(color|background)\s*:\s*#(?:[0-9a-f]{3}){1,2}\b", text, re.I) and not re.search(r"--[\w-]+\s*:", text):
        f("NOTE", "raw-hex", "theming", rel, "colours are raw hex values with no tokens (custom properties)")

ONLY = None  # set by --only: the exact files (paths relative to --root) to scan, for the background check
def walk(src, excludes):
    if ONLY is not None:  # exact files someone changed: scanned even under build/ or vendor/, never outside the root
        top = SCAN_ROOT.resolve(); items = []
        for r in sorted(ONLY):
            q = SCAN_ROOT / r
            try: real = q.resolve()
            except OSError: continue
            if ".." in pathlib.PurePath(r).parts or not real.is_relative_to(top) or real != top / pathlib.PurePath(r) or not q.is_file(): continue
            if ".critic" in pathlib.PurePath(r).parts: continue
            items.append(q)
    else: items = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
    for p in items:
        try:
            rel_parts = () if ONLY is not None else (p.relative_to(src).parts if src.is_dir() else (p.name,))
            if set(rel_parts) & SKIP or p.resolve() == SELF: continue
            if any(fnmatch.fnmatch(str(p), g) or fnmatch.fnmatch(p.name, g) for g in excludes): continue
            if p.stat().st_size > MAX_BYTES: continue
            yield p
        except OSError: continue

TEXTS = {}
CONFIG_TEXTS = {}  # config files: rule files and line rules for their types read them; the code checks don't
SCAN_ROOT = pathlib.Path.cwd()  # set in main from --root, so every run-log line lands in the project being scanned
NO_PROJECT_RULES = False  # set by --no-project-rules (the background stop check uses it)
RULE_AREAS = {"safety", "errors", "state", "async", "perf", "a11y", "layout", "domain", "html", "theming", "ux", "structure", "deps"}
LIMIT = "\x00limit\x00"  # marks a note that a limit cut the rule set (a file name can't contain it)
def load_rule_files(root):
    """Rule files: the plugin's built-in rules/ folder, then the project's .critic/rules/. Data only: nothing runs.
    Each bad rule or file is reported once and skipped; it never stops the scan. Every rule's rows are reported as
    rule-<id>, so a rule file can never pose as a built-in check. A project's files are read only when they are
    plain files (no links, no devices) of at most 256 KB, and not at all under --no-project-rules."""
    rules, bad, taken = [], [], set()
    budget = {"files": 50, "rules": 2000, "bytes": 2 * 1024 * 1024}  # a project's rule files, all together
    folders = [(pathlib.Path(__file__).resolve().parent.parent / "rules", False)]
    if not NO_PROJECT_RULES: folders.append((root / ".critic" / "rules", True))
    for folder, is_project in folders:
        if not folder.is_dir() or folder.is_symlink(): continue
        found, more = [], False
        with os.scandir(folder) as it:  # a bounded listing: a folder of a million files is never read in full
            for e in it:
                if e.name.endswith(".json"):
                    if len(found) >= 500: more = True; break
                    found.append(folder / e.name)
        if more: bad.append(LIMIT + f"project rule files: over 500 .json files in {folder.name}/, only the first 500 listed were considered")
        for rf in sorted(found):
            if rf.is_symlink() or not rf.is_file(): bad.append(f"{rf.name}: not a plain file (links and devices are never read)"); continue
            if rf.stat().st_size > 256 * 1024: bad.append(LIMIT + f"{rf.name}: over 256 KB, not read"); continue
            if is_project:
                budget["files"] -= 1; budget["bytes"] -= rf.stat().st_size
                if budget["files"] < 0 or budget["bytes"] < 0 or budget["rules"] <= 0:
                    bad.append(LIMIT + f"project rule files stopped at {rf.name}: over the limit of 50 files, 2 MB or 2,000 rules in all"); break
            try: items = json.loads(rf.read_text(encoding="utf-8"))
            except Exception as e: bad.append(f"{rf.name}: not valid JSON ({str(e)[:80]})"); continue
            if not isinstance(items, list): bad.append(f"{rf.name}: must hold a JSON list of rules"); continue
            for r in items[:200]:
                try:
                    if not isinstance(r, dict): raise ValueError("a rule must be a JSON object")
                    rid, sev, area, pat, msg = r["id"], r["severity"], r["area"], r["pattern"], r["message"]
                    globs = r.get("files", [])
                    if not isinstance(rid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", rid) or rid in taken: raise ValueError("id must be lowercase letters, digits and dashes, used once")
                    if rid.startswith("file-"): raise ValueError("ids starting with file- are reserved for the plugin's own rule-file notes")
                    if sev not in ("FAIL", "WARN", "NOTE") or area not in RULE_AREAS: raise ValueError("severity or area not allowed")
                    if not isinstance(pat, str) or not pat or len(pat) > 300: raise ValueError("pattern missing or over 300 characters")
                    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs): raise ValueError("files must be a list of filename patterns")
                    if not isinstance(msg, str) or not msg.strip(): raise ValueError("message missing")
                    re.compile(pat)  # reject a broken pattern here; a project's patterns then run in rule_runner.py under a time limit
                    if is_project:
                        if sev == "FAIL": sev = "WARN"  # a repo's own rules can warn, never fail: only the plugin's checks become automatic findings
                        budget["rules"] -= 1
                        if budget["rules"] < 0:
                            bad.append(LIMIT + f"project rules stopped partway through {rf.name}: over the limit of 2,000 rules in all"); break
                    rules.append(("rule-" + rid, sev, area, pat, msg[:200], globs, is_project)); taken.add(rid)
                except Exception as e: bad.append(f"{rf.name}: rule {r.get('id', '?') if isinstance(r, dict) else '?'} skipped ({str(e)[:80]})")
            if len(items) > 200: bad.append(LIMIT + f"{rf.name}: only the first 200 rules were read")
    return rules, bad

def static(src, root, excludes):
    n = texts = 0; secrets_only = {}
    custom, bad = load_rule_files(root)
    limits = [b[len(LIMIT):] for b in bad if b.startswith(LIMIT)]  # a limit cut the rule set: always shown, never behind the cap
    rest = [b for b in bad if not b.startswith(LIMIT)]
    for b in limits: f("NOTE", "rule-file-limit", "structure", "rules", b)
    for b in rest[:20]: f("NOTE", "rule-file-invalid", "structure", "rules", b)
    if len(rest) > 20: f("NOTE", "rule-file-invalid", "structure", "rules", f"{len(rest) - 20} more rule-file problems not listed")
    for p in walk(src, excludes):
        try: text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError): continue
        try: rel = str(p.resolve().relative_to(root))
        except ValueError: rel = str(p)
        lines = text.split("\n"); texts += 1
        scan_secrets.scan(rel, text, f)  # every text file, dotfiles and configs included
        if p.suffix not in SCAN_EXT:
            if is_config(p, rel):
                CONFIG_TEXTS[rel] = text
                for i, l in enumerate(lines, 1):
                    for rid, sev, area, rx, msg, exts, fl in RULES:
                        if exts and p.suffix in exts and re.search(rx, l, fl): f(sev, rid, area, f"{rel}:{i}", msg, l)
            else: secrets_only[p.suffix.lower() or p.name] = secrets_only.get(p.suffix.lower() or p.name, 0) + 1
            continue
        n += 1; TEXTS[rel] = text
        scan_rules_extra.scan(rel, p.suffix, text, f)
        if p.suffix in (".html", ".htm"): scan_html.scan(rel, text, f)
        if len(lines) > 400: f("WARN", "long-file", "structure", rel, f"{len(lines)} lines in one file")
        longl = [i for i, l in enumerate(lines, 1) if len(l) > 300 and not p.name.endswith(".min.js")]
        if longl: f("NOTE", "long-lines", "structure", f"{rel}:{longl[0]}", f"{len(longl)} lines over 300 characters")
        if p.suffix in CODE and re.search(r"\bfetch\(", text) and not re.search(r"\.ok\b|\.status\b", text):
            f("WARN", "status-unchecked", "errors", rel, "fetch used but no response status is ever checked (errors look like success)")
        for i, l in enumerate(lines, 1):
            for rid, sev, area, rx, msg, exts, fl in RULES:
                if exts and p.suffix not in exts: continue
                if not re.search(rx, l, fl): continue
                if area in ("state", "async") and in_try(lines, i): continue
                if rid == "outline-none" and ":focus-visible" in text: continue
                f(sev, rid, area, f"{rel}:{i}", msg, l)
        if p.suffix in CODE: unescaped_html(rel, lines)
        if p.suffix in (".css", ".scss", ".less"): css_detector(rel, text)
        elif p.suffix in MARKUP:
            for blk in re.findall(r"<style[^>]*>(.*?)</style>", text, re.S): css_detector(rel, blk)
    # the plugin's own rule files run here; a project's .critic/rules run in a separate process with a time limit,
    # because anyone who wrote the repository could have written them
    builtin = [r[:6] for r in custom if not r[6]]; project = [r[:6] for r in custom if r[6] and not NO_PROJECT_RULES]
    for rid, sev, area, pat, msg, globs in builtin:
        rx = re.compile(pat)
        for rel, text in {**TEXTS, **CONFIG_TEXTS}.items():
            if rel in CONFIG_TEXTS and not globs: continue  # config is read only by a rule that names its file type
            if globs and not any(fnmatch.fnmatch(pathlib.PurePath(rel).name, g) or fnmatch.fnmatch(rel, g) for g in globs): continue
            for i, l in enumerate(text.split("\n"), 1):
                if len(l) <= 2000 and rx.search(l): f(sev, rid, area, f"{rel}:{i}", msg, l[:160])
    if project and (TEXTS or CONFIG_TEXTS):
        try:
            log_run(SCAN_ROOT, "script", f"rule_runner.py ({len(project)} project rule(s), 20 s limit)")
            r = subprocess.run([sys.executable, "-I", str(pathlib.Path(__file__).resolve().parent / "rule_runner.py")], input=json.dumps({"rules": project, "files": list({**TEXTS, **CONFIG_TEXTS}.items()), "config": list(CONFIG_TEXTS)}),
                               capture_output=True, text=True, timeout=20)
            if r.returncode != 0: f("WARN", "rule-file-failed", "structure", ".critic/rules", f"the project's rule files could not run (exit {r.returncode}); their results are missing")
            for row in json.loads(r.stdout or "[]"): f(*row)
        except subprocess.TimeoutExpired: f("WARN", "rule-file-timeout", "structure", ".critic/rules", "the project's rule files took over 20 s and were stopped (a pattern may be too slow); their results are missing")
        except ValueError: f("NOTE", "rule-file-invalid", "structure", ".critic/rules", "the rule runner returned no readable results")
    if texts: state("static", *family_state({"safety", "errors", "state", "async", "perf", "a11y", "layout", "domain", "html", "theming", "ux"}, f"{n} source files, {len(CONFIG_TEXTS)} config files, {texts} text files checked for secrets, {len(custom)} rule-file rules"
                              + (("; not checked beyond secrets: " + ", ".join(f"{k} {v}" for k, v in sorted(secrets_only.items(), key=lambda kv: -kv[1])[:8])) if secrets_only else "")))
    else: state("static", "blocked", "no readable files found")
    try:
        g = scan_graph.scan(root, TEXTS, f)
        skipped = ", ".join(f"{k} {v}" for k, v in sorted(g["not_analysed"].items(), key=lambda kv: -kv[1]) if k not in (".html", ".htm", ".css", ".scss", ".less"))
        note = f"{g['modules']} modules, {g['import_edges']} imports, {g['cycles']} cycles, {g['duplicates']} duplicates" + (f"; import graph not analysed for {skipped}" if skipped else "")
        if g["modules"]: state("structure", *family_state({"structure"}, note))
        else: state("structure", NA, "no JavaScript, TypeScript or Python modules to map" + (f"; not analysed: {skipped}" if skipped else ""))
    except Exception as e: state("structure", "blocked", f"{type(e).__name__}: {str(e)[:100]}")
    return n

def ci_evidence(root, out=None):
    """Read results that earlier test or lint runs already left in the project, instead of re-running them.
    Curmudgeon's own outputs (anything under .critic/ or the --out folder) are never read back as evidence."""
    import xml.etree.ElementTree as ET
    seen = files = unreadable = 0
    own = {"scan.sarif", "findings.sarif"}
    def mine(p): return ".critic" in p.parts or p.name in own or (out is not None and str(p.resolve()).startswith(str(out.resolve())))
    for p in list(root.rglob("*.sarif"))[:20]:
        if set(p.parts) & SKIP or mine(p): continue
        try:
            j = json.loads(p.read_text()); files += 1
            for run in j.get("runs", []):
                tool = run.get("tool", {}).get("driver", {}).get("name", "tool")
                for r in run.get("results", [])[:50]:
                    loc = (r.get("locations") or [{}])[0].get("physicalLocation", {})
                    where = f"{loc.get('artifactLocation', {}).get('uri', '')}:{loc.get('region', {}).get('startLine', '')}"
                    f({"error": "WARN"}.get(r.get("level"), "NOTE"), f"ci-{tool}-{r.get('ruleId', '')}", "ci", where, f"{tool}: {r.get('message', {}).get('text', '')[:150]}"); seen += 1
        except Exception: unreadable += 1; continue
    for p in list(root.rglob("*.xml"))[:40]:
        if set(p.parts) & SKIP or mine(p): continue
        try:
            try: t = ET.parse(p).getroot()
            except ET.ParseError:
                if re.search(r"<testsuites?\b", p.read_text(encoding="utf-8", errors="replace")[:4000]): unreadable += 1
                continue
            if t.tag not in ("testsuite", "testsuites"): continue
            files += 1
            for tc in t.iter("testcase"):
                bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
                if bad is not None:
                    f("WARN", "ci-test-failure", "ci", str(p.relative_to(root)), f"test failing in the last recorded run: {tc.get('classname', '')} {tc.get('name', '')}", (bad.get("message") or "")[:120]); seen += 1
        except Exception: continue
    bad = f"; {unreadable} result file(s) could not be read" if unreadable else ""
    if not files and unreadable: state("ci", "blocked", f"{unreadable} CI result file(s) found but none could be read (damaged or cut short)")
    elif not files: state("ci", NA, "no earlier CI results found (no SARIF or JUnit files to read)")
    else: state("ci", "fail" if seen else "pass", f"{files} result file(s) read from earlier runs, {seen} problem(s){bad}")

def project_checks(root, timeout=600):
    """Run the commands listed under '## Scripted checks' in .critic/rules.md ("- name: command"). Each one passes on
    exit 0 and fails otherwise; its last output lines are kept as evidence. Opt-in (--project-checks): a cloned repo can
    ship its own rules.md, and its commands must never run just because something was scanned."""
    p = root / ".critic" / "rules.md"
    if not p.exists(): return
    sec, cmds = False, []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "): sec = line.strip().lower() == "## scripted checks"; continue
        m = re.match(r"\s*-\s*([\w .-]+?)\s*:\s*`?(.+?)`?\s*$", line) if sec else None
        if m: cmds.append((m.group(1).strip(), m.group(2).strip()))
    if not cmds: return
    bad = 0
    for name, cmd in cmds[:10]:
        try:
            # commands written by the project owner in rules.md; run in their own process group so a timeout kills all of it
            log_run(root, "command", f"project check {name}: {cmd}")
            pr = subprocess.Popen(cmd, shell=True, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            try: outp, _ = pr.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try: os.killpg(pr.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
                pr.communicate(); raise
            if pr.returncode != 0:
                bad += 1; tail = (outp or "").strip().splitlines()[-3:]
                f("FAIL", f"project-check-{name}", "ci", f"rules.md: {name}", f"project check “{name}” failed (exit {pr.returncode})", " / ".join(tail))
        except subprocess.TimeoutExpired:
            bad += 1; f("FAIL", f"project-check-{name}", "ci", f"rules.md: {name}", f"project check “{name}” timed out after {timeout} s (stopped)")
    state("project-checks", "fail" if bad else "pass", f"{len(cmds[:10])} check(s) from rules.md, {bad} failed")

def find_axe(arg):
    cands = [arg] if arg else []
    cands += [d / "node_modules/axe-core/axe.min.js" for d in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents]]
    log_run(SCAN_ROOT, "command", "npm root -g (to find axe-core)")
    try: cands.append(pathlib.Path(subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=20).stdout.strip()) / "axe-core/axe.min.js")
    except Exception: pass
    return next((pathlib.Path(c) for c in cands if c and pathlib.Path(c).exists()), None)

DESTRUCTIVE = re.compile(r"\b(delete|remove|refund|pay|purchase|buy|send|submit|transfer|charge|cancel|archive|publish|post|sign ?out|log ?out|wipe|reset|destroy|approve|confirm)\b", re.I)
FOCUS_REST = r"""() => {
  const label = (e) => (e.getAttribute('aria-label') || e.textContent || e.id || e.tagName).trim().slice(0, 40);
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const pick = (s) => [s.outlineStyle, s.outlineWidth, s.boxShadow, s.backgroundColor, s.borderColor, s.color, s.textDecorationLine].join('|');
  const els = [...document.querySelectorAll('button, [role=button], a[href], [onclick], input, select, textarea, summary, span, div, li')]
    .filter(e => vis(e) && !e.disabled && e.getAttribute('aria-disabled') !== 'true' && (e.matches('button,[role=button],a[href],[onclick],input,select,textarea,summary') || (getComputedStyle(e).cursor === 'pointer' && !e.closest('button,a')))).slice(0, 40);
  return els.map((e, i) => { e.setAttribute('data-critic-f', i); const r = e.getBoundingClientRect();
    return { i, name: label(e), rest: pick(getComputedStyle(e)), small: !e.matches('input[type=checkbox],input[type=radio]') && (r.width < 24 || r.height < 24), size: `${Math.round(r.width)}×${Math.round(r.height)}` }; });
}"""
FOCUS_NOW = r"""() => { const e = document.activeElement; if (!e || !e.hasAttribute('data-critic-f')) return null;
  const s = getComputedStyle(e); return [e.getAttribute('data-critic-f'), [s.outlineStyle, s.outlineWidth, s.boxShadow, s.backgroundColor, s.borderColor, s.color, s.textDecorationLine].join('|')]; }"""
CANDIDATES = "() => [...document.querySelectorAll('button, [role=button], [onclick], a[href], span, div, li')].filter(e => e.getBoundingClientRect().width > 0 && !(e.form && (e.type === 'submit' || e.getAttribute('type') === null && e.tagName === 'BUTTON') && !e.form.checkValidity()) && (e.matches('button,[role=button],[onclick]') || (getComputedStyle(e).cursor === 'pointer' && !e.closest('button,a')))).slice(0, 15).map((e, i) => { e.setAttribute('data-critic-i', i); return (e.getAttribute('aria-label') || e.textContent || e.id || '').trim().slice(0, 40); })"
SIG = "() => document.body.innerText + '|' + document.querySelectorAll('*').length + '|' + location.href + '|' + [...document.querySelectorAll('[aria-expanded],[aria-pressed],dialog[open]')].map(e => (e.getAttribute('aria-expanded')||'') + (e.getAttribute('aria-pressed')||'') + e.open).join('')"

OBSCURED_JS = r"""() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return null;
  let vis = 0, n = 0, by = '';
  for (let i = 1; i <= 5; i++) for (let j = 1; j <= 5; j++) {
    const x = r.left + r.width * i / 6, y = r.top + r.height * j / 6;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) { n++; continue; }
    const h = document.elementFromPoint(x, y); n++;
    if (h && (h === e || e.contains(h) || h.contains(e))) vis++; else if (h && !by) by = (h.id ? '#' + h.id : h.tagName.toLowerCase() + (h.className && typeof h.className === 'string' ? '.' + h.className.split(' ')[0] : ''));
  }
  return { name: (e.getAttribute('aria-label') || e.textContent || e.id || e.tagName).trim().slice(0, 40), vis, n, by };
}"""

PERF_INIT = "window.__lcp = 0; window.__long = 0; try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = Math.max(window.__lcp, e.startTime); }).observe({ type: 'largest-contentful-paint', buffered: true }); new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long += Math.max(0, e.duration - 50); }).observe({ type: 'longtask', buffered: true }); } catch (e) {}"
PERF_READ = "() => { const r = performance.getEntriesByType('resource'); const n = performance.getEntriesByType('navigation')[0]; return { bytes: r.reduce((a, x) => a + (x.transferSize || x.encodedBodySize || 0), 0) + (n ? (n.transferSize || n.encodedBodySize || 0) : 0), requests: r.length + 1, lcp: window.__lcp || 0, long: window.__long || 0 }; }"

def guarded(name, fn):
    """Run one check family; an error marks only that family blocked."""
    try: fn()
    except Exception as e: state(name, "blocked", f"{type(e).__name__}: {str(e)[:120]}")

def has_userinfo(url):
    from urllib.parse import urlsplit
    try: return "@" in urlsplit(url).netloc
    except ValueError: return True

def is_local_url(url):
    """True only for http(s) on this computer: localhost or a loopback address (127.0.0.0/8, ::1), with no user@ part.
    Parsed, never pattern-matched: http://127.0.0.1:80@evil.example/ is evil.example."""
    import ipaddress
    from urllib.parse import urlsplit
    try: u = urlsplit(url); host = (u.hostname or "").lower()
    except ValueError: return False
    if has_userinfo(url) or u.scheme not in ("http", "https"): return False
    if host == "localhost": return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False

RUNTIME_CHECKS = ("page", "axe", "console", "keyboard", "focus", "obscured", "screen-reader", "interactive", "responsive", "speed", "screenshots", "visual")
def runtime(page, src, root, out, axe_arg, interact, allow_live, baseline=None, budget_kb=1500):
    names = RUNTIME_CHECKS
    if re.match(r"^https?://", page):
        if not is_local_url(page) and not allow_live:
            for k in names: state(k, "blocked", "live URL refused; rerun with --allow-live if this is a safe test copy")
            f("WARN", "live-refused", "runtime", page, "live URL refused: the scan would load a real site (pass --allow-live for a safe test copy)"); return {}
        if has_userinfo(page):  # http://127.0.0.1@evil.example/ goes to evil.example: never load an address that hides its real host
            for k in names: state(k, "blocked", "live URL refused: the address carries a user name or password (user@host), which hides the real host")
            f("WARN", "live-refused", "runtime", page, "live URL refused: an address with user@host is never loaded"); return {}
    try: from playwright.sync_api import sync_playwright
    except ImportError:
        for k in names: state(k, "unavailable", "Playwright not installed")
        f("WARN", "no-playwright", "runtime", "setup", "Playwright not installed: runtime checks unavailable; mark runtime findings [UNCERTAIN RISK]"); return {}
    stats, srv = {}, None
    if re.match(r"^https?://", page): url = page; origin = re.match(r"^(https?://[^/]+)", page).group(1)
    else:
        import functools, http.server, threading
        pp = pathlib.Path(page).resolve(); base = src if src.is_dir() and str(pp).startswith(str(src)) else pp.parent
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a): pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(base)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        # the page is served from this computer only (loopback); nothing is sent anywhere else
        origin = urllib.parse.urlunsplit(("http", "%s:%d" % srv.server_address[:2], "", "", "")); url = origin + "/" + pp.relative_to(base).as_posix()
    would_send = []
    from urllib.parse import urlsplit
    o_ = urlsplit(origin); own = (o_.scheme, o_.hostname, o_.port or (443 if o_.scheme == "https" else 80))
    def same_origin(u):
        try: x = urlsplit(u)
        except ValueError: return False
        if "@" in x.netloc: return False  # an address with user@host goes to that other host
        return (x.scheme, x.hostname, x.port or (443 if x.scheme == "https" else 80)) == own
    def guard_net(r):
        req = r.request
        if req.url.startswith(("data:", "blob:")): return r.continue_()
        if req.method not in ("GET", "HEAD", "OPTIONS") or not same_origin(req.url):
            would_send.append(f"{req.method} {req.url[:100]}"); return r.abort()
        return r.continue_()
    try:
        with sync_playwright() as pw:
            log_run(SCAN_ROOT, "command", f"Chromium (Playwright, headless) opening {page}")
            try: b = pw.chromium.launch()
            except Exception as e:
                for k in names: state(k, "unavailable", f"Chromium would not start: {str(e)[:80]}")
                return stats
            ctx = b.new_context(viewport={"width": 1360, "height": 900}); ctx.route("**/*", guard_net)
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("dialog", lambda d: d.dismiss())
            pg.add_init_script("window.__cls = 0; try { new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}")
            t0 = time.time()
            try: resp = pg.goto(url, wait_until="load", timeout=20000); pg.wait_for_timeout(800)
            except Exception as e: resp = None; state("page", "blocked", f"page did not load: {str(e)[:100]}")
            stats["load_ms"] = round((time.time() - t0) * 1000)
            if resp is None or (resp.status and resp.status >= 400):
                if resp is not None: state("page", "blocked", f"HTTP {resp.status} for {url}")
                for k in names[1:]: state(k, "blocked", "page did not load")
                b.close(); return stats
            state("page", "pass", f"HTTP {resp.status}")
            out.mkdir(parents=True, exist_ok=True)
            def shots():
                pg.screenshot(path=str(out / "desktop.png"), full_page=True)
            guarded("screenshots", shots)
            def axe_check():
                axe = find_axe(axe_arg)
                if not axe:
                    state("axe", "unavailable", "axe-core not found (npm i axe-core, or --axe PATH)"); return
                pg.add_script_tag(path=str(axe))
                res = pg.evaluate("async () => { const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } }); const m = (v) => [v.impact, v.id, v.help, v.nodes.length, v.nodes.slice(0,2).map(n => n.target.join(' ')).join('; ')]; return { v: r.violations.map(m), i: r.incomplete.map(m) }; }")
                vs = res["v"]
                for v in vs: f("FAIL" if v[0] in ("serious", "critical") else "WARN", f"axe-{v[1]}", "a11y-axe", "page", f"axe {v[1]} ({v[0]}): {v[2]} — {v[3]} element(s)", v[4])
                for v in res["i"]: f("NOTE", f"axe-incomplete-{v[1]}", "a11y-axe", "page", f"axe couldn't decide {v[1]}: {v[2]} — {v[3]} element(s) need a look (often contrast over images or gradients)", v[4])
                state("axe", "fail" if vs else "pass", f"{len(vs)} rule(s) violated, {len(res['i'])} undecided (WCAG 2.0–2.2 A/AA)")
            guarded("axe", axe_check)
            def keyboard():
                n = pg.evaluate("() => [...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex=\"-1\"])')].filter(e => e.getBoundingClientRect().width > 0 && !e.disabled).length")
                seen = set()
                for _ in range(min(60, n + 5)):
                    pg.keyboard.press("Tab"); seen.add(pg.evaluate("() => document.activeElement && document.activeElement !== document.body ? document.activeElement.outerHTML.slice(0, 80) : ''"))
                got = len([s for s in seen if s]); stats["focusable"] = n; stats["reached_by_tab"] = got
                if n and got < n: f("FAIL" if got == 0 else "WARN", "tab-reach", "a11y-keyboard", "keyboard", f"Tab reaches {got} of {n} focusable controls")
                state("keyboard", "fail" if n and got < n else ("pass" if n else NA), f"{got} of {n} reached" if n else "nothing focusable on the page")
            guarded("keyboard", keyboard)
            def focus():
                pg.evaluate("() => document.activeElement && document.activeElement.blur()"); pg.mouse.click(1, 1); pg.wait_for_timeout(100)
                els = pg.evaluate(FOCUS_REST); stats["controls_checked"] = len(els)  # rest styles, captured with nothing focused
                seen = {}
                for _ in range(len(els) + 10):  # real Tab presses, so :focus-visible styles apply as they do for users
                    pg.keyboard.press("Tab"); r = pg.evaluate(FOCUS_NOW)
                    if r: seen.setdefault(r[0], r[1])
                for e in els:
                    k = str(e["i"])
                    if k not in seen: f("FAIL", "not-focusable", "a11y-focus", f"control “{e['name']}”", "looks clickable but Tab never reaches it (WCAG 2.1.1)")
                    elif seen[k] == e["rest"]: f("FAIL", "no-focus-style", "a11y-focus", f"control “{e['name']}”", "no visible change on keyboard focus (WCAG 2.4.7)")
                    if e["small"]: f("NOTE", "small-target", "a11y-focus", f"control “{e['name']}” ({e['size']})", "under 24×24 px (WCAG 2.5.8 is a 2.2 AA rule; 44 px is 2.5.5, AAA)")
                state("focus", *family_state({"a11y-focus"}, f"{len(els)} controls, {len(seen)} reached by Tab"))
            guarded("focus", focus)
            def obscured():
                bad, partial, stops = [], [], 0
                for key in ("Tab", "Shift+Tab"):  # going backwards finds headers that cover what you tab back to
                    pg.evaluate("() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); }")
                    if key == "Shift+Tab": pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)"); pg.wait_for_timeout(100)
                    for _ in range(int(stats.get("focusable", 20)) + 5):
                        pg.keyboard.press(key); pg.wait_for_timeout(30); r = pg.evaluate(OBSCURED_JS)
                        if not r: continue
                        stops += 1
                        if r["vis"] == 0: bad.append(f"{r['name']} ({key}, covered by {r['by'] or 'other content'})")
                        elif r["vis"] < r["n"] / 2: partial.append(r["name"])
                for x in sorted(set(bad))[:10]: f("FAIL", "focus-obscured", "a11y-obscured", f"control “{x}”", "keyboard focus lands on it but it is entirely hidden behind other content (WCAG 2.4.11)")
                for x in sorted(set(partial))[:5]: f("NOTE", "focus-partly-obscured", "a11y-obscured", f"control “{x}”", "focused control more than half hidden (WCAG 2.4.12, AAA)")
                state("obscured", "fail" if bad else "pass", f"{stops} focus stops checked forwards and backwards")
            guarded("obscured", obscured)
            def screen_reader():
                snap = pg.locator("body").aria_snapshot()
                (out / "screen-reader.yaml").write_text(snap)
                for line in snap.split("\n"):
                    t = line.strip()
                    m = re.match(r"- (button|link|textbox|combobox|checkbox|img|image)(?:\s+\"([^\"]*)\")?\s*(?:\[.*\])?:?\s*$", t)
                    if not m: continue
                    role, name = m.group(1), (m.group(2) or "").strip()
                    if not name: f("FAIL" if role in ("button", "link") else "WARN", f"sr-unnamed-{role}", "a11y-sr", "screen reader", f"a screen reader announces only “{role}”: no name (WCAG 4.1.2 / 1.1.1)", t)
                    elif name.lower() in ("image", "icon", "picture", "graphic", "photo", "button", "link", "click here", "read more", "more", "here"):
                        f("NOTE", "sr-generic-name", "a11y-sr", "screen reader", f"a screen reader announces “{role} {name}”: the name tells the user nothing", t)
                state("screen-reader", *family_state({"a11y-sr"}, "accessibility tree saved as screen-reader.yaml"))
            guarded("screen-reader", screen_reader)
            def interactive():
                if not interact: state("interactive", NA, "skipped on request (--no-interact)"); return
                names_ = pg.evaluate(CANDIDATES); clicked = skipped = 0
                for i, name in enumerate(names_):
                    if DESTRUCTIVE.search(name or ""): skipped += 1; continue
                    p2 = ctx.new_page(); e2 = []; p2.on("pageerror", lambda e: e2.append(str(e))); p2.on("dialog", lambda d: d.dismiss())
                    try:
                        p2.goto(url, wait_until="load", timeout=15000); p2.wait_for_timeout(400); p2.evaluate(CANDIDATES)
                        before = p2.evaluate(SIG); p2.click(f"[data-critic-i='{i}']", timeout=1500); p2.wait_for_timeout(500); clicked += 1
                        if p2.evaluate(SIG) == before and not e2: f("WARN", "dead-control", "ux", f"control “{name}”", "clicking it changes nothing visible (no feedback, no state)")
                        for x in e2: f("FAIL", "click-error", "ux", f"click “{name}”", x[:160])
                    except Exception: pass
                    finally: p2.close()
                hov = pg.evaluate("() => [...document.querySelectorAll('button, [role=button], a[href]')].filter(e => e.getBoundingClientRect().width > 0).slice(0, 10).map((e, i) => { e.setAttribute('data-critic-h', i); const s = getComputedStyle(e); return [i, (e.textContent||'').trim().slice(0,30), [s.backgroundColor, s.color, s.textDecorationLine, s.boxShadow, s.borderColor].join('|')]; })")
                nohover = []
                for i, name, rest in hov:
                    try: pg.hover(f"[data-critic-h='{i}']", timeout=1000); pg.wait_for_timeout(200)
                    except Exception: continue
                    now = pg.evaluate(f"() => {{ const s = getComputedStyle(document.querySelector('[data-critic-h=\"{i}\"]')); return [s.backgroundColor, s.color, s.textDecorationLine, s.boxShadow, s.borderColor].join('|'); }}")
                    if now == rest: nohover.append(name)
                if nohover: f("NOTE", "no-hover", "ux", "hover", f"{len(nohover)} control(s) look the same on hover: " + ", ".join(nohover[:5]))
                cls = pg.evaluate("() => window.__cls || 0"); stats["layout_shift"] = round(cls, 3)
                if cls > 0.1: f("WARN", "layout-shift", "ux", "layout shift", f"cumulative layout shift {cls:.2f} (over 0.1)")
                st, _ = family_state({"ux"}); state("interactive", st, f"{clicked} clicked, {skipped} skipped as destructive, {len(hov)} hovered")
            guarded("interactive", interactive)
            def responsive():
                worst = {}
                for w in (320, 390):  # 320 CSS px is the WCAG 1.4.10 reflow width (1280 px at 400% zoom)
                    pg.set_viewport_size({"width": w, "height": 844}); pg.wait_for_timeout(250)
                    if w == 390: pg.screenshot(path=str(out / "phone.png"), full_page=True)
                    worst[w] = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                for w, over in worst.items():
                    if over > 2: f("FAIL", "sideways", "responsive", f"{w} px", f"page scrolls sideways by {over}px at {w} px wide (WCAG 1.4.10)")
                state("responsive", "fail" if any(v > 2 for v in worst.values()) else "pass", ", ".join(f"overflow {v}px at {w}" for w, v in worst.items()))
            guarded("responsive", responsive)
            def speed():
                runs = []
                for _ in range(3):  # median of three loads, so one slow load doesn't decide it
                    p3 = ctx.new_page(); p3.add_init_script(PERF_INIT)
                    try: p3.goto(url, wait_until="load", timeout=20000); p3.wait_for_timeout(600); runs.append(p3.evaluate(PERF_READ))
                    finally: p3.close()
                med = lambda k: sorted(r[k] for r in runs)[len(runs) // 2]
                kb, req, lcp, blk = med("bytes") / 1024, med("requests"), med("lcp"), med("long")
                stats.update(page_kb=round(kb), requests=req, lcp_ms=round(lcp), blocking_ms=round(blk))
                if kb > budget_kb: f("WARN", "budget-bytes", "perf-rt", "page", f"page weight {kb:.0f} KB is over the {budget_kb} KB budget")
                if req > 60: f("NOTE", "budget-requests", "perf-rt", "page", f"{req} requests to load the page")
                if lcp > 2500: f("WARN", "budget-lcp", "perf-rt", "page", f"largest content appears after {lcp:.0f} ms (target under 2,500 ms, on this machine)")
                if blk > 200: f("WARN", "budget-blocking", "perf-rt", "page", f"{blk:.0f} ms of main-thread blocking while loading (target under 200 ms)")
                state("speed", *family_state({"perf-rt"}, f"median of 3 loads: {kb:.0f} KB, {req} requests, LCP {lcp:.0f} ms, blocking {blk:.0f} ms (local machine, not a phone on 4G)"))
            guarded("speed", speed)
            def visual():
                if not baseline: state("visual", NA, "no --baseline save|compare"); return
                bdir = root / ".critic" / "baseline"
                if baseline == "save":
                    bdir.mkdir(parents=True, exist_ok=True)
                    for n_ in ("desktop.png", "phone.png"):
                        if (out / n_).exists(): (bdir / n_).write_bytes((out / n_).read_bytes())
                    state("visual", "pass", "baseline saved"); return
                try: from PIL import Image, ImageChops
                except ImportError: state("visual", "unavailable", "Pillow not installed"); return
                notes = []
                for n_ in ("desktop.png", "phone.png"):
                    a_, b_ = bdir / n_, out / n_
                    if not a_.exists() or not b_.exists(): notes.append(f"{n_}: no baseline"); continue
                    A, B = Image.open(a_).convert("RGB"), Image.open(b_).convert("RGB")
                    if A.size != B.size: f("WARN", "visual-size", "visual", n_, f"page size changed from {A.size[0]}×{A.size[1]} to {B.size[0]}×{B.size[1]}"); notes.append(f"{n_}: size changed"); continue
                    diff = ImageChops.difference(A, B).convert("L").point(lambda v: 255 if v > 32 else 0)
                    pct = 100 * sum(1 for v in diff.getdata() if v) / (A.size[0] * A.size[1])
                    if pct > 0.5: diff.save(out / f"diff-{n_}"); f("WARN", "visual-change", "visual", n_, f"{pct:.1f}% of the page looks different from the baseline (see diff-{n_})")
                    notes.append(f"{n_}: {pct:.2f}% changed")
                state("visual", *family_state({"visual"}, "; ".join(notes)))
            guarded("visual", visual)
            if CHECKS.get("screenshots", {}).get("state") != "blocked":
                shots_ok = all((out / s).exists() and (out / s).stat().st_size > 2000 for s in ("desktop.png", "phone.png"))
                state("screenshots", "pass" if shots_ok else "fail", "desktop.png, phone.png")
            for e in errs[:10]: f("FAIL", "console-error", "runtime", "console", e[:200])
            state("console", "fail" if errs else "pass", f"{len(errs)} error(s)"); stats["console_errors"] = len(errs)
            if would_send:
                stats["requests_blocked"] = len(would_send)
                f("NOTE", "would-send", "runtime", "network", f"{len(would_send)} request(s) blocked by the scan's safety guard (the app would have sent them): " + "; ".join(sorted(set(would_send))[:4]))
            b.close()
    finally:
        if srv: srv.shutdown()
    return stats

def esc_cell(s): return str(s).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("src"); ap.add_argument("--root"); ap.add_argument("--page"); ap.add_argument("--out"); ap.add_argument("--axe")
    ap.add_argument("--exclude", action="append", default=[]); ap.add_argument("--no-interact", action="store_true"); ap.add_argument("--allow-live", action="store_true")
    ap.add_argument("--online", action="store_true"); ap.add_argument("--mutate", nargs="+", default=[]); ap.add_argument("--test-cmd"); ap.add_argument("--project-checks", action="store_true"); ap.add_argument("--no-project-rules", action="store_true")
    ap.add_argument("--only", help="a file listing the exact paths (relative to --root) to scan; the background check uses it")
    ap.add_argument("--baseline", choices=("save", "compare")); ap.add_argument("--budget-kb", type=int, default=1500)
    a = ap.parse_args(argv)
    global NO_PROJECT_RULES, SCAN_ROOT, ONLY; NO_PROJECT_RULES = a.no_project_rules
    SCAN_ROOT = pathlib.Path(a.root or os.environ.get("CRITIC_ROOT") or os.getcwd()).resolve()
    refuse_linked_state(SCAN_ROOT)
    if a.only:
        try: ONLY = {x.strip() for x in pathlib.Path(a.only).read_text(encoding="utf-8").splitlines() if x.strip() and not x.strip().startswith(("/", ".."))}
        except OSError as e: print(f"critic_scan: can't read --only list: {e}", file=sys.stderr); return 2
    log_run(SCAN_ROOT, "script", "critic_scan.py " + " ".join(argv))
    src = pathlib.Path(a.src).resolve()
    if not src.exists(): print(f"critic_scan: {a.src} does not exist", file=sys.stderr); return 2
    root = pathlib.Path(a.root or os.environ.get("CRITIC_ROOT") or os.getcwd()).resolve()
    out = pathlib.Path(a.out).resolve() if a.out else root / ".critic" / "scan"
    led = root / ".critic" / "ledger.json"
    if led.exists():
        try: FP.extend((json.loads(led.read_text()) or {}).get("false_positives", []))
        except Exception: f("WARN", "ledger-unreadable", "setup", str(led), "ledger unreadable; no false positives suppressed")
    t = time.time(); nfiles = static(src, root, a.exclude)
    try: scan_deps.scan(root if src.is_dir() else src.parent, f, online=a.online, state=state)
    except Exception as e: state("deps", "blocked", f"{type(e).__name__}: {str(e)[:100]}")
    try: ci_evidence(root, out)
    except Exception as e: state("ci", "blocked", f"{type(e).__name__}: {str(e)[:100]}")
    if a.project_checks:
        try: project_checks(root)
        except Exception as e: state("project-checks", "blocked", f"{type(e).__name__}: {str(e)[:100]}")
    stats = {}
    if a.page:
        try: stats = runtime(a.page, src, root, out, a.axe, not a.no_interact, a.allow_live, a.baseline, a.budget_kb)
        except Exception as e: state("runtime", "blocked", f"{type(e).__name__}: {str(e)[:120]}")
    else:
        for k in RUNTIME_CHECKS: state(k, NA, "no --page given")
    if a.mutate:
        try: scan_mutation.run(root, a.mutate, f, state, a.test_cmd, allow_rules=a.project_checks)
        except Exception as e: state("mutation", "blocked", f"{type(e).__name__}: {str(e)[:100]}")
    # fail closed: every check this run asked for must have reported; silence never counts as a pass
    expected = ["static", "structure", "deps", "ci"] + (list(RUNTIME_CHECKS) if a.page else []) + (["mutation"] if a.mutate else [])
    for k in expected:
        if k not in CHECKS: state(k, "blocked", "this check never reported (treated as not run)")
    order = {"FAIL": 0, "WARN": 1, "NOTE": 2}; R.sort(key=lambda x: (order[x["sev"]], x["area"], x["where"]))
    for i, x in enumerate(R, 1): x["id"] = f"S{i:03d}"
    out.mkdir(parents=True, exist_ok=True)
    degraded = [k for k, v in CHECKS.items() if v["state"] in ("blocked", "unavailable") and k in expected]  # n/a is never degraded
    (out / "report.json").write_text(json.dumps({"src": str(src), "root": str(root), "files": nfiles, "stats": stats, "checks": CHECKS, "degraded": degraded, "findings": R, "suppressed": SUPPRESSED}, indent=1))
    from critic_findings import to_sarif
    (out / "scan.sarif").write_text(json.dumps(to_sarif([{"category": x["rule"], "impact": {"FAIL": "High", "WARN": "Medium", "NOTE": "Low"}[x["sev"]], "file": x["where"].split(":")[0] if ":" in x["where"] else x["where"],
        "line": int(x["where"].rsplit(":", 1)[1]) if re.search(r":\d+$", x["where"]) else 1, "title": x["what"], "id": x["id"], "verified": "executed" if x["level"] == "runtime" else "traced"} for x in R], tool="critic-scan"), indent=1))
    c = {s: sum(1 for x in R if x["sev"] == s) for s in order}
    md = [f"# Curmudgeon scripted checks: {src.name}", f"{nfiles} files · {c['FAIL']} FAIL · {c['WARN']} WARN · {c['NOTE']} NOTE · {len(SUPPRESSED)} suppressed · {time.time() - t:.1f} s", ""] + \
         ([f"**DEGRADED:** these checks could not run: {', '.join(degraded)}. Anything they cover is unverified.", ""] if degraded else []) + [
          "## Checks", "| Check | State | Note |", "| --- | --- | --- |"] + [f"| {k} | {v['state']} | {esc_cell(v['note'])} |" for k, v in CHECKS.items()] + \
         ["", "## Stats"] + [f"- {k}: {v}" for k, v in stats.items()] + ["", "## Findings", "| ID | Sev | Rule | Level | Where | What | Evidence |", "| --- | --- | --- | --- | --- | --- | --- |"] + \
         [f"| {x['id']} | {x['sev']} | {x['rule']} | {x['level']} | {esc_cell(x['where'])} | {esc_cell(x['what'])} | {esc_cell(x['evidence'][:100])} |" for x in R]
    if SUPPRESSED: md += ["", "## Suppressed (known false positives from the ledger)"] + [f"- `{x['rule']}` at {x['where']}: {x['what']} — {x['why']}" for x in SUPPRESSED]
    (out / "report.md").write_text("\n".join(md) + "\n"); print("\n".join(md[:2])); print("report:", out / "report.md")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
