## Curmudgeon review (lite tier, review only)

**VERDICT: 3 findings. Critical 0, High 1, Medium 1, Low 1.** Counts are from `critic_merge.py`. The scripted scan had 0 FAIL, and I changed no source files.

Reviewed: `app.js`, `index.html`, `store.js` and `styles.css` (the only tracked files). The `.` payload had no uncommitted change, so I passed those four files explicitly.

**1. High, confirmed (verified by tracing): a second tab silently deletes the first tab's notes** (F-75d5aaea, `store.js:75`)
- **Failing case:**
  - Tab A saves a new note.
  - Tab B, which loaded its list earlier, then edits a note. `saveNotes` writes tab B's whole stale array with `localStorage.setItem`.
  - Tab A's note is gone, and the status line still says "Saved".
- **Why nothing catches it:** there is no `storage` listener, no read-before-write merge, and no backup on save.
- **Fix:** re-read and merge by id before writing, or listen for `storage` events and reload.

**2. Medium, confirmed (verified by tracing): keyboard select or delete drops focus to `<body>`** (F-fb256fc2, `app.js:84`)
- **Failing case:** `renderList()` calls `replaceChildren`, which removes the focused button. Only `createNote` sets focus afterwards.
- **Impact:** keyboard and screen-reader users lose their place (WCAG 2.4.3).
- **Fix:** restore focus to the selected row, the editor, or the next row after the rebuild.

**3. Low (one reviewer, not independently verified; the lite tier verifies only High and above): "Search notes" matches titles only** (F-f6b4e780, `app.js:62`)
- **Failing case:** searching for a word that appears only in a note body returns nothing.
- **Fix:** also test `n.body`, or rename the field to "Search titles".

**Checks that held:**
- Corrupted or old saved data is handled, and the raw copy is kept under `notes-backup`.
- A pending save is flushed on page close.
- Hostile text typed into search is rendered as text.
- A failing network shows a cause and a next step.

**Not reviewed:**
- Only one blind reviewer ran, per the lite tier, so these findings have 1/1 votes.
- The no-network and storage-full paths were traced, not driven.
- Phone width and 200% zoom were traced from the CSS, not screenshotted.
- Screen-reader announcements were not tested.
- Browser checks used `file://`, because localhost timed out in the sandbox.
- The scan ran without `--page` (no page checks in a browser) and with no test command.
- I did not save `.critic/last-review.md` or run `critic_ledger.py stamp`.

The `.critic/` working folder is new in the repo and is untracked. The stated intent was just "task", so there was nothing to check against.