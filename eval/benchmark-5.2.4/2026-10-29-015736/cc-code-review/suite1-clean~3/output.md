```json
[
  {
    "file": "store.js",
    "line": 73,
    "summary": "Every save writes this tab's whole in-memory notes array over the stored value, and nothing listens for `storage` events or re-reads before writing.",
    "failure_scenario": "The app is open in tabs A and B. In A, the user creates and edits note X. B was loaded earlier and doesn't have X. B then edits or deletes any note, and its `saveNotes` replaces the stored list with its own stale one, so X is gone. The same happens in reverse for deletions and edits."
  },
  {
    "file": "store.js",
    "line": 50,
    "summary": "The loader accepts any saved shape that has a notes array and never checks `data.version`. A newer schema (version 2 or later) is read as version 1 and later overwritten with `version: 1`.",
    "failure_scenario": "A newer build writes {version:2, notes:[...]} with extra fields. An older cached copy of the app loads it, `normalizeNote` drops the unknown fields, and the next save rewrites the stored data as version 1. The newer data is lost and no backup was taken, because `backupRaw` only runs on parse or format failure."
  },
  {
    "file": "store.js",
    "line": 41,
    "summary": "The version-0 migration (bare array, numeric ids) and the duplicate-id rewrite change the data but never back up the original raw string. The first save then overwrites it.",
    "failure_scenario": "A user has v0 data such as [{id:1,title:'a'},{id:'1',title:'b'}]. The loader changes the ids and returns problem:null. On the next edit the original is replaced with the normalized data. If the migration got something wrong, such as ids that were once used elsewhere, there is no way back."
  },
  {
    "file": "store.js",
    "line": 30,
    "summary": "`backupRaw` always writes the single key `notes-backup`, so a second corrupt load replaces the earlier backup. Its error is swallowed and the message still says the data was kept.",
    "failure_scenario": "Corrupt data is backed up on one load. The user then saves new notes, and later a different corruption or format problem occurs. The first backup is overwritten, and the data it held is lost. If the backup `setItem` throws a quota error, the user is still told 'was kept under notes-backup', which is false."
  },
  {
    "file": "app.js",
    "line": 188,
    "summary": "`createNote` pushes the new note and selects it without clearing the search box. When the filter doesn't match 'Untitled', the new note is selected but missing from the list.",
    "failure_scenario": "The user searches 'meeting' and presses New note. The editor opens an 'Untitled' note, but the list shows 'No notes match "meeting"' and no highlighted entry. The user can't tell the note exists and may think the click did nothing or create duplicates."
  },
  {
    "file": "app.js",
    "line": 199,
    "summary": "`deleteNote` removes the note from memory before the save is known to have worked. If `commit()` fails, the note stays deleted in the UI but is still in storage.",
    "failure_scenario": "Storage is full or blocked when the user confirms a delete. The note vanishes from the list, and an error status shows briefly. The next `renderList` or `flushSave` run replaces that status with 'Saved' or hides it. After a reload the 'deleted' note reappears, despite the 'cannot be undone' prompt."
  },
  {
    "file": "app.js",
    "line": 119,
    "summary": "When a save fails, `flushSave` clears `pending` and keeps the edit only in memory. Nothing retries, and the error status is replaced by the next 'Saving…' or 'Saved'.",
    "failure_scenario": "The user types, the 500 ms save hits QuotaExceededError, and the error shows. They then type one more character, which sets 'Saving…' and, if space was freed, writes everything. If it still fails, the earlier error is overwritten by 'Saving…' before it fails again. In the meantime, closing the tab loses everything unsaved without a beforeunload warning."
  },
  {
    "file": "app.js",
    "line": 142,
    "summary": "Local search filters on `n.title` only. A note's body text is never searched, and the 'Search notes' label doesn't say so.",
    "failure_scenario": "The user searches for a word that appears only in a note body and gets 'No notes match', though the note exists."
  },
  {
    "file": "app.js",
    "line": 212,
    "summary": "When the shared-search query becomes empty, the box is hidden but `sharedStatus` is not cleared. Stale 'Searching shared notes…' text remains.",
    "failure_scenario": "The user types a query, then clears it before the response arrives. The box is hidden, and the in-flight fetch is aborted. The next query shows the box again with the old 'Searching…' or old results for a moment, until the debounce fires. A screen reader's role=status region can announce the stale text."
  },
  {
    "file": "app.js",
    "line": 223,
    "summary": "The shared-notes search fetches the relative URL '/api/shared', sending each typed query to the page's origin by default. The app has no consent step, and the error text is the same for file:// and for a missing endpoint.",
    "failure_scenario": "Opened from file:// or a static host, every search shows 'Shared notes could not be loaded (...)'. On a hosted origin, search terms go to that server whenever the user types in the search box, with no opt-in."
  }
]
```