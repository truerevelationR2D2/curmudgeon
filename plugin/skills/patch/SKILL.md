---
name: patch
description: Fixes only the named Curmudgeon finding or issue and leaves everything else untouched. Runs only when the user types /curmudgeon:patch [issue].
disable-model-invocation: true
argument-hint: "<finding id(s) or a short description>"
---

Fix only: $ARGUMENTS
1. Find the finding ids in `.critic/ledger.md` or the last review. If the issue isn't there, write it up first as one finding (Evidence, Failing case, Impact).
2. Save a restore point for the files you'll touch (`critic_ledger.py restore save <files>`), then make the smallest complete fix.
3. Prove it: replay that finding's failing case, re-run the scan on the file, and run the project's tests. Record the three claims (`critic_ledger.py claim <id> targeted|no-new-defect|behaviour-unchanged "<evidence>"`), then `critic_ledger.py fixed <id> "<how>"`. Report each check as pass, fail, unavailable or blocked.
4. Mark it in the ledger and show a diff summary. Change nothing else, even if you notice other problems; list those as new findings instead.
