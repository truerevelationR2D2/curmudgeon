# Contributing to Curmudgeon

Thanks for helping the grump get sharper. A few house rules keep it honest:

1. **Precision before recall.** A change that finds more bugs but raises more false alarms is a regression. Run the eval kit before and after your change, and include both scores in the pull request.
2. **Counting stays in code.** Votes, merges, suppression and severity changes happen in the Python scripts, never in a prompt. Prompts decide what *might* be wrong. Scripts decide what *counts*.
3. **Every bug fix gets a test.** Add it to the last part, `plugin/tests/cases_3.py` (start a `cases_4.py` when a part nears 200 KB: the plugin directory holds any file over 256 KiB for a reviewer); the tests need no framework, just `python3 plugin/tests/run_tests.py`, which runs every part (`CRITIC_TEST_ONLY=<text>` runs only the tests whose name contains it). Name each test after the finding or issue it fixes.
4. **New checks start as rule files.** If a check is a line pattern, add it to `plugin/skills/review/rules/` as JSON (see the README there) with a test, rather than editing the scanner.
4a. **New lenses are measured before they ship.** A lens is a scanner module plus a rubric row, with a planted-defect fixture, a clean twin and decoys in `eval/`, and a `lensN.json` answer key that `python3 eval/lens.py` checks (every planted defect found, and no wrong row, decoy row or clean-twin row). To read another tool's SARIF under a lens, add the tool's name and lens to `TOOL_LENS` in `critic_scan.py`, with a test.
5. **No copied rules or code.** Ideas from other tools are welcome. Their code and rule text aren't, unless their licence allows it and you credit them in the file header. Name the tool that inspired each new check.
6. **Nothing leaves the machine by default.** Any new network call must be opt-in, listed under "What it runs, reads and sends" in the README, and send the least data possible.
7. **Never weaken the safety rules.** These rules stay:
   - learned memories only add notes and never hide a finding;
   - verifiers may lower an impact but never raise it;
   - secrets are always redacted in reports, and restore copies stay private and git-ignored;
   - the mutation runner always restores the original files.

## Before you open a pull request

```
python3 plugin/tests/run_tests.py
python3 eval/golden.py
python3 eval/replay.py
python3 eval/score.py --selftest
for k in eval/lens*.json; do python3 eval/lens.py "$k"; done
claude plugin validate --strict .
claude plugin validate --strict plugin
claude plugin validate --strict --profile directory plugin
```

All of them must pass. None of them needs a model, an account or a network connection beyond installing Claude Code, and CI (`.github/workflows/ci.yml`) runs them on Python 3.9 to 3.14 for every push and pull request (the script tests also run on Windows and macOS).
- `golden.py` checks that the scripted checks still find exactly what they found on each eval fixture. If your change is meant to alter that, rerun it with `CRITIC_UPDATE_GOLDEN=1`, and explain the diff in your pull request.
- `replay.py` runs recorded review runs (the models' reviews, groups and verdicts) through the counting scripts and checks the outcome is unchanged. Use `CRITIC_UPDATE_REPLAY=1` only for a change meant to alter it.
- `score.py --selftest` checks that the accept/kill gate can still fail.
- `lens.py` measures each scripted lens against its planted defects, clean twin and decoys (the script tests run it too).
- The last validation checks part of what Anthropic's plugin directory checks.

## Reporting a wrong finding

Open an issue with the finding as `.critic/findings.jsonl` shows it (redact anything private), the code it pointed at, and why it's wrong. False alarms are the most useful bug reports Curmudgeon gets.

Comments in the code cite design rulings as `§2` or `§5.NN`; [plugin/RULINGS.md](plugin/RULINGS.md) says what each one decided.
