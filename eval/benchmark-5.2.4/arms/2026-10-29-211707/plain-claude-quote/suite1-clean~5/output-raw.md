```json
[
  {
    "file": "app.js",
    "line": 62,
    "quote": ".filter(n => n.title.toLowerCase().includes(q))",
    "title": "The search matches only the raw title, not the displayed name. A note with an empty title is listed as 'Untitled' but can't be found by searching 'untitled'. Searching also never looks at note bodies.",
    "failing_case": "Clear a note's title so it is stored as ''. Type 'untitled' in the search box. The note, which the list shows as 'Untitled', disappears and the message says 'No notes match \"untitled\"'."
  },
  {
    "file": "app.js",
    "line": 108,
    "quote": "selectNote(note.id);",
    "title": "createNote doesn't clear the search filter. A new note is titled 'Untitled' and is selected and focused, but renderList filters it out when the search text doesn't match.",
    "failing_case": "Type 'foo' in the search box, then click New note. The editor opens on the new note, but the sidebar list doesn't show it and says 'No notes match \"foo\"'. The user is editing an invisible note."
  },
  {
    "file": "store.js",
    "line": 78,
    "quote": "if (e && e.name === 'QuotaExceededError') return 'Not saved: browser storage is full. Delete old notes to free space.';",
    "title": "Quota detection only checks the standard exception name. Firefox legacy builds throw NS_ERROR_DOM_QUOTA_REACHED, and some Safari versions throw a different name or code 22/1014. In those cases the user gets the generic 'browser refused' message with no hint to free space.",
    "failing_case": "Fill localStorage in a browser that throws NS_ERROR_DOM_QUOTA_REACHED. saveNotes returns 'Not saved: the browser refused to store notes (NS_ERROR_DOM_QUOTA_REACHED).' instead of the storage-full guidance."
  },
  {
    "file": "store.js",
    "line": 30,
    "quote": "try { localStorage.setItem(BACKUP_KEY, raw); } catch (e) { /* storage is already failing; the load message says so */ }",
    "title": "Each failed load overwrites the single backup slot. Worse, if the backup write fails (e.g. quota), the load message still says the data 'was kept under notes-backup'. The next saveNotes then overwrites STORAGE_KEY and the unreadable data is lost.",
    "failing_case": "Storage is nearly full and 'notes' holds corrupt JSON. The page loads, backupRaw throws and is swallowed, and the user sees 'The unreadable data was kept under notes-backup'. They create a note, saveNotes overwrites 'notes', and the original data is gone with no backup."
  }
]
```