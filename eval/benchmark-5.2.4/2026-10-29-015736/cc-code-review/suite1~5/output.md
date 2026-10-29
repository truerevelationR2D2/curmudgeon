```json
[
  {
    "file": "app.js",
    "line": 10,
    "summary": "Note titles are interpolated into innerHTML unescaped, so a title containing HTML runs as markup (stored XSS).",
    "failure_scenario": "A user sets a note title to `<img src=x onerror=alert(1)>`. It is saved to localStorage and rendered through innerHTML on every renderList call. The script runs on each page load. Imported or synced notes would trigger it the same way."
  },
  {
    "file": "app.js",
    "line": 46,
    "summary": "Titles returned by /api/shared are inserted as raw HTML with no escaping.",
    "failure_scenario": "A shared note titled `<script>` or `<img onerror=...>` from the server runs in the page when the user searches. The server is untrusted input here."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "`list.innerHTML +=` inside the loop re-parses and rebuilds the whole list on every iteration. This is quadratic, and it also discards state on the existing nodes.",
    "failure_scenario": "With N notes the list is re-serialized and re-parsed N times on every keystroke in search."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The sorted copy of `notes` is rebuilt inside the per-note loop, which gives O(n² log n) work. The rank is also computed against all notes, not the filtered ones.",
    "failure_scenario": "With 1000 notes, each search keystroke sorts 1000 arrays of 1000 items. The rank shown on a filtered list also does not match the visible positions."
  },
  {
    "file": "app.js",
    "line": 12,
    "summary": "The delete control is a div with an inline onclick that has no keyboard access or accessible name. It is opacity:0 until hover, so it is hidden on touch devices and from keyboard users.",
    "failure_scenario": "On a phone, or with keyboard-only use, notes cannot be deleted. The 🗑 button is invisible and unfocusable. The inline handler also stops the click from reaching the list handler only because removeNote calls stopPropagation."
  },
  {
    "file": "store.js",
    "line": 53,
    "summary": "`JSON.parse(localStorage.getItem('notes'))` is not guarded. Corrupt or non-array data throws at load, so store.js and then app.js never run.",
    "failure_scenario": "localStorage 'notes' holds invalid JSON, or something like `{}` or `5`. The parse throws a SyntaxError, or `notes.filter` fails later. The app is blank until the user clears site data. Blocked storage also throws a SecurityError here. persist() has a try/catch but this read does not."
  },
  {
    "file": "store.js",
    "line": 67,
    "summary": "The debounced save dereferences `currentNote` after 500ms without checking it. The note may have been deleted or switched in the meantime.",
    "failure_scenario": "The user types and then deletes the note within 500ms. `currentNote` is null, so the timer throws a TypeError and the edit is lost. If the user opens another note within the window, the new note's fields are overwritten with the old note's pending title and body, because the values are read from the inputs at fire time. Typing in the title with no note selected also throws, since currentNote starts as null."
  },
  {
    "file": "store.js",
    "line": 58,
    "summary": "Note ids come from Date.now(), so two notes created within the same millisecond collide.",
    "failure_scenario": "A double-click on New note, or a fast import, creates two notes with the same id. `find` and `filter` then match both. Deleting one deletes both, and opening one opens the other."
  },
  {
    "file": "store.js",
    "line": 76,
    "summary": "persist() swallows every error silently, such as a full quota, while the UI says \"Changes save automatically\".",
    "failure_scenario": "A QuotaExceededError or storage-disabled error is ignored. The user keeps editing, sees the hint, and loses all changes on reload with no warning."
  },
  {
    "file": "index.html",
    "line": 88,
    "summary": "The viewport has `maximum-scale=1`, which blocks pinch zoom. The layout is fixed at `width: 1200px` and `300px 1fr`, so it is not responsive and overflows on phones. The inputs also have no labels, and `outline: none` removes the focus indicators.",
    "failure_scenario": "On a 375px phone the 1200px container forces horizontal scrolling, and users with low vision cannot zoom in. Keyboard users cannot see which control has focus. Screen readers announce the unlabeled title and body fields as unnamed edit boxes."
  }
]
```