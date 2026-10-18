---
name: gate
description: Turns Curmudgeon's stop checks on or off for this project. Runs only when the user types /curmudgeon:gate on, /curmudgeon:gate async or /curmudgeon:gate off.
disable-model-invocation: true
argument-hint: "on | async | off"
---

Requested: $ARGUMENTS

- **on:** run `critic_ledger.py gate on` from the project root (the review skill's `scripts/` folder). Don't create the file by hand: the plugin's guard blocks direct edits to `.critic/`. In Claude Code, the Stop hook then keeps the session from finishing while a reviewed file (or, before any review, any code file) is newer than `.critic/last-review.md`, or while the last *full* run left a Critical or High finding open. It blocks at most three times for the same work, then hands the decision back for that work for good; a new edit starts again.
- **async:** run `critic_ledger.py gate async`. Nothing blocks. When Claude stops, a free static scan of the files changed since the last review runs in the background. Only a new blocking problem wakes Claude, each problem once, at most three times per batch of edits.
- **off:** run `critic_ledger.py gate off`.
- Anything else: ask "on, async or off?"

Say in two lines what changed, and that it works only where plugin hooks run (Claude Code), not in a chat window. If the user overrides a block to finish anyway, record it with `critic_ledger.py override "<what>" "<who>" "<why>"`. An override can't be recorded as by the author.
