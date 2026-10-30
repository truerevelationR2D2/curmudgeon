```json
[
  {
    "file": "app.js",
    "line": 10,
    "summary": "Note titles are interpolated into innerHTML unescaped, which allows stored XSS.",
    "failure_scenario": "A user (or an imported note) sets a title like `<img src=x onerror=alert(1)>`. It is saved to localStorage and runs as script on every renderList call, including page load."
  },
  {
    "file": "app.js",
    "line": 46,
    "summary": "Titles from /api/shared are inserted as raw HTML, so the server response can inject script.",
    "failure_scenario": "A shared note titled `<script>` or `<img onerror=...>`, or a compromised endpoint, executes script in the page when the user types in search."
  },
  {
    "file": "app.js",
    "line": 40,
    "summary": "The search handler has a race between async responses and a list that is wiped on each keystroke. Shared results are appended with no cleanup.",
    "failure_scenario": "The user types 'a', then 'ab'. renderList clears the list, then the fetch for 'a' appends its results. The 'ab' fetch then appends too, so stale and duplicate shared items appear. Responses can also arrive out of order. A non-JSON or error response throws, and the error is only logged."
  },
  {
    "file": "store.js",
    "line": 16,
    "summary": "scheduleSave dereferences currentNote with no null check. The debounced timer is also not flushed or cancelled when the note is switched or deleted.",
    "failure_scenario": "The user types, then deletes the current note within 500ms. removeNote sets currentNote to null and the timer fires, so a TypeError is thrown. Alternatively, the user types in the title and clicks another note within 500ms. currentNote is now the new note, so the old edit is written onto the wrong note and overwrites its content. With no note open, typing in the empty title input also throws."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The sorted copy of notes is rebuilt, and indexOf run, inside the per-note forEach, so the work is O(n² log n). The rank is also computed from stale or unrelated data.",
    "failure_scenario": "With a few thousand notes, each keystroke in search re-sorts the whole array once per displayed note, and the UI freezes. The sort should be done once outside the loop."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "Setting list.innerHTML += inside the loop re-parses and rebuilds the whole list on every iteration. It also uses inline onclick handlers.",
    "failure_scenario": "This is O(n²) DOM work. Re-serialising the list each time drops the shared items and any other state. The inline handler requires a global removeNote."
  },
  {
    "file": "app.js",
    "line": 12,
    "summary": "The delete control is a non-focusable div that only becomes visible on hover. It has no keyboard or touch access and no confirmation, so a single click permanently deletes a note.",
    "failure_scenario": "Keyboard and touch users cannot delete at all, because the control is hidden without hover. A mouse user who clicks the invisible target loses the note with no undo."
  },
  {
    "file": "store.js",
    "line": 2,
    "summary": "JSON.parse of localStorage is not guarded. persist swallows every error silently.",
    "failure_scenario": "Corrupt stored data throws at script load, so store.js fails and app.js then fails on the undefined `notes`, leaving the app dead. When storage is full or disabled, persist silently drops saves while the UI still says 'Changes save automatically', so the user loses data without knowing."
  },
  {
    "file": "store.js",
    "line": 7,
    "summary": "Note id is Date.now(), which can collide, and createNote does not select or focus the new note.",
    "failure_scenario": "Two notes created in the same millisecond (a double-click, or an import) get the same id. openNote and deleteNote then act on both. Deleting one removes both."
  },
  {
    "file": "styles.css",
    "line": 6,
    "summary": "Focus outlines are removed with no replacement. The layout is also fixed at 1200px, and the viewport meta sets maximum-scale=1.",
    "failure_scenario": "Keyboard users get no visible focus indicator. On phones the 1200px container causes horizontal scrolling. maximum-scale=1 blocks pinch-zoom, which is an accessibility failure. The #ccc, #bbb and #eee text and border colors also fall below contrast minimums."
  }
]
```