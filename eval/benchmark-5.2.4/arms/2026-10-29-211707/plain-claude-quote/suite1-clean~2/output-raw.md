```json
[
  {
    "file": "app.js",
    "line": 62,
    "quote": ".filter(n => n.title.toLowerCase().includes(q))",
    "title": "Search matches the stored title, but the list shows 'Untitled' for notes with an empty title. Searching for what the user sees finds nothing.",
    "failing_case": "Create a note and clear its title field, so it is stored with title ''. The list shows it as 'Untitled'. Type 'untitled' in the search box. The note is filtered out and the empty-state text reads 'No notes match \"untitled\".' even though a visible 'Untitled' note exists."
  }
]
```