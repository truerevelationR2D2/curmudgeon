DEGRADED: axe-core could not run, so the scripted WCAG pass did not run. The other scripted checks reported 0 FAIL.

**BLOCK** · Counts: 0 Critical, 4 High, 2 Medium, 0 Low

Three blind reviewers raised 21 raw findings, which merged into 6. Blind verifiers confirmed all 6 (the check that they could be reproduced or traced), and the variant hunt found no variants. No source file was changed. The review's own state is in `.critic/`, and the full teardown is `.critic/last-review.md`.

| # | Where | Impact | Votes | Defect |
|---|---|---|---|---|
| C1 `F-10b39db9` | `store.js:9` | High | 3/3 | Corrupt stored data loads as an empty list with no message, and the next save overwrites it. The comment saying `app.js` tells the user is false. |
| C2 `F-75a04bfd` | `store.js:15` (also `app.js:3`) | High | 3/3 | Every save writes a copy read once at page load, so a second tab erases the first tab's recipes. |
| C3 `F-7df54c58` | `app.js:35` | High | 3/3 | Delete ignores the save result and says "Deleted" even when storage failed. |
| C4 `F-1091813d` | `app.js:21` | High | 2/3 | `parseInt` on a number input turns `1e2` into 1 minute. |
| C5 `F-42d4f3d7` | `app.js:37` | Medium | 3/3 | Deleting rebuilds the list, so focus drops to the body (WCAG 2.4.3, level A). |
| C6 `F-e9e546c7` | `store.js:7` (also `app.js:33`) | Medium | 3/3 | Load only checks `name`. Records with no `id` can never be deleted, and a string `minutes` makes the total read "020x5 minutes". |

Nit, not counted: `importRecipes` and `getJson` are never called, and `importRecipes` builds records with no validation.

Fixes worth the most per hour:
1. Validate and normalise records on load, back up unreadable data, and tell the user (C1, C6).
2. Re-read the stored list before each write (C2).
3. Check the save result on delete (C3).
4. Read `valueAsNumber` for minutes (C4).
5. Restore focus after a delete (C5).

Not checked:
- Only reviewer A drove the page in Chromium. B and C could not run it, so their lines are traced, and C4 is traced only.
- Real storage-quota behaviour (A forced `setItem` to throw instead), other browsers, 200% zoom as its own run, and contrast beyond hand-computed ratios.
- The outside reviewer was not offered, because no user was present to ask.

`.critic/` is new in the working folder and holds the run's state and reports. Delete the folder if you don't want to keep it.

Next steps:
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only one.