```json
[
 {
  "file": "app.js",
  "line": 11,
  "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
  "title": "Note title is inserted into innerHTML without escaping (stored XSS / broken markup)",
  "failing_case": "Set a note's title to `<img src=x onerror=alert(1)>`. It is saved to localStorage, and the script runs every time renderList() runs. A title like `</span><b>` also breaks the list layout."
 },
 {
  "file": "app.js",
  "line": 46,
  "quote": "    document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
  "title": "Server-supplied shared note titles are injected as raw HTML (XSS). Responses can also arrive out of order or be appended twice, and nothing checks res.ok.",
  "failing_case": "The /api/shared endpoint returns a title of `<img src=x onerror=...>` and the script runs. Typing 'ab' quickly sends two requests. If the 'a' response arrives after the 'ab' response, stale shared items are appended to the list. Because renderList() is not re-run, the same shared items can also be appended twice."
 },
 {
  "file": "store.js",
  "line": 16,
  "quote": "    currentNote.title = document.getElementById('title').value;",
  "title": "The debounced save writes the editor contents into whatever note is current when the timer fires, and it throws if currentNote is null.",
  "failing_case": "Case 1: Edit note A, then click note B within 500ms. The timer fires and writes A's edited text into B, so B's content is overwritten and A's edit is lost. Case 2: Type in the body, then delete the current note within 500ms (or after deletion, type into the still-enabled fields). currentNote is null, so this line throws a TypeError. Case 3: Type in the fields before any note exists, and it throws the same way."
 },
 {
  "file": "store.js",
  "line": 2,
  "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
  "title": "Corrupt or invalid stored JSON throws at load, and an unavailable localStorage throws too. No script after this line runs, so the app is dead.",
  "failing_case": "localStorage 'notes' holds `{bad` or an old format: JSON.parse throws SyntaxError, `notes` is never defined, and app.js fails with a ReferenceError. In browsers that block storage access, getItem itself throws."
 },
 {
  "file": "store.js",
  "line": 7,
  "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
  "title": "Using Date.now() as an id allows duplicate ids",
  "failing_case": "Two notes created within the same millisecond (a double-click, or a script) get the same id. Opening, deleting or finding one then affects the other, because find() and filter() match both."
 },
 {
  "file": "app.js",
  "line": 26,
  "quote": "  if (currentNote && currentNote.id === id) currentNote = null;",
  "title": "Deleting the open note leaves its title and body in the editor, so the editor still shows and edits a deleted note",
  "failing_case": "Open note A and click its trash icon. The list updates, but the editor still shows A's text. Typing into it triggers scheduleSave with currentNote === null, which throws a TypeError, and the edits are never persisted."
 },
 {
  "file": "store.js",
  "line": 19,
  "quote": "    persist();",
  "title": "Saving never refreshes the list. The title shown and the '#rank' badge (sorted by updated) stay stale until some other action re-renders.",
  "failing_case": "Rename a note from 'Untitled' to 'Groceries'. The sidebar still shows 'Untitled' and the old rank, and a search for 'Groceries' won't match until a re-render."
 },
 {
  "file": "store.js",
  "line": 26,
  "quote": "  } catch (e) {}",
  "title": "Failed saves (quota exceeded, storage disabled) are silently swallowed, while the UI still says 'Changes save automatically'",
  "failing_case": "When localStorage is full or blocked (private mode), setItem throws and the error is ignored. The user sees no warning, and all notes are lost on reload."
 },
 {
  "file": "app.js",
  "line": 10,
  "quote": "    list.innerHTML += `<li data-id=\"${n.id}\" class=\"${currentNote && currentNote.id === n.id ? 'active' : ''}\">",
  "title": "The list is rebuilt by repeated `innerHTML +=` inside the loop, and each iteration re-sorts the whole array to compute the rank. That makes it O(n² log n) and re-parses the DOM every time.",
  "failing_case": "With a few thousand notes, every keystroke in search or every click on a note freezes the UI for seconds."
 }
]
```
