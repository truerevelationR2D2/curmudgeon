"""The operations lens (SC-54), our own rules and code. Ideas from pint (Apache-2.0, Prometheus rule linting), the
Kubernetes production checklists and the OWASP logging cheat sheet; no rule text copied.

  ops-log-secret        WARN  a log or print call that passes a variable named like a password, secret, token, API key
                              or authorization header: it ends up in log files and log services. Not a name that only
                              describes one (auth_method, token_path, secret_backend), and not a value passed through
                              mask(), redact(), obfuscate(), sanitize() or scrub().
  ops-alert-no-runbook  WARN  a Prometheus alerting rule with no runbook_url (or runbook) annotation: whoever is paged
                              has nothing to follow.
  ops-runbook-missing   WARN  a runbook link that is a relative path to a file that doesn't exist (links are never
                              fetched; only local paths are checked).
  ops-debug-on          WARN  DEBUG = True in a settings file that isn't for development or tests.
  ops-k8s-no-probes     NOTE  (pedantic) a Kubernetes container with no readiness or liveness probe.
  ops-k8s-no-limits     NOTE  (pedantic) a Kubernetes container with no resource limits.
  ops-not-checked       NOTE  an alert or Kubernetes file the strict YAML reader refused."""
import ast, os, pathlib, re
import yaml_lite

SECRETISH = re.compile(r"(?i)^(?:.*_)?(pass(?:word|wd)?|secret|token|api_?key|apikey|auth(?:orization)?|credentials?|private_?key|session_?id|cookie)(?:_.*)?$")
NOT_SECRET = re.compile(r"(?i)_(counts?|types?|len|length|policy|expiry|expires(_at)?|url|uri|endpoint|field|name|required|valid|ttl|lifetime|format|kind|prefix|index|idx|num|number|hint|label|min|max|strength|reset_at|hash(ed)?|digest|fingerprint|method|mode|backend|provider|scheme|file|path|dir|header_name|source|status|state|error)$|^(is|has|num|n|max|min)_")
def secretish(name): return bool(SECRETISH.match(name)) and not NOT_SECRET.search(name)
MASKER = re.compile(r"(?i)^_?(mask|redact|obfuscate|sanitize|sanitise|scrub|censor|hide|anonymi[sz]e)")  # mask(password) logs no secret
LOG_CALLS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log", "print"}
PEDANTIC = {"ops-k8s-no-probes", "ops-k8s-no-limits"}

def _names(node):
    """Variable and attribute names whose VALUE an expression passes on: not string contents, and not names only
    tested or measured (bool(x), len(x), x is None, x ? a : b, not x) or masked by a slice (token[-4:])."""
    out = []
    def skip(n):
        called = n.func.id if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) else (n.func.attr if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) else "")
        return called in ("bool", "len", "type", "isinstance", "hash", "callable") or MASKER.search(called or "-") is not None or \
               isinstance(n, (ast.Compare, ast.BoolOp)) or (isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)) or \
               (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice))
    stack = [node]; seen = []
    while stack:
        n = stack.pop()
        if skip(n): continue
        if isinstance(n, ast.IfExp): stack += [n.body, n.orelse]; continue
        seen.append(n); stack += list(ast.iter_child_nodes(n))
    for n in seen:
        if isinstance(n, ast.Name): out.append(n.id)
        elif isinstance(n, ast.Attribute): out.append(n.attr)
        elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str): out.append(n.slice.value)
    return out

def scan_python(rel, text, emit):
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError): return
    lines = text.split("\n")
    name = pathlib.PurePosixPath(rel).name.lower()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
            if fname in LOG_CALLS and (fname == "print" or re.search(r"(?i)log", owner) or owner in ("logging",)):
                hits = [n for a in list(node.args) + [k.value for k in node.keywords] for n in _names(a) if secretish(n)]
                if hits:
                    emit("WARN", "ops-log-secret", "operations", f"{rel}:{node.lineno}", f"{hits[0]} is written to the log: secrets in logs end up in log files and log services (log that it exists, or its last 4 characters)", lines[node.lineno - 1])
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEBUG" for t in node.targets) and isinstance(node.value, ast.Constant) and node.value.value is True:
            p = rel.replace("\\", "/").lower()
            if re.search(r"settings|config", p) and not re.search(r"dev|local|test|example|sample", p):
                emit("WARN", "ops-debug-on", "operations", f"{rel}:{node.lineno}", "DEBUG = True in a settings file that isn't for development or tests: error pages leak code, settings and data", lines[node.lineno - 1])

JS_LOG = re.compile(r"\b(?:console|logger|log)\.(?:log|info|debug|warn|error|trace)\s*\((.*)\)")

def scan_js(rel, text, emit):
    for i, l in enumerate(text.split("\n"), 1):
        m = JS_LOG.search(l)
        if not m: continue
        args = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", m.group(1))  # strings are text, not variables
        args = re.sub(r"[A-Za-z_$][\w$.]*\s*\?[^:]*:", " ", args)  # x ? a : b tests x, it doesn't log it
        args = re.sub(r"(?i)\b_?(?:mask|redact|obfuscate|saniti[sz]e|scrub|censor|anonymi[sz]e)\w*\s*\([^()]*\)", " ", args)  # mask(token) logs no secret
        args = re.sub(r"!!?\s*[A-Za-z_$][\w$.]*|Boolean\([^)]*\)|[A-Za-z_$][\w$]*\.length\b|[A-Za-z_$][\w$]*\.slice\(\s*-\d+\s*\)", " ", args)
        args = re.sub(r"`(?:\\.|[^`\\])*`", lambda t: " ".join(re.findall(r"\$\{([^}]*)\}", t.group(0))), args)
        for ident in re.findall(r"[A-Za-z_$][\w$]*", args):
            snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", ident).lower()
            if secretish(snake):
                emit("WARN", "ops-log-secret", "operations", f"{rel}:{i}", f"{ident} is written to the log: secrets in logs end up in log files and log services", l); break

def scan_yaml(rel, text, emit, root):
    if not re.search(r"(?m)^\s*-?\s*alert\s*:|^kind\s*:", text): return
    try: doc = yaml_lite.loads(text)
    except yaml_lite.Refused as e:
        emit("NOTE", "ops-not-checked", "operations", f"{rel}:{e.line}", f"not checked: the strict YAML reader refused it ({e.why})", ""); return
    raw = text.split("\n")
    if isinstance(doc, dict) and isinstance(doc.get("groups"), list):
        for g in doc["groups"]:
            for r in (g.get("rules") if isinstance(g, dict) and isinstance(g.get("rules"), list) else []):
                if not isinstance(r, dict) or "alert" not in r: continue
                ann = r.get("annotations") if isinstance(r.get("annotations"), dict) else {}
                link = ann.get("runbook_url") or ann.get("runbook")
                ln = r.key_lines.get("alert", r.line)
                if not link:
                    emit("WARN", "ops-alert-no-runbook", "operations", f"{rel}:{ln}", f"alert {r['alert']} has no runbook_url annotation: whoever is paged has nothing to follow", raw[ln - 1])
                elif not re.match(r"(?i)^[a-z][a-z0-9+.-]*://", str(link)):
                    target = str(link).split("#")[0]
                    base = pathlib.Path(root)
                    cands = [base / target.lstrip("/"), base / pathlib.PurePosixPath(rel).parent / target]
                    if target and not any(c.exists() for c in cands):
                        lnk = getattr(link, "line", ln)
                        emit("WARN", "ops-runbook-missing", "operations", f"{rel}:{lnk}", f"the runbook {target} doesn't exist in the repository", raw[lnk - 1])
    if isinstance(doc, dict) and str(doc.get("kind")) in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"):
        spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
        tpl = spec.get("template") if isinstance(spec.get("template"), dict) else spec
        if str(doc.get("kind")) == "CronJob": tpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
        pod = tpl.get("spec") if isinstance(tpl, dict) and isinstance(tpl.get("spec"), dict) else (spec if str(doc.get("kind")) == "Pod" else {})
        for c in pod.get("containers") or [] if isinstance(pod, dict) else []:
            if not isinstance(c, dict): continue
            ln = getattr(c.get("name"), "line", c.line)
            if str(doc.get("kind")) not in ("Job", "CronJob") and not ("readinessProbe" in c or "livenessProbe" in c):
                emit("NOTE", "ops-k8s-no-probes", "operations", f"{rel}:{ln}", f"container {c.get('name', '?')} has no readiness or liveness probe: traffic can reach it before it is ready, and a hung one is never restarted", raw[ln - 1])
            res = c.get("resources") if isinstance(c.get("resources"), dict) else {}
            if not isinstance(res.get("limits"), dict):
                emit("NOTE", "ops-k8s-no-limits", "operations", f"{rel}:{ln}", f"container {c.get('name', '?')} has no resource limits: one leak can starve the node", raw[ln - 1])

def scan(rel, text, emit, root):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    if p.suffix == ".py": scan_python(rel, text, emit)
    elif p.suffix in (".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"): scan_js(rel, text, emit)
    elif p.suffix in (".yml", ".yaml") and not (len(p.parts) >= 3 and p.parts[-3:-1] == (".github", "workflows")): scan_yaml(rel, text, emit, root)
