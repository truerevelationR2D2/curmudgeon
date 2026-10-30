```json
[
  {
    "file": "app.js",
    "line": 62,
    "quote": ".filter(n => n.title.toLowerCase().includes(q))",
    "title": "Search matches the stored title, but the list shows 'Untitled' for an empty title. A note displayed as 'Untitled' can't be found by searching 'untitled'.",
    "failing_case": "Create a note and clear its title field, so title is ''. The list shows 'Untitled'. Type 'untitled' in the search box. The note is filtered out, and the message reads 'No notes match \"untitled\".' even though a row labelled 'Untitled' was visible a moment before."
  },
  {
    "file": "app.js",
    "line": 116,
    "quote": "if (!window.confirm(`Delete \"${note.title || 'Untitled'}\"? This cannot be undone.`)) return;",
    "title": "The confirm dialog reads the title from the note, but a pending unsaved edit is only applied later, in flushSave. The prompt can name a title the user has already changed.",
    "failing_case": "Open note 'A' and rename it to 'B'. Within 500 ms, before the save timer fires, click Delete on that note. The dialog asks 'Delete \"A\"?', although the editor and the user's intent say 'B'."
  }
]
```