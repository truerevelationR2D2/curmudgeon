```json
[
  {
    "file": "app.js",
    "line": 11,
    "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
    "title": "Note title is inserted into innerHTML without escaping (stored XSS and broken markup)",
    "failing_case": "Set a note's title to `<img src=x onerror=alert(1)>`. It is saved to localStorage, and the script runs on every renderList call. A title like `</span><b>` also breaks the list markup."
  },
  {
    "file": "app.js",
    "line": 46,
    "quote": "    document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
    "title": "Server-supplied shared note titles are inserted as raw HTML (XSS). Out-of-order responses also append stale or duplicate results.",
    "failing_case": "/api/shared returns a title of `<img src=x onerror=...>`, and the script executes. Separately, type 'ab' quickly. The response for 'a' arrives after the render for 'ab', so its shared items are appended to the 'ab' list. If two responses arrive, both sets are appended and duplicate entries show."
  },
  {
    "file": "store.js",
    "line": 16,
    "quote": "    currentNote.title = document.getElementById('title').value;",
    "title": "The debounced save dereferences currentNote when it may be null, and it writes to whichever note is current when the timer fires, not the note that was edited",
    "failing_case": "(a) Type in the body, then delete the open note within 500ms. currentNote is null, so the timer throws a TypeError. (b) On first load with no notes, typing in #title makes scheduleSave throw, because currentNote is null. (c) Edit note A, then click note B within 500ms. The edit to A is never persisted, because the timer reads the editor fields that now hold B's content."
  },
  {
    "file": "store.js",
    "line": 2,
    "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
    "title": "Unguarded JSON.parse of localStorage. Corrupt or non-array data throws at startup, and no script after it runs.",
    "failing_case": "localStorage.notes = 'oops', or '{}' or '5'. JSON.parse throws or returns a non-array, then `notes.filter` or `notes.find` fails and the app never initialises."
  },
  {
    "file": "store.js",
    "line": 7,
    "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
    "title": "Note id is Date.now(), so two notes created in the same millisecond get the same id",
    "failing_case": "Two createNote calls in the same millisecond, such as a double-click or a scripted call, produce notes with the same id. openNote, removeNote and deleteNote then act on both, or on the wrong one."
  },
  {
    "file": "store.js",
    "line": 20,
    "quote": "    persist();",
    "title": "After the debounced save, the list is not re-rendered, so edited titles and the #rank values go stale",
    "failing_case": "Rename a note from 'Untitled' to 'Groceries'. The sidebar keeps showing 'Untitled' and the old rank until some other action calls renderList."
  }
]
```