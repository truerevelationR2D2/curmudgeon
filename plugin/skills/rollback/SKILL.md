---
name: rollback
description: Undoes Curmudgeon's last refactor from its restore point. Runs only when the user types /curmudgeon:rollback.
disable-model-invocation: true
---

Undo the last Curmudgeon refactor.
1. Run `critic_ledger.py restore apply` from the project root (the review skill's `scripts/` folder). It puts back the files saved by the last `restore save`, recorded in `.critic/ledger.json`, so it works in a new session too.
2. If no restore point is recorded, say so and stop. Never reset or check out the whole repository.
3. `restore apply` reopens the finding ids the restore point recorded (saved with `restore save --ids`). If it recorded none, list the findings whose files were restored and reopen them with `critic_ledger.py status <id> open "rolled back"`. If it reports files it could not restore (restore points saved by an older version with keys redacted), tell the user to restore those from version control.
4. Reply in two lines: what was restored, and the ids that are open again. Ask whether to try a different approach with `/curmudgeon:iterate`.
