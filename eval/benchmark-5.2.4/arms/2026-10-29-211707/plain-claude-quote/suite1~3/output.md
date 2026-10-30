```json
[
 {
  "file": "app.js",
  "line": 10,
  "quote": "  list.innerHTML += `<li data-id=\"${n.id}\" class=\"${currentNote && currentNote.id === n.id ? 'active' : ''}\">",
  "title": "Note titles are inserted into innerHTML unescaped, so a title containing HTML runs as markup (stored XSS). The title is user-controlled and stored in localStorage.",
  "failing_case": "Set a note title to `<img src=x onerror=alert(1)>`. After the 500ms autosave, the next renderList call (search, open, delete) executes the script. A title such as `</span><b>` also breaks the layout."
 },
 {
  "file": "app.js",
  "line": 11,
  "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
  "title": "The title is interpolated unescaped into HTML (XSS and broken markup).",
  "failing_case": "A title of `<script>` or `<img onerror=...>` is parsed as HTML when the list renders."
 },
 {
  "file": "app.js",
  "line": 46,
  "quote": "document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
  "title": "Server-supplied shared note titles are inserted as raw HTML (XSS). The results are also appended without clearing earlier shared entries, and async responses can arrive out of order or after a later render, so stale or duplicate shared items appear.",
  "failing_case": "Type 'a' then 'ab' quickly. Both responses append to the list, and the slower response for 'a' can land last. A shared title of `<img src=x onerror=...>` executes script."
 },
 {
  "file": "app.js",
  "line": 8,
  "quote": "    const sorted = notes.slice().sort((a, b) => b.updated - a.updated);",
  "title": "The notes array is copied and sorted inside the per-note loop, which is O(n² log n) and wasteful. The rank is also based on the whole list while the list shows only filtered notes, so the displayed ranks skip numbers.",
  "failing_case": "With 2000 notes, each keystroke in the search box re-sorts the array 2000 times and the UI lags. Filtering to one note shows '#37' instead of '#1'."
 },
 {
  "file": "app.js",
  "line": 12,
  "quote": "      <div class=\"del\" onclick=\"removeNote(${n.id}, event)\">🗑</div></li>`;",
  "title": "The delete control is a non-focusable div with an inline handler, so it can't be used from the keyboard. Clicking it also bubbles to the list's click handler: removeNote calls stopPropagation on the element, but the delegated listener is on the parent `ul`, so the stop works only because the inline handler runs first. Deletion needs no confirmation.",
  "failing_case": "Keyboard-only users cannot delete notes. A mis-click on the bin deletes the note permanently with no undo."
 },
 {
  "file": "app.js",
  "line": 26,
  "quote": "  if (currentNote && currentNote.id === id) currentNote = null;",
  "title": "After the current note is deleted, currentNote is null but the editor fields still hold its text. A pending autosave timer then dereferences null, and typing in the stale editor throws.",
  "failing_case": "Type in the body, then within 500ms click delete on that note. The scheduleSave timer fires and runs `currentNote.title = ...` on null, throwing a TypeError. Alternatively, delete the current note and type in the editor: the input handler throws and the text is lost."
 },
 {
  "file": "store.js",
  "line": 16,
  "quote": "    currentNote.title = document.getElementById('title').value;",
  "title": "The debounced save writes the editor contents into whichever note is current when the timer fires, not the note that was edited. Switching notes within 500ms writes the old note's text into the newly opened note. When no note has been created, currentNote is null and typing throws.",
  "failing_case": "Edit note A's body, then click note B within 500ms. openNote fills the editor with B's text, the timer fires, and B gets overwritten with the text shown in the editor, while A's edit is lost. On first load with no notes, typing in the editor throws a TypeError."
 },
 {
  "file": "store.js",
  "line": 7,
  "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
  "title": "The id is Date.now(), so two notes created within the same millisecond get the same id. Deleting or opening one then affects both.",
  "failing_case": "Call createNote() twice in a single tick, or double-click New very fast. Both notes get the same id. Deleting one removes both, and openNote always finds the first."
 },
 {
  "file": "store.js",
  "line": 2,
  "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
  "title": "There is no error handling around parsing or reading storage. Corrupt JSON or blocked storage throws at load, so store.js fails and the whole app is dead. persist() has a try/catch but this read does not. Valid JSON that isn't an array, such as an object, also breaks `notes.filter`.",
  "failing_case": "localStorage 'notes' set to '{bad' (or storage disabled in a private or sandboxed context) throws a SyntaxError or SecurityError at load, and app.js then fails with `notes` undefined."
 },
 {
  "file": "store.js",
  "line": 25,
  "quote": "    localStorage.setItem('notes', JSON.stringify(notes));",
  "title": "Save failures (quota exceeded) are silently swallowed, while the UI says 'Changes save automatically'. The user loses data with no warning.",
  "failing_case": "With storage full, the user types a long note. setItem throws, the empty catch ignores it, and after reload the edits are gone."
 },
 {
  "file": "index.html",
  "line": 5,
  "quote": "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, maximum-scale=1\">",
  "title": "maximum-scale=1 disables pinch zoom, an accessibility failure.",
  "failing_case": "A low-vision user on a phone cannot zoom the page."
 }
]
```
