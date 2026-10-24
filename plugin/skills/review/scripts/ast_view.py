#!/usr/bin/env python3
"""Print the parsed syntax tree of a Python file, or of the statements on a line range (SC-63), so a reviewer or
verifier can trace what the code really does (which name a call binds to, what an `if` actually tests, where a
string ends) instead of guessing from the text. Read-only; nothing is run or imported.

usage:
  ast_view.py FILE [LINE | START-END] [--depth N]

Only Python has a parser here (Python's own `ast`). For any other language it says "no parser" and exits 3, rather
than pretend. A file that doesn't parse prints the syntax error and exits 2."""
import ast, pathlib, sys

def fmt(node, depth, indent=0, limit=6):
    pad = "  " * indent
    name = type(node).__name__
    where = f" L{node.lineno}" + (f"-{node.end_lineno}" if getattr(node, "end_lineno", None) not in (None, node.lineno) else "") if hasattr(node, "lineno") else ""
    bits = []
    for f in ("id", "name", "attr", "arg", "module", "asname"):
        v = getattr(node, f, None)
        if isinstance(v, str): bits.append(f"{f}={v}")
    if isinstance(node, ast.Constant): bits.append(f"value={node.value!r}"[:80])
    if isinstance(node, (ast.BinOp, ast.BoolOp, ast.UnaryOp, ast.AugAssign)): bits.append(f"op={type(node.op).__name__}")
    if isinstance(node, ast.Compare): bits.append("ops=" + ",".join(type(o).__name__ for o in node.ops))
    out = [f"{pad}{name}{where}" + (f" ({', '.join(bits)})" if bits else "")]
    if depth <= 0:
        kids = list(ast.iter_child_nodes(node))
        if kids: out.append(f"{pad}  … {len(kids)} more node(s); raise --depth to see them")
        return out
    for field, value in ast.iter_fields(node):
        items = value if isinstance(value, list) else [value]
        nodes = [x for x in items if isinstance(x, ast.AST) and not isinstance(x, (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop))]
        if not nodes: continue
        out.append(f"{pad}  .{field}:")
        for x in nodes: out += fmt(x, depth - 1, indent + 2)
    return out

def main(a):
    if not a or a[0] in ("-h", "--help"): print(__doc__); return 0
    depth = 8
    if "--depth" in a:
        i = a.index("--depth")
        try: depth = int(a[i + 1]); a = a[:i] + a[i + 2:]
        except (IndexError, ValueError): print("ast_view: --depth needs a number", file=sys.stderr); return 2
    p = pathlib.Path(a[0])
    if p.suffix not in (".py", ".pyi", ".pyw"): print(f"ast_view: no parser for {p.suffix or 'this file'} (only Python has one here); read the code itself"); return 3
    try: src = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e: print(f"ast_view: can't read {p}: {e}", file=sys.stderr); return 2
    try: tree = ast.parse(src, filename=str(p))
    except SyntaxError as e: print(f"ast_view: {p}:{e.lineno}: syntax error: {e.msg}"); return 2
    lo = hi = None
    if len(a) > 1:
        try:
            lo, _, hi = a[1].partition("-"); lo = int(lo); hi = int(hi) if hi else lo
        except ValueError: print("ast_view: the range is LINE or START-END", file=sys.stderr); return 2
    picked = []
    def visit(n):
        for c in ast.iter_child_nodes(n):
            if isinstance(c, ast.stmt) and lo is not None:
                if c.lineno <= hi and (c.end_lineno or c.lineno) >= lo:
                    inner = [x for x in ast.iter_child_nodes(c) if isinstance(x, ast.stmt) and x.lineno <= hi and (x.end_lineno or x.lineno) >= lo]
                    if inner and not (c.lineno >= lo and (c.end_lineno or c.lineno) <= hi): visit(c)  # descend to the statements on the range
                    else: picked.append(c)
            elif lo is None and isinstance(c, ast.stmt): picked.append(c)
    visit(tree)
    if not picked: print(f"ast_view: no statement on line{'s' if hi != lo else ''} {a[1] if len(a) > 1 else ''} of {p}"); return 1
    for n in picked: print("\n".join(fmt(n, depth)))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
