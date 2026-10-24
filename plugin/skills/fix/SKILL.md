---
name: fix
description: Acts on Curmudgeon's last review. Runs only when the user types /curmudgeon:fix patch [id], iterate [part], approve or rollback.
argument-hint: "patch <finding id or issue> | iterate <component> | approve | rollback"
disable-model-invocation: true
---

Do what the first word of `$ARGUMENTS` names; the words after it are the target (the finding id or issue for patch, the component for iterate). Arguments: $ARGUMENTS. Work using the review skill's `scripts/` folder (`${CLAUDE_PLUGIN_ROOT}/skills/review/scripts`) from the project root. With no word, or an unknown one, list the four below and stop.

## patch [id or issue]: fix only that
1. Find the finding ids in `.critic/ledger.md` or the last review. If the issue isn't there, write it up first as one finding (Evidence, Failing case, Impact). Then run `critic_ledger.py fresh <ids>`: if it says STALE, the code changed since the review, so review that file again before fixing; never fix against an old report.
2. Save a restore point for the files you'll touch (`critic_ledger.py restore save <files>`), then make the smallest complete fix.
3. Prove it: replay that finding's failing case, re-run the scan on the file, and run the project's tests. Record the three claims (`critic_ledger.py claim <id> targeted|no-new-defect|behaviour-unchanged "<evidence>"`), then `critic_ledger.py fixed <id> "<how>"`. Report each check as pass, fail, unavailable, blocked or n/a.
4. Mark it in the ledger and show a diff summary. Change nothing else, even if you notice other problems; list those as new findings instead.

## iterate [component]: go deeper on one part
1. Run `critic_ledger.py round`. If it says past round 3 for this run, or prints any `ESCALATE to the owner` line (a finding fixed twice and open again, one open for 3 rounds, or open Critical+High not falling), stop and hand the open items to the owner with those lines. If it prints a `WHACK-A-MOLE` line (one control in one file keeps springing new holes), stop fixing that control and write the design finding in `${CLAUDE_PLUGIN_ROOT}/skills/review/references/escalation.md`: the pattern, the real requirement, and up to five solutions ranked best to worst, for the owner to choose. (A new `/curmudgeon:review` run starts again at round 1.)
2. Re-run the review skill on that component only: `critic_map.py --files <its files>`, the scripted checks, fresh blind reviewers (who don't see the earlier review), the merge and verification, limited to it. If the user rejected the previous fix, say what approach it took and take a different one. In round 3, only verify: no new findings without an executed case.
3. Refactor, re-check and update the ledger as in the review skill's steps 7 and 8, but stamp with `critic_ledger.py stamp --add <component files>` so the rest of the project stays watched. Leave everything outside the component untouched.

## approve: keep the last refactor
1. Confirm the re-check in the last reply passed. If it didn't, say which check failed and stop.
2. If the project is a git repository, offer to commit the refactored files with a message listing the fixed finding ids, and commit only if the user says yes. Otherwise say the files on disk are final.
3. Check each fixed id has its three claims (`critic_ledger.py claim <id> targeted|no-new-defect|behaviour-unchanged "<evidence>"`), then mark it with `critic_ledger.py fixed <id> "<how verified>"`. Keep the restore copies in `.critic/restore/` until the user deletes them.
4. Reply in two lines: what was kept, and any deferred items still waiting on the owner.

## rollback: undo the last refactor
1. Run `critic_ledger.py restore apply`. It puts back the files saved by the last `restore save`, recorded in `.critic/ledger.json`, so it works in a new session too.
2. If no restore point is recorded, say so and stop. Never reset or check out the whole repository.
3. `restore apply` reopens the finding ids the restore point recorded (saved with `restore save --ids`). If it recorded none, list the findings whose files were restored and reopen them with `critic_ledger.py status <id> open "rolled back"`. If it reports files it could not restore (restore points saved by an older version with keys redacted), tell the user to restore those from version control.
4. Reply in two lines: what was restored, and the ids that are open again. Ask whether to try a different approach with `/curmudgeon:fix iterate`.
