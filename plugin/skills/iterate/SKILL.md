---
name: iterate
description: Runs a second Curmudgeon teardown and refactor on one named component. Runs only when the user types /curmudgeon:iterate [component].
disable-model-invocation: true
argument-hint: "<component, file or screen>"
---

Go deeper on one part: $ARGUMENTS
1. Run `critic_ledger.py round`. If it says past round 3 for this run, stop and hand the open items to the owner. (A new `/curmudgeon:review` run starts again at round 1.)
2. Re-run the review skill on that component only: `critic_map.py --files <its files>`, the scripted pass, fresh blind reviewers (who don't see the earlier review), the merge and verification, limited to it. If the user rejected the previous fix, say what approach it took and take a different one. In round 3, only verify: no new findings without an executed case.
3. Refactor, re-check and update the ledger as in the review skill's steps 7 and 8, but stamp with `critic_ledger.py stamp --add <component files>` so the rest of the project stays watched. Leave everything outside the component untouched.
