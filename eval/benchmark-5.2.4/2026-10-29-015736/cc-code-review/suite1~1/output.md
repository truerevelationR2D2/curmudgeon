```json
[
  {
    "file": "app.js",
    "line": 10,
    "summary": "Note titles are interpolated into innerHTML unescaped, which gives stored XSS.",
    "failure_scenario": "A user, or a shared note, titled `<img src=x onerror=alert(1)>` runs script when the list renders. The payload is persisted in localStorage, so it re-executes on every load."
  },
  {
    "file": "app.js",
    "line": 46,
    "summary": "Server-returned shared-note titles are inserted with insertAdjacentHTML without escaping.",
    "failure_scenario": "Any other user's shared note with an HTML or script payload in its title runs in this origin whenever a search is typed. This is remote XSS from the /api/shared response."
  },
  {
    "file": "store.js",
    "line": 67,
    "summary": "The debounced save dereferences currentNote without a null check, and it saves into whatever note is current when the timer fires.",
    "failure_scenario": "Edit the title, then delete the current note within 500 ms. removeNote sets currentNote to null and the timer throws a TypeError. Alternatively, switch notes within 500 ms and the typed text is written into the newly opened note, overwriting its content. openNote never flushes or cancels the pending timer."
  },
  {
    "file": "store.js",
    "line": 53,
    "summary": "JSON.parse of localStorage is unguarded, and `notes` may not be an array.",
    "failure_scenario": "Corrupt or hand-edited localStorage 'notes' makes JSON.parse throw at load. Valid non-array JSON such as `{}` makes `notes.filter` throw. Either way store.js fails, app.js never runs, and the app is bricked until the storage is cleared."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The full notes array is copied and sorted inside the per-note loop, so rendering is O(n² log n). The ranks are also meaningless.",
    "failure_scenario": "With 1000 notes, each render does 1000 sorts. The rank is computed against all notes rather than the filtered set. It also shifts every time a note is saved, because `updated` changes. Compute the sort once outside the loop."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "`list.innerHTML +=` inside the loop re-parses and rebuilds the whole list on every iteration.",
    "failure_scenario": "Each iteration re-serialises and re-parses the existing DOM, which is quadratic and wasteful. It also discards state on existing nodes. Build one string and assign it once."
  },
  {
    "file": "store.js",
    "line": 58,
    "summary": "Note ids come from Date.now(), so two notes created in the same millisecond collide.",
    "failure_scenario": "Two notes created in the same millisecond share an id. Delete, open and find then act on the wrong one. Delete removes both notes, and notes.find always returns the first. Use crypto.randomUUID or a counter."
  },
  {
    "file": "app.js",
    "line": 12,
    "summary": "The delete control is a div with an inline onclick. It is hover-only, with no keyboard access, no confirmation and no undo.",
    "failure_scenario": "Keyboard and touch users cannot reach delete, because opacity is 0 until hover and the div is not focusable. A mis-click permanently deletes a note with no confirmation. The inline handler also relies on global functions."
  },
  {
    "file": "app.js",
    "line": 40,
    "summary": "The search handler fires a fetch on every keystroke with no debounce and no stale-response guard. It also appends to the list without clearing earlier shared entries.",
    "failure_scenario": "Typing 'abc' sends three requests. Responses can arrive out of order, so results for 'a' land after results for 'abc'. Shared `<li>` items are appended after renderList(q) resets the list, so a late response from a previous query is added to the current one. Failed fetches are only console.logged."
  },
  {
    "file": "styles.css",
    "line": 117,
    "summary": "Focus outlines are removed with no replacement, and the viewport meta blocks zoom. The layout is also a fixed 1200px width.",
    "failure_scenario": "Keyboard users see no focus indicator, which fails WCAG 2.4.7. `maximum-scale=1` prevents pinch zoom. `.container{width:1200px}` forces horizontal scrolling on phones and small windows."
  }
]
```