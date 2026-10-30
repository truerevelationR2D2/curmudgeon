## Code review

Reviewed `git diff main...HEAD` ("Add the app"). I posted nothing and changed no files.

**1 issue found (bug), validated:**

1. **`tests/test_helpers_ok.py:85`: the decorator factory `def test(name):` errors on every pytest run.**
   - It sits at module level, and pytest's default `python_functions = test` prefix matches a function named exactly `test`.
   - pytest then collects it and treats `name` as a fixture. No fixture called `name` exists, so every run reports `fixture 'name' not found`.
   - The repo has no `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `conftest.py` or `__test__ = False` that would stop this.
   - The file is named `test_*.py`, so a plain `pytest` run picks it up. Its docstring says nothing in it should be flagged, but this error makes the run fail.
   - Fix: rename it (for example `make_decorator`) or set `test.__test__ = False`.
   - Both bug agents found this independently. The validation agent confirmed it by reading the code and pytest's default rules. Nobody ran pytest, because Bash was denied to those agents.

**CLAUDE.md compliance:** no violations. The repo has no CLAUDE.md files, and both compliance agents returned empty lists.

**Not flagged:** the unreachable `assert` after `pytest.skip` in `test_inline_skip_with_reason` and the skipped `test_discount_bounds` in `tests/test_cart.py`. Both are test-quality smells, not definite defects.

**PR description:** "Adds this application's code" doesn't match the content. The diff adds a small `src/cart.py` and two test files, which look like planted-defect fixtures for a test-quality lens. That is outside the high-signal bug filter, so I didn't count it as an issue.