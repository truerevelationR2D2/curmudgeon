```json
[
  {
    "file": "app.js",
    "line": 11,
    "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
    "title": "Note title is inserted into innerHTML without escaping (stored XSS / broken markup)",
    "failing_case": "Click New note, set the title to `<img src=x onerror=alert(1)>` and wait for the save. The next renderList runs the handler, and it runs again on every reload. A title like `<b>` also breaks the list markup."
  },
  {
    "file": "app.js",
    "line": 46,
    "quote": "    document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
    "title": "Server-supplied shared titles are injected as unescaped HTML. Late responses from earlier searches are also appended with no staleness check.",
    "failing_case": "The server returns a shared note titled `<img src=x onerror=...>`, and the script runs. Separately, type 'a' then 'ab' quickly. If the 'a' response arrives after renderList('ab'), stale or duplicate shared items are appended to the 'ab' list."
  },
  {
    "file": "store.js",
    "line": 67,
    "quote": "    currentNote.title = document.getElementById('title').value;",
    "title": "The debounced save dereferences currentNote when the timer fires. currentNote may then be null, or a different note from the one that was edited.",
    "failing_case": "(a) Type in the body, then delete the open note within 500ms, or type in the editor after deleting the current note. currentNote is null and this throws a TypeError, so the edit is lost. (b) Edit note A, then click note B within 500ms. A's edited text is written into B, so B is overwritten with A's content and A keeps its old text."
  },
  {
    "file": "app.js",
    "line": 27,
    "quote": "  renderList();",
    "title": "Deleting a note re-renders with no filter, so the active search is dropped from the list. The editor also keeps showing the deleted note.",
    "failing_case": "Type 'foo' in the search box, then delete a matching note. The list shows all notes again while the search box still says 'foo'. The deleted note's title and body stay in the editor, and typing there triggers the null crash above."
  },
  {
    "file": "store.js",
    "line": 2,
    "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
    "title": "Corrupt or non-array localStorage data crashes startup",
    "failing_case": "localStorage 'notes' holds `{bad` or `{}`. JSON.parse throws, or notes is a non-array and `notes.filter` and `notes.find` fail. store.js stops loading and the whole app is dead."
  },
  {
    "file": "store.js",
    "line": 7,
    "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
    "title": "Date.now() ids can collide, so notes may share an id",
    "failing_case": "Two notes created in the same millisecond, or a double-click on New, get the same id. openNote, find and deleteNote then act on the wrong note, or on both at once."
  }
]
```