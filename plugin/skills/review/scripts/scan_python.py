"""Python checks for Curmudgeon scan, read with Python's own parser (the standard-library `ast` module) instead of text
patterns, so strings, comments and look-alike names no longer cause false alarms. The rule ids match the old
text-pattern rules, which stay as the fallback for files that don't parse (for example Python 2 code).
Idea from Bandit (Apache-2.0); our own code, no rule text copied."""
import ast

SAFE_YAML_LOADERS = {f"yaml{m}.{c}" for m in ("", ".loader", ".cyaml") for c in ("SafeLoader", "CSafeLoader", "BaseLoader", "CBaseLoader")}
VERIFY_NAMES = {"verify", "ssl_verify", "verify_ssl", "tls_verify", "verify_tls", "verify_certs", "verify_cert"}  # not skip_verify, reverify ...

def _name(node):
    """Dotted name of a call target: os.system, subprocess.run, eval ..."""
    parts = []
    while isinstance(node, ast.Attribute): parts.append(node.attr); node = node.value
    if isinstance(node, ast.Name): parts.append(node.id)
    return ".".join(reversed(parts))

def _kw(call, name):
    return next((k.value for k in call.keywords if k.arg == name), None)

def _const(node, value):
    return isinstance(node, ast.Constant) and node.value is value

def scan(rel, text, emit):
    """Raises SyntaxError when the file doesn't parse; the caller then falls back to the text rules."""
    tree = ast.parse(text)
    lines = text.split("\n")
    # import aliases: `import subprocess as sp` makes sp.run mean subprocess.run; `from subprocess import run as r`
    # makes r mean subprocess.run; `from yaml import SafeLoader` makes SafeLoader mean yaml.SafeLoader
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: alias[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names: alias[a.asname or a.name] = f"{node.module}.{a.name}"
    def full(node):
        n = _name(node)
        if not n: return n
        head, _, rest = n.partition(".")
        return alias.get(head, head) + ("." + rest if rest else "")
    def hit(sev, rid, area, node, msg):
        ln = getattr(node, "lineno", 0)
        emit(sev, rid, area, f"{rel}:{ln}", msg, lines[ln - 1] if 0 < ln <= len(lines) else "")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            n = full(node.func)
            if n in ("eval", "exec"):
                hit("FAIL", "py-eval", "safety", node, "eval/exec runs arbitrary code")
            elif n.startswith("subprocess.") and _const(_kw(node, "shell"), True):
                cmd = node.args[0] if node.args else _kw(node, "args")
                if not isinstance(cmd, ast.Constant):  # a fixed string is safe; built text is where injection lives
                    hit("WARN", "py-shell-true", "safety", node, "subprocess with shell=True on a built command: any untrusted text in it becomes a shell command")
            elif n in ("os.system", "os.popen"):
                hit("WARN", "py-os-system", "safety", node, "os.system/os.popen run through the shell: prefer subprocess with a list")
            elif n.split(".")[0] in ("pickle", "cPickle", "dill", "shelve") and n.split(".")[-1] in ("load", "loads", "open"):
                hit("WARN", "py-pickle", "safety", node, "unpickling runs code from the data: never load untrusted pickles")
            elif n == "yaml.load":
                ld = _kw(node, "Loader") or (node.args[1] if len(node.args) > 1 else None)
                if not (ld is not None and full(ld) in SAFE_YAML_LOADERS):  # only PyYAML's own safe loaders
                    hit("WARN", "py-yaml-load", "safety", node, "yaml.load without SafeLoader can build arbitrary objects (use yaml.safe_load)")
            elif n == "tempfile.mktemp":
                hit("WARN", "py-mktemp", "safety", node, "tempfile.mktemp is racy: use mkstemp or NamedTemporaryFile")
            if _const(_kw(node, "verify"), False):
                hit("WARN", "py-verify-false", "safety", node, "TLS certificate checks switched off")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _const(node.value, False):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any((isinstance(t, ast.Attribute) and t.attr == "verify") or (isinstance(t, ast.Name) and t.id.lower() in VERIFY_NAMES) for t in targets):
                hit("WARN", "py-verify-false", "safety", node, "TLS certificate checks switched off")
        elif isinstance(node, ast.ExceptHandler):
            broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"))
            if broad and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                hit("WARN", "py-bare-except-pass", "errors", node, "every error is swallowed here (the user is never told)")
        elif isinstance(node, ast.Assert):
            src = ast.unparse(node.test).lower()
            if any(w in src for w in ("auth", "permission", "user", "admin", "valid")):
                hit("NOTE", "py-assert-guard", "errors", node, "assert used as a guard: it disappears under python -O")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("/tmp/") and len(node.value) > 5 and "\n" not in node.value:  # a path, not the bare prefix
            hit("NOTE", "py-hardcoded-tmp", "safety", node, "hard-coded /tmp path: other users can create it first")
