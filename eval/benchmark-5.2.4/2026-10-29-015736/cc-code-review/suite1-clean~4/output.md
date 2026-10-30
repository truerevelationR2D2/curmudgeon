```json
[
  {
    "file": "app.js",
    "line": 114,
    "summary": "Every save rewrites the whole notes array from this tab's in-memory copy, and there is no `storage` event listener or re-read before writing.",
    "failure_scenario": "Two tabs are open. Tab A creates or edits notes. Tab B, loaded earlier, edits one note. Tab B's save writes its stale array over localStorage and silently erases everything Tab A added. The same happens when a tab resumes after the user edited elsewhere."
  },
  {
    "file": "store.js",
    "line": 50,
    "summary": "`loadNotes` never checks `data.version`, so data written by a newer schema is read as version 1 and then overwritten in the old shape.",
    "failure_scenario": "A newer build saves `{version: 2, notes: [...]}` with extra fields or a different note shape. This build loads it, normalizeNote drops the unknown fields, and the next edit saves it back as version 1. The newer data is lost and no backup is made, because the backup only happens on parse failure or skipped notes."
  },
  {
    "file": "store.js",
    "line": 47,
    "summary": "`backupRaw` overwrites the single `notes-backup` key unconditionally on every problematic load.",
    "failure_scenario": "The first load hits corrupt data and backs it up. The user does not save, or saves an empty state. A later load backs up again, and if the main key has since been replaced by a different but also flawed value, the original corrupt data is overwritten and gone. The 'kept under notes-backup' message then promises data that no longer exists."
  },
  {
    "file": "app.js",
    "line": 187,
    "summary": "`createNote` leaves an active search filter in place, so the new note is selected in the editor but missing from the list.",
    "failure_scenario": "The user types 'foo' in search, then clicks New note. The 'Untitled' note is created and selected but renderList filters it out. The sidebar shows 'No notes match' or no current item, with an editor open on an invisible note. If they retitle it to something that doesn't match 'foo', it disappears from view and they can't find it."
  },
  {
    "file": "app.js",
    "line": 141,
    "summary": "Search matches only the title, not the body, although the field is labelled 'Search notes'.",
    "failure_scenario": "A user searches for a word they wrote in a note body. The local list shows 'No notes match', which looks as if the note is lost. The query is also sent to /api/shared, so the shared results can match differently from local ones."
  },
  {
    "file": "app.js",
    "line": 129,
    "summary": "`flushSave` always reports 'Saved' and re-renders. When `commit` fails, the in-memory edit stays and `pending` is cleared, so nothing retries.",
    "failure_scenario": "The quota is full. The user types, flushSave runs and shows the error. They keep typing, and each later flush re-attempts the full save. If they navigate away or close the tab after a failed save, the edits are lost with only a transient error shown. The error status is also overwritten by 'Saving…' on the next keystroke, so the failure is easy to miss."
  },
  {
    "file": "app.js",
    "line": 223,
    "summary": "The shared-notes fetch has no timeout, and the shared status is not cleared or reset when the query becomes empty.",
    "failure_scenario": "The server hangs. The user sees 'Searching shared notes…' forever, because only a newer query aborts the request. After the box is hidden and shown again for a new query, the old status text can briefly reappear."
  },
  {
    "file": "app.js",
    "line": 197,
    "summary": "`deleteNote` runs `commit()`, which reports 'Saved' even though the delete was not persisted if storage failed. The note also stays gone from the UI.",
    "failure_scenario": "The delete is rendered as done, but if the save throws, the next reload brings the note back. The user is shown an error that is easy to miss and has already seen the note disappear."
  }
]
```