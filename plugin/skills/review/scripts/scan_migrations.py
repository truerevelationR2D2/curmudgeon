"""The release and rollback lens (SC-53), our own rules and code. Ideas from squawk (Apache-2.0/MIT),
strong_migrations (MIT) and django-migration-linter (Apache-2.0); no rule text copied. PostgreSQL semantics.

SQL is read from .sql files and from the SQL strings a migration passes to op.execute (Alembic) or
migrations.RunSQL (Django). Statements are split on semicolons outside quotes, with comments removed.

  mig-index-blocking      WARN  CREATE INDEX without CONCURRENTLY on a table this file didn't create (CREATE TABLE,
                                Alembic op.create_table or Django CreateModel): it blocks writes to the table while it
                                builds.
  mig-not-null-no-default WARN  ADD COLUMN ... NOT NULL with no DEFAULT on an existing table: it fails on a table with
                                rows (and on old PostgreSQL rewrites the table). serial types carry their own default.
  mig-constraint-validate WARN  ADD CONSTRAINT ... FOREIGN KEY or CHECK without NOT VALID on an existing table: it scans
                                the whole table under a lock (add it NOT VALID, then VALIDATE CONSTRAINT separately).
  mig-irreversible        WARN  a migration that can't be rolled back: an Alembic downgrade() that does nothing, or a
                                Django RunPython or RunSQL with no reverse.
  mig-drop-rename         NOTE  (pedantic) DROP or RENAME of a column or table: code still deployed may use the old name."""
import ast, pathlib, re

DOLLAR = re.compile(r"\$[A-Za-z_]*\$")

def _add_clauses(rest):
    """The ADD ... clauses of an ALTER TABLE, split on commas outside parentheses, so numeric(12,2) stays whole."""
    parts, depth, cur = [], 0, []
    q = None
    for c in rest:
        if q:
            if c == q: q = None
            cur.append(c); continue
        if c in "'\"": q = c; cur.append(c); continue
        if c == "(": depth += 1
        elif c == ")": depth = max(0, depth - 1)
        if c == "," and depth == 0: parts.append("".join(cur)); cur = []; continue
        cur.append(c)
    parts.append("".join(cur))
    return [p.strip() for p in parts if re.match(r"(?i)\s*add\b", p)]

def _statements(sql, first_line=1):
    """(line, statement) pairs, comments removed, split on ; outside quotes and dollar quotes."""
    out, buf, line, start, i, n = [], [], first_line, None, 0, len(sql)
    q = None
    while i < n:
        c = sql[i]
        if q is None:
            if sql.startswith("--", i):
                j = sql.find("\n", i); i = n if j < 0 else j; continue
            if sql.startswith("/*", i):
                j = sql.find("*/", i + 2); seg = sql[i:(n if j < 0 else j + 2)]; line += seg.count("\n"); i = n if j < 0 else j + 2; continue
            m = DOLLAR.match(sql, i) if c == "$" else None  # match at i, without copying the rest of the file
            if m:
                q = m.group(0); buf.append(q); i += len(q)
                if start is None: start = line
                continue
            if c in "'\"": q = c
            if c == ";":
                s = "".join(buf).strip()
                if s: out.append((start or line, s))
                buf, start = [], None; i += 1; continue
            if start is None and not c.isspace(): start = line
        else:
            if q.startswith("$") and sql.startswith(q, i):
                buf.append(q); i += len(q); q = None; continue
            if q in "'\"" and c == q: q = None
        if c == "\n": line += 1
        buf.append(c); i += 1
    s = "".join(buf).strip()
    if s: out.append((start or line, s))
    return out

def _flat(s): return re.sub(r"\s+", " ", s).strip()

def check_sql(rel, sql, emit, first_line=1, created=None):
    created = set() if created is None else created
    stmts = _statements(sql, first_line)
    for _, s in stmts:
        m = re.match(r"(?is)create\s+(?:unlogged\s+|temporary\s+|temp\s+)?table\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", s)
        if m: created.add(m.group(1).strip('"').lower().split(".")[-1])
    for ln, s in stmts:
        f = _flat(s)
        m = re.match(r"(?i)create\s+(unique\s+)?index\s+(concurrently\s+)?(?:if\s+not\s+exists\s+)?(?:[\w\"]+\s+)?on\s+(?:only\s+)?([\w.\"]+)", f)
        if m and not m.group(2) and m.group(3).strip('"').lower().split(".")[-1] not in created:
            emit("WARN", "mig-index-blocking", "release", f"{rel}:{ln}", f"CREATE INDEX on {m.group(3)} without CONCURRENTLY blocks writes to it while the index builds (use CREATE INDEX CONCURRENTLY, outside a transaction)", f[:160])
        m = re.match(r"(?i)alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?([\w.\"]+)\s+(.*)", f)
        if not m:
            m2 = re.match(r"(?i)(drop\s+table|alter\s+table\s+\S+\s+rename\s+to)\b", f)
            if m2: emit("NOTE", "mig-drop-rename", "release", f"{rel}:{ln}", "a table is dropped or renamed: code still deployed may use it (expand, migrate, then contract)", f[:160])
            continue
        table = m.group(1).strip('"').lower().split(".")[-1]; rest = m.group(2)
        if table in created: continue
        for col in _add_clauses(rest):
            if re.search(r"(?i)\bnot\s+null\b", col) and not re.search(r"(?i)\bdefault\b|\bgenerated\b", col) and not re.match(r"(?i)add\s+(?:column\s+(?:if\s+not\s+exists\s+)?)?(?!column\b)[\w\"]+\s+(?:small|big)?serial\d?\b", col) and not re.match(r"(?i)add\s+constraint", col):
                emit("WARN", "mig-not-null-no-default", "release", f"{rel}:{ln}", f"a NOT NULL column with no DEFAULT is added to {table}: it fails if the table has rows (add it nullable or with a default, backfill, then set NOT NULL)", f[:160])
        if re.search(r"(?i)add\s+constraint\s+\S+\s+(foreign\s+key|check)\b", rest) and not re.search(r"(?i)\bnot\s+valid\b", rest):
            emit("WARN", "mig-constraint-validate", "release", f"{rel}:{ln}", f"a constraint is added to {table} without NOT VALID: the whole table is checked under a lock (add NOT VALID, then VALIDATE CONSTRAINT separately)", f[:160])
        if re.search(r"(?i)\bdrop\s+column\b|\brename\s+(column\s+)?[\w\"]+\s+to\b|\brename\s+to\b", rest):
            emit("NOTE", "mig-drop-rename", "release", f"{rel}:{ln}", f"a column of {table} is dropped or renamed: code still deployed may use it (expand, migrate, then contract)", f[:160])

def _str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
    if isinstance(node, ast.JoinedStr): return None
    return None

def _does_nothing(fn):
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return all(isinstance(s, ast.Pass) for s in body)

def check_python(rel, text, emit):
    """Alembic and Django migrations: irreversible steps, and the SQL they run."""
    if not re.search(r"\bdef\s+upgrade\b|migrations\.Migration\b", text): return
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError): return
    created = set()
    forward = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("upgrade", "forwards")]
    scope_nodes = [x for f in forward for x in ast.walk(f)] if forward else [x for x in ast.walk(tree) if not (isinstance(x, ast.FunctionDef) and x.name in ("downgrade", "backwards"))]
    for node in scope_nodes:  # tables this migration creates going forward (never downgrade()): an index on them blocks nobody
        if isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", ""))
            if name == "create_table" and node.args and _str(node.args[0]): created.add(_str(node.args[0]).lower())
            if name == "CreateModel":
                model = _str(node.args[0]) if node.args else next((_str(k.value) for k in node.keywords if k.arg == "name"), None)
                if model:  # Django names the table <app>_<model>; the app is the folder above migrations/
                    parts = pathlib.PurePosixPath(rel.replace("\\", "/")).parts
                    app = parts[parts.index("migrations") - 1] if "migrations" in parts and parts.index("migrations") > 0 else ""
                    created.add(model.lower())
                    if app: created.add(f"{app}_{model}".lower())
                    for k in node.keywords:
                        if k.arg == "options" and isinstance(k.value, ast.Dict):
                            for kk, vv in zip(k.value.keys, k.value.values):
                                if _str(kk) == "db_table" and _str(vv): created.add(_str(vv).lower())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade" and _does_nothing(node) and re.search(r"\bdef\s+upgrade\b", text):
            emit("WARN", "mig-irreversible", "release", f"{rel}:{node.lineno}", "downgrade() does nothing: this migration can't be rolled back (write the reverse, or raise to say it is one-way on purpose)", text.split("\n")[node.lineno - 1])
        if isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", ""))
            if name == "RunPython" and len(node.args) < 2 and not any(k.arg == "reverse_code" for k in node.keywords):
                emit("WARN", "mig-irreversible", "release", f"{rel}:{node.lineno}", "RunPython with no reverse_code: this migration can't be rolled back (pass a reverse, or migrations.RunPython.noop when nothing needs undoing)", text.split("\n")[node.lineno - 1])
            if name == "RunSQL" and len(node.args) < 2 and not any(k.arg == "reverse_sql" for k in node.keywords):
                emit("WARN", "mig-irreversible", "release", f"{rel}:{node.lineno}", "RunSQL with no reverse_sql: this migration can't be rolled back", text.split("\n")[node.lineno - 1])
            if name in ("execute", "RunSQL") and node.args:
                sql = _str(node.args[0])
                if sql: check_sql(rel, sql, emit, node.args[0].lineno, created)

def wants(rel):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    return p.suffix == ".sql" or (p.suffix == ".py" and any(x in ("migrations", "versions", "alembic") for x in p.parts[:-1]))

def scan(rel, text, emit):
    if rel.endswith(".sql"): check_sql(rel, text, emit)
    else: check_python(rel, text, emit)
