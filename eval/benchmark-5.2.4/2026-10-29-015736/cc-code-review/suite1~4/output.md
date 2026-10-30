```json
[
  {
    "file": "app.js",
    "line": 10,
    "summary": "Note titles are interpolated into innerHTML without escaping (stored XSS).",
    "failure_scenario": "A note titled `<img src=x onerror=alert(1)>` runs script every time the list renders, and again on each reload because the title is saved to localStorage."
  },
  {
    "file": "app.js",
    "line": 46,
    "summary": "Titles from the /api/shared response are inserted as raw HTML.",
    "failure_scenario": "A shared note whose title contains markup or a script payload executes in the page when the user types in the search box."
  },
  {
    "file": "app.js",
    "line": 40,
    "summary": "The search handler does async work with no ordering guard and no dedupe, so it races.",
    "failure_scenario": "The user types 'ab'. The response for 'a' arrives after the response for 'ab', so stale shared results are appended. Each keystroke's response appends again, which duplicates shared items. renderList on the next keystroke clears them, so they flicker."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "Building the list with `innerHTML +=` inside a loop re-parses the whole list on every iteration. The sort and indexOf for the rank are also recomputed for every note, which makes rendering O(n² log n).",
    "failure_scenario": "With hundreds of notes, each keystroke in the search box re-sorts the full array once per visible note and rebuilds the DOM repeatedly, so typing lags. Sort once outside the loop."
  },
  {
    "file": "store.js",
    "line": 67,
    "summary": "The debounced save writes to currentNote without checking it, and it saves whichever note is current when the timer fires.",
    "failure_scenario": "The user edits note A and, within 500ms, clicks note B or deletes A. The timer fires and copies the editor contents (now B's, or none) into the new currentNote, which overwrites B with A's edits. If A was deleted, currentNote is null and the timer throws a TypeError, and the edit is lost."
  },
  {
    "file": "store.js",
    "line": 53,
    "summary": "JSON.parse of localStorage is unguarded, and so is the shape of the parsed value.",
    "failure_scenario": "If the 'notes' value is corrupted, store.js throws at load. app.js never runs and the app is blank. A non-array value such as an object makes notes.filter throw."
  },
  {
    "file": "app.js",
    "line": 12,
    "summary": "The inline onclick passes the id into an attribute, and the delete control is a non-focusable div. Delete has no confirmation and cannot be used from the keyboard.",
    "failure_scenario": "A keyboard or screen-reader user cannot delete a note. The delete icon has opacity 0 until hover, so it is invisible and unreachable on touch devices. A mis-tap deletes the note permanently with no undo."
  },
  {
    "file": "app.js",
    "line": 58,
    "summary": "Note ids use Date.now(), so two notes created in the same millisecond share an id.",
    "failure_scenario": "Two notes created in the same millisecond get the same id. Opening or deleting either one affects both, because find and filter match by id."
  },
  {
    "file": "styles.css",
    "line": 117,
    "summary": "Focus outlines are removed with no replacement, and the viewport meta blocks zoom.",
    "failure_scenario": "Keyboard users cannot see which control has focus. maximum-scale=1 disables pinch zoom for low-vision users. The fixed `width: 1200px` container also makes the page scroll horizontally on phones."
  },
  {
    "file": "app.js",
    "line": 51,
    "summary": "The editor inputs are not cleared when the current note is deleted or no note is open, and editing with currentNote null throws.",
    "failure_scenario": "The user deletes the open note. The title and body still show its text, and typing there triggers scheduleSave, which dereferences null currentNote and throws. On first load with no notes, typing in the editor throws the same way."
  }
]
```