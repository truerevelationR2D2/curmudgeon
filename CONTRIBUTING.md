# Contributing to Curmudgeon

Thanks for helping the grump get sharper. A few house rules keep it honest:

1. **Precision before recall.** A change that finds more bugs but raises more false alarms is a regression. Run the eval kit before and after your change, and include both scores in the pull request.
2. **Counting stays in code.** Votes, merges, suppression and severity changes happen in the Python scripts, never in a prompt. Prompts decide what *might* be wrong. Scripts decide what *counts*.
3. **Every bug fix gets a test.** Add it to `plugin/tests/run_tests.py`; the tests need no framework, just `python3 plugin/tests/run_tests.py`. Name each test after the finding or issue it fixes.
4. **New checks start as rule files.** If a check is a line pattern, add it to `plugin/skills/review/rules/` as JSON (see the README there) with a test, rather than editing the scanner.
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
claude plugin validate --strict .
claude plugin validate --strict plugin
claude plugin validate --strict --profile directory plugin
```

All four must pass. The last one checks part of what Anthropic's plugin directory checks.

## Reporting a wrong finding

Open an issue with the finding as `.critic/findings.jsonl` shows it (redact anything private), the code it pointed at, and why it's wrong. False alarms are the most useful bug reports Curmudgeon gets.
