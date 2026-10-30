```json
[
 {
  "file": "app.js",
  "line": 108,
  "quote": "  selectNote(note.id);",
  "title": "A new note is created and selected but stays hidden when a search filter is active. renderList filters by the search text, and a new note's title 'Untitled' may not match it. The editor then shows a note that is missing from the list.",
  "failing_case": "Type 'groceries' in the search box, then click 'New note'. The note 'Untitled' is created and opened in the editor, but the list shows 'No notes match \"groceries\".' There is no list entry for the open note, and its Delete button is unreachable until the search is cleared."
 }
]
```
