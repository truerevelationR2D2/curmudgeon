```json
[
  {
    "file": "app.js",
    "line": 108,
    "quote": "  selectNote(note.id);",
    "title": "A new note is created and selected but stays hidden when a search filter is active. renderList filters by the search text, and a new note's title 'Untitled' may not match it. The editor then shows a note that is missing from the list.",
    "failing_case": "Type 'groceries' in the search box, then click 'New note'. The note 'Untitled' is created and opened in the editor, but the list shows 'No notes match \"groceries\".' There is no list entry for the open note, and its Delete button is unreachable until the search is cleared."
  },
  {
    "file": "store.js",
    "line": 259,
    "quote": "    if (e && e.name === 'QuotaExceededError') return 'Not saved: browser storage is full. Delete old notes to free space.';",
    "title": "Quota detection only matches the standard error name. Firefox throws NS_ERROR_DOM_QUOTA_REACHED, and older browsers use code 22 or 1014. Those cases get the generic 'browser refused to store notes' message instead of the 'delete old notes' advice.",
    "failing_case": "In Firefox, fill localStorage and save a note. e.name is 'NS_ERROR_DOM_QUOTA_REACHED', so the user sees 'Not saved: the browser refused to store notes (NS_ERROR_DOM_QUOTA_REACHED).' with no hint to free space."
  }
]
```