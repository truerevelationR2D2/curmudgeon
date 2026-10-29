```json
[
  {
    "file": "store.js",
    "line": 65,
    "summary": "The recovery backup is overwritten by any later load problem, so the first unreadable data is lost.",
    "failure_scenario": "Load 1 finds corrupt data and copies it to 'notes-backup'. The user adds a note and the app overwrites 'notes'. If a later load hits another problem, such as a skipped note, backupRaw() replaces the first backup. The original unreadable data is gone, even though the message says it was kept."
  },
  {
    "file": "store.js",
    "line": 50,
    "summary": "Data with a version newer than SCHEMA_VERSION is read as v1 and written back as v1, and the stored version is never checked.",
    "failure_scenario": "A newer build, or another tab on a newer version, saves {version:2, notes:[{..., tags:[...]}]}. This build normalizes each note to only id, title, body and updated. The next edit saves it back as version 1, with no backup and no warning, so the extra fields and version are permanently lost."
  },
  {
    "file": "app.js",
    "line": 119,
    "summary": "flushSave() drops the pending edit if the save fails, and nothing retries it.",
    "failure_scenario": "Storage is full. flushSave sets pending=null, updates the note in memory and commit() shows the error. If the user does not act, no later flush retries the write. The data is only in memory and is lost on reload. The error status can also be overwritten by the next 'Saving…' or 'Saved'."
  },
  {
    "file": "app.js",
    "line": 187,
    "summary": "createNote() and deleteNote() ignore the commit result and carry on, and selectNote/renderList can leave a stale status.",
    "failure_scenario": "Storage is blocked or full. createNote pushes the note, commit() shows the error, and the UI behaves as if the note exists. The same happens for delete. After a reload the note is gone or comes back, and the status text may have been replaced by an unrelated message."
  },
  {
    "file": "app.js",
    "line": 260,
    "summary": "The load-problem message is set once and replaced by the first 'Saved' or 'Saving…' status.",
    "failure_scenario": "Load skips 3 corrupt notes and shows the problem plus the backup key name. The user clicks New note, commit() sets 'Saved', and the warning disappears. Meanwhile the file is rewritten without those notes, so the user is never reminded that data was dropped."
  },
  {
    "file": "app.js",
    "line": 142,
    "summary": "Local search filters on the title only, not the body, even though the box is labelled 'Search notes'.",
    "failure_scenario": "A note titled 'Untitled' has the body 'dentist 3pm'. Searching 'dentist' shows 'No notes match', and the same query is sent to the server's shared search."
  },
  {
    "file": "app.js",
    "line": 217,
    "summary": "Every search query is sent to /api/shared without consent or disclosure. The request is also not cancelled when the shared box is hidden after a fetch fails.",
    "failure_scenario": "A user types private text into the 'Search notes' box meant for local notes. After 250ms the text goes to the server. There is no UI warning that the search leaves the browser."
  },
  {
    "file": "app.js",
    "line": 173,
    "summary": "selectNote() calls flushSave(), which already runs renderList(), and then calls renderList() again. createNote also commits before selectNote's flush.",
    "failure_scenario": "Every note switch rebuilds the list DOM twice, and a new note triggers two localStorage writes. This is wasted work, and the list flickers when it is large."
  },
  {
    "file": "store.js",
    "line": 20,
    "summary": "A saved note with no usable id gets a fresh random id on every load, and numeric ids from version 0 are not rewritten until the next edit.",
    "failure_scenario": "Old records without ids keep changing id across reloads until a save happens. The id also changes in memory only, so it is unstable if anything else keys on it."
  },
  {
    "file": "app.js",
    "line": 61,
    "summary": "A migrated or normalized notes list is never persisted at load, so storage stays in the old format until the user edits something.",
    "failure_scenario": "A user with version-0 data opens the app and only reads. Storage keeps the bare array with numeric ids, and the in-memory ids are generated fresh. A second tab or the next load can regenerate different ids for the same records."
  }
]
```