---
name: approve
description: Keeps Curmudgeon's last refactor. Runs only when the user types /curmudgeon:approve.
disable-model-invocation: true
---

Keep the last Curmudgeon refactor.
1. Confirm the re-check in the last reply passed. If it didn't, say which check failed and stop.
2. If the project is a git repository, offer to commit the refactored files with a message listing the fixed finding ids, and commit only if the user says yes. Otherwise say the files on disk are final.
3. Check each fixed id has its three claims (`critic_ledger.py claim <id> targeted|no-new-defect|behaviour-unchanged "<evidence>"`), then mark it with `critic_ledger.py fixed <id> "<how verified>"`. Keep the restore copies in `.critic/restore/` until the user deletes them.
4. Reply in two lines: what was kept, and any deferred items still waiting on the owner.
