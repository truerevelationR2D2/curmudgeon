## Code review

I reviewed `git diff main...HEAD` (one commit, 3 new files). I did not run the tests, and I changed no files. No `CLAUDE.md` exists in the repo, so I checked nothing for compliance. This is a read-through only: I did not launch the parallel sub-agent and validation steps, and I did not verify this issue by running pytest.

**1 issue found**

1. **`tests/test_helpers_ok.py:86-89`: the decorator-factory helper `def test(name)` will be collected as a test and error.**
   - pytest's default `python_functions = test` is a prefix match, so a module-level function named exactly `test` is collected.
   - The repo has no pytest config that would change this.
   - pytest then treats `name` as a fixture request, finds no such fixture, and reports `fixture 'name' not found` as an error at setup.
   - The file's docstring says it holds correct tests that only look suspicious, so a fixture error is a real defect in it. Any `pytest` run over `tests/` will report it.
   - The fix is to rename the helper so it doesn't start with `test`, for example `deco_factory`. Alternatively, set `__test__ = False` on it or move it out of the collected path.

**Noted but not flagged**
- The weak assertions in `tests/test_cart.py` are the planted defects the fixture exists to hold. They are intended, so I did not report them as bugs.
- The tests import `src.cart` and there are no `__init__.py` files or pytest config. Plain `pytest` may fail to import `src`, while `python -m pytest` from the root should work. I didn't flag it because it depends on how the tests are invoked.