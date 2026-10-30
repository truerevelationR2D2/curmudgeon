```json
[
  {
    "file": "app.js",
    "line": 10,
    "summary": "Note titles are interpolated into innerHTML unescaped, so a note title containing HTML runs as script (stored XSS).",
    "failure_scenario": "The user types a title such as `<img src=x onerror=alert(1)>`. It is saved to localStorage, and renderList writes it into the list via innerHTML, so the handler fires on every render. The same applies on every reload."
  },
  {
    "file": "app.js",
    "line": 46,
    "summary": "Titles returned by /api/shared are inserted as raw HTML, and every keystroke fires a new request with no ordering guard.",
    "failure_scenario": "A server response or a shared note with a title like `<script>` or `<img onerror>` runs in the page (XSS from remote data). Responses can also arrive out of order. An older response then appends stale shared items, and a response for 'ab' can land after renderList('abc') and leave duplicates. Shared items are never cleared between keystrokes."
  },
  {
    "file": "store.js",
    "line": 16,
    "summary": "The debounced save dereferences currentNote without a null check and always writes to whichever note is current when the timer fires.",
    "failure_scenario": "The user types, then within 500ms deletes the current note (currentNote becomes null) and the timer throws a TypeError. Or the user types, then clicks another note within 500ms. openNote swaps in the other note's content, the timer fires, and the editor's new content overwrites that other note's title and body. The pending edit to the original note is lost."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "list.innerHTML += inside the loop re-parses and rebuilds the whole list on every iteration, and rank is computed with a full sort per item.",
    "failure_scenario": "The cost is O(n^2) DOM work plus O(n^2 log n) sorting per render, and the list re-renders on every search keystroke and every openNote. With a few hundred notes the UI lags. Rebuilding the DOM this way also drops any state on the existing list items."
  },
  {
    "file": "store.js",
    "line": 2,
    "summary": "JSON.parse on the stored value is unguarded and its result is not checked to be an array.",
    "failure_scenario": "If localStorage 'notes' is corrupt or not an array (for example `{}` or truncated JSON), or storage access throws as in private mode, store.js throws at load. app.js never runs and the page is dead. If the value is a non-array object, notes.filter later throws."
  },
  {
    "file": "store.js",
    "line": 7,
    "summary": "Note IDs come from Date.now(), so they can collide and are not unique.",
    "failure_scenario": "Two notes created within the same millisecond (a double-click or a scripted call) get the same id. openNote, delete and the active highlight then all target the first match, and deleting one removes both."
  },
  {
    "file": "store.js",
    "line": 26,
    "summary": "A persist() failure is swallowed silently, so the UI still says changes save automatically.",
    "failure_scenario": "When localStorage is full or blocked (quota exceeded, private mode), setItem throws and the catch discards it. The user keeps typing under the 'Changes save automatically' hint and loses every note on reload, with no warning."
  },
  {
    "file": "app.js",
    "line": 6,
    "summary": "The list shows only filtered notes, but the displayed rank is computed over all notes, and the list is not re-rendered after a save.",
    "failure_scenario": "While searching, the #rank labels skip numbers because they are relative to the unfiltered set. After the debounced save updates a title or `updated`, renderList is not called, so the list keeps the old title and old ranking until the next click or keystroke."
  },
  {
    "file": "styles.css",
    "line": 6,
    "summary": "The focus outline is removed on buttons, inputs and textareas, and no replacement focus style is given.",
    "failure_scenario": "Keyboard users get no visible focus indicator, which fails WCAG 2.4.7. The delete control is a div with an onclick, so it cannot be reached or activated from the keyboard, and it is invisible (opacity 0) until hovered."
  },
  {
    "file": "styles.css",
    "line": 2,
    "summary": "A fixed 1200px container, together with `maximum-scale=1` in the viewport meta, breaks small screens and blocks zoom.",
    "failure_scenario": "On a 375px phone the page is 1200px wide and needs horizontal scrolling, and the 300px+1fr grid never collapses. maximum-scale=1 stops pinch-zoom, which hurts low-vision users. Placeholder-looking copy ('Lorem ipsum') ships in the hero as well."
  }
]
```