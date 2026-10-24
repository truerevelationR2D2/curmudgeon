"""The tests-of-the-tests lens (SC-48): checks Python test files with Python's own parser for tests that can't fail,
can't run, or hide failures. Our own rules and code; the ideas come from pytest and unittest behaviour, PyNose
(Apache-2.0) and the test-smell literature. TSDetect (GPL-3.0) was read for ideas only, nothing taken.

Which files: test_*.py, *_test.py, conftest.py, and any .py file under a folder named test or tests.
What a test is: a function named test* at module level, or a method named test* in a class.

  test-no-assert         WARN  a test with no assert, no assertion call, no pytest.raises/warns/fail and no raise: it passes
                               whatever the code does. A call to a helper whose name says it checks (assert*, check*,
                               verify*, expect*, ensure*, validate*, must*, should*) counts, so helper-based tests aren't flagged;
                               a function that returns a value is a helper (or a decorator factory named test), not a test.
  test-const-assert      FAIL  an assert that is always true: a non-empty tuple (`assert (x == 1, "msg")`), a non-empty
                               string or number, True; or assertTrue/assertIsNotNone of a constant.
  test-duplicate-name    FAIL  two tests with the same name in one module or class: the later one replaces the earlier,
                               which never runs.
  test-swallowed-error   WARN  a test that catches Exception, BaseException, AssertionError or everything and then does
                               nothing (pass, continue, ...): a failure inside it can't fail the test.
  test-skip-no-reason    NOTE  a skip with no reason (pytest.mark.skip(), unittest.skip with none, pytest.skip()).
  test-sleep             NOTE  time.sleep in a test (pedantic: slow and timing-dependent).
  test-unseeded-random   NOTE  random or the clock read in a test with no seed or freeze in the file (pedantic)."""
import ast, pathlib, re

CHECKER = re.compile(r"^(assert|check|verify|expect|ensure|validate|must|should)", re.I)
PEDANTIC = {"test-sleep", "test-unseeded-random"}

def is_test_file(rel):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    if p.suffix != ".py": return False
    return p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "conftest.py" or any(x in ("test", "tests") for x in p.parts[:-1])

def _name(node):
    parts = []
    while isinstance(node, ast.Attribute): parts.append(node.attr); node = node.value
    if isinstance(node, ast.Name): parts.append(node.id)
    elif isinstance(node, ast.Call): return _name(node.func) + "()"
    return ".".join(reversed(parts))

def _always_true(node):
    if isinstance(node, ast.Tuple): return bool(node.elts)
    if isinstance(node, ast.Constant): return bool(node.value)
    if isinstance(node, (ast.List, ast.Set, ast.Dict)): return bool(getattr(node, "elts", None) or getattr(node, "keys", None))
    return False

def _checks(fn):
    """True when the test body can fail: an assert, an assertion-like call, a raise, or pytest.raises/warns/fail."""
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assert, ast.Raise)): return True
        if isinstance(n, ast.Call):
            last = _name(n.func).split(".")[-1]
            if CHECKER.match(last) or last in ("raises", "warns", "fail", "deprecated_call", "fail_if", "failIf", "failUnless"): return True
        if isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if isinstance(it.context_expr, ast.Call) and _name(it.context_expr.func).split(".")[-1] in ("raises", "warns", "assertRaises", "assertWarns", "assertRaisesRegex", "assertLogs"): return True
    return False

def _skip_without_reason(dec):
    if isinstance(dec, ast.Call):
        n = _name(dec.func)
        if n.endswith("mark.skip") or n in ("unittest.skip", "skip"):
            return not dec.args and not any(k.arg == "reason" for k in dec.keywords)
        return False
    return _name(dec).endswith("mark.skip")  # @pytest.mark.skip with no call: no reason

def scan(rel, text, emit):
    """Raises SyntaxError when the file doesn't parse; the caller then skips this lens for the file."""
    if not is_test_file(rel): return 0
    tree = ast.parse(text)
    lines = text.split("\n"); n = 0
    seeded = bool(re.search(r"\brandom\.seed\(|\bseed\s*=|freeze_time|freezegun|time_machine|monkeypatch\.setattr\([^)]*(time|datetime|random)", text))
    def hit(sev, rid, node, msg):
        nonlocal n; n += 1
        ln = getattr(node, "lineno", 1)
        emit(sev, rid, "tests", f"{rel}:{ln}", msg, lines[ln - 1] if 0 < ln <= len(lines) else "")

    def scope(body, where):
        seen = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                if node.name in seen:
                    hit("FAIL", "test-duplicate-name", node, f"test {node.name} is defined twice in {where}: this one replaces the one at line {seen[node.name]}, which never runs")
                seen[node.name] = node.lineno
                check_test(node)
            elif isinstance(node, ast.ClassDef): scope(node.body, f"class {node.name}")

    def check_test(fn):
        if any(_skip_without_reason(d) for d in fn.decorator_list):
            hit("NOTE", "test-skip-no-reason", fn, f"{fn.name} is skipped with no reason: say why, and when it can run again")
        returns_value = any(isinstance(x, ast.Return) and x.value is not None for x in ast.walk(fn))  # a helper or decorator factory named test*, not a test
        if not _checks(fn) and not returns_value and not any(_name(d).split(".")[-1] in ("skip", "skipif", "xfail") or (isinstance(d, ast.Call) and _name(d.func).split(".")[-1] in ("skip", "skipif", "xfail")) for d in fn.decorator_list):
            hit("WARN", "test-no-assert", fn, f"{fn.name} checks nothing (no assert, no assertion call, no pytest.raises): it passes whatever the code does")
        for node in ast.walk(fn):
            if isinstance(node, ast.Assert) and _always_true(node.test):
                what = "a non-empty tuple, so the message became part of the condition" if isinstance(node.test, ast.Tuple) else "a constant"
                hit("FAIL", "test-const-assert", node, f"this assert is always true ({what}): it can never fail")
            elif isinstance(node, ast.Call):
                last = _name(node.func).split(".")[-1]
                if last in ("assertTrue", "assertIsNotNone", "assert_") and node.args and _always_true(node.args[0]) and not isinstance(node.args[0], ast.Tuple) or \
                   last == "assertTrue" and node.args and isinstance(node.args[0], ast.Tuple) and node.args[0].elts:
                    hit("FAIL", "test-const-assert", node, f"{last} of a constant is always true: it can never fail")
                elif _name(node.func) in ("pytest.skip",) and not node.args and not node.keywords:
                    hit("NOTE", "test-skip-no-reason", node, "pytest.skip() with no reason: say why")
                elif _name(node.func) in ("time.sleep", "sleep"):
                    hit("NOTE", "test-sleep", node, "sleep in a test: slow, and it fails or passes by timing; wait for the condition instead")
                elif not seeded and (_name(node.func).startswith("random.") or _name(node.func) in ("datetime.now", "datetime.datetime.now", "datetime.utcnow", "time.time", "date.today")):
                    hit("NOTE", "test-unseeded-random", node, f"{_name(node.func)} in a test with no seed or frozen clock in the file: the result can change between runs")
            elif isinstance(node, ast.Try):
                for h in node.handlers:
                    broad = h.type is None or _name(h.type) in ("Exception", "BaseException", "AssertionError") or \
                            isinstance(h.type, ast.Tuple) and any(_name(e) in ("Exception", "BaseException", "AssertionError") for e in h.type.elts)
                    idle = all(isinstance(s, (ast.Pass, ast.Continue)) or isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) for s in h.body)
                    if broad and idle:
                        hit("WARN", "test-swallowed-error", h, f"{fn.name} catches {'everything' if h.type is None else _name(h.type) or 'a broad error'} and does nothing: a failure inside it can't fail the test")

    scope(tree.body, "this module")
    return n
