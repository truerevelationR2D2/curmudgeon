```json
[
  {
    "file": "app.js",
    "line": 11,
    "quote": "      <span class=\"t\">${n.title}</span><small>#${rank}</small>",
    "title": "Note titles are inserted into innerHTML without escaping (stored XSS and broken markup)",
    "failing_case": "Create a note and set its title to `<img src=x onerror=alert(1)>`. Once it saves, the next renderList() runs the handler. A title like `<b>` also breaks the list layout."
  },
  {
    "file": "app.js",
    "line": 46,
    "quote": "document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class=\"shared\">${s.title}</li>`).join(''));",
    "title": "Titles from the server are injected as unescaped HTML",
    "failing_case": "/api/shared returns [{\"title\":\"<img src=x onerror=alert(1)>\"}]. Typing any search runs that script."
  },
  {
    "file": "app.js",
    "line": 44,
    "quote": "    const res = await fetch('/api/shared?q=' + encodeURIComponent(q));",
    "title": "Search responses can arrive out of order and are appended with no stale check, so shared rows are duplicated or belong to an old query",
    "failing_case": "Type 'a' then 'ab'. If the 'a' response arrives after the 'ab' response, the list shows results for 'a'. Each response appends its own rows, but only renderList(q) clears the list, so a response arriving after a later keystroke's renderList leaves rows for the old query."
  },
  {
    "file": "app.js",
    "line": 27,
    "quote": "  renderList();",
    "title": "Deleting a note redraws the list without the active search filter, and the editor still shows the deleted note",
    "failing_case": "Type 'foo' in search, then delete one note. The full unfiltered list appears while the search box still says 'foo'. The title and body fields keep the deleted note's text."
  },
  {
    "file": "app.js",
    "line": 36,
    "quote": "document.getElementById('title').addEventListener('input', scheduleSave);",
    "title": "The list is never re-rendered after an autosave, so titles and #rank labels go stale",
    "failing_case": "Edit note B's title. The sidebar keeps the old title and rank until something else triggers a render. The edited note should move to #1 because its updated time changed."
  },
  {
    "file": "store.js",
    "line": 16,
    "quote": "    currentNote.title = document.getElementById('title').value;",
    "title": "The save timer dereferences currentNote when it fires, which throws if the note was deleted and loses edits if the note was switched",
    "failing_case": "Case 1: type in the body, then delete the current note within 500ms. currentNote becomes null and the timer throws TypeError. Case 2: edit note A, then click note B within 500ms. The timer then writes B's editor contents into B and A's edit is lost. Case 3: after deleting the last note, typing in the still-populated editor also throws."
  },
  {
    "file": "store.js",
    "line": 2,
    "quote": "let notes = JSON.parse(localStorage.getItem('notes')) || [];",
    "title": "Corrupt or invalid stored JSON throws at load, so store.js and app.js never initialise",
    "failing_case": "localStorage.notes = '{bad'. JSON.parse throws SyntaxError, the script aborts, and the app is blank on every reload."
  },
  {
    "file": "store.js",
    "line": 7,
    "quote": "  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };",
    "title": "Using Date.now() as the id can produce duplicate ids",
    "failing_case": "Two createNote() calls in the same millisecond, such as a double-click or a scripted call, give the same id. openNote and deleteNote then act on the wrong note, and deleting one removes both."
  },
  {
    "file": "store.js",
    "line": 27,
    "quote": "  } catch (e) {}",
    "title": "persist() silently swallows storage failures, but the UI still says changes save automatically",
    "failing_case": "When localStorage is full or blocked (private mode), setItem throws. The error is ignored and the 'Changes save automatically' hint stays up, so every note is lost on reload."
  }
]
```