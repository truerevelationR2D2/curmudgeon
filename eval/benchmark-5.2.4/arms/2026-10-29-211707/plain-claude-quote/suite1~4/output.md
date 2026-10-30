```json
[
 {
  "file": "app.js",
  "line": 11,
  "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
  "title": "Note titles are inserted into innerHTML without escaping, which allows HTML/script injection and breaks the markup.",
  "failing_case": "Set a note's title to `<img src=x onerror=alert(1)>`. The next renderList() runs the handler. A title like `</span><li>` also corrupts the list."
 },
 {
  "file": "app.js",
  "line": 46,
  "quote": "    document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
  "title": "Titles returned by the server are injected as raw HTML (XSS). Responses can also arrive out of order, so stale shared results are appended to a list that a newer keystroke has already re-rendered, giving duplicates or results for the wrong query.",
  "failing_case": "The server returns a shared note titled `<img src=x onerror=...>`, and it executes. Separately, type 'a' then 'ab'. If the 'a' response arrives after the 'ab' response, its items are appended after the 'ab' items and both sets show."
 },
 {
  "file": "store.js",
  "line": 16,
  "quote": "    currentNote.title = document.getElementById('title').value;",
  "title": "The debounced save dereferences currentNote, which is null after the open note is deleted (or when no note was ever opened). The editor inputs stay enabled and still hold the old text.",
  "failing_case": "Open a note, click its trash icon (removeNote sets currentNote = null, and the editor isn't cleared), then type in the title or body. After 500ms the timer throws `TypeError: Cannot set properties of null`, and the edit is lost. Typing right before deleting has the same effect."
 },
 {
  "file": "store.js",
  "line": 2,
  "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
  "title": "Unguarded parse and read of stored data. Corrupt JSON, or a storage SecurityError, throws at load, so store.js fails and app.js then fails on the undefined `notes`. Parsed data that isn't an array also breaks `notes.filter`.",
  "failing_case": "localStorage 'notes' is `{bad` or `{}`. The page loads blank and every later script errors, while persist() guards its own failures."
 },
 {
  "file": "store.js",
  "line": 7,
  "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
  "title": "Using Date.now() as the id can produce duplicate ids when two notes are created in the same millisecond.",
  "failing_case": "Two createNote() calls in the same millisecond (a scripted or fast double-trigger) give identical ids. openNote and deleteNote then act on the wrong note, and deleting one removes both."
 },
 {
  "file": "store.js",
  "line": 20,
  "quote": "    persist();",
  "title": "After an autosave the list isn't re-rendered, so the sidebar title and the '#rank' badge stay stale. The search filter is also not re-applied.",
  "failing_case": "Open a note, rename it to 'Groceries', and wait for the save. The sidebar still shows 'Untitled' and the old rank until some other action calls renderList()."
 },
 {
  "file": "app.js",
  "line": 8,
  "quote": "    const sorted = notes.slice().sort((a, b) => b.updated - a.updated);",
  "title": "The full sort is repeated inside the per-note loop, which makes rendering O(n² log n). It is combined with `list.innerHTML +=`, which reparses the whole list for every item. Re-rendering also loses the focus and state of the list.",
  "failing_case": "With a few thousand notes, every keystroke in the search box re-renders slowly and freezes the UI."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "document.getElementById('new').addEventListener('click', () => { const n = createNote(); openNote(n.id); });",
  "title": "A new note is opened while a search filter is active, but the list is re-rendered with that filter. The new 'Untitled' note is hidden, yet it is the current note and shows in the editor.",
  "failing_case": "Type 'milk' in search, then click 'New note'. The editor shows an Untitled note, but the list does not."
 }
]
```
