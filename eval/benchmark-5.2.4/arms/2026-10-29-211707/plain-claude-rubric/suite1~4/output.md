Bugs found (code read and traced, nothing run; no files changed). Line numbers are per file.

**High**

1. **store.js:64-72 — a pending save writes to the wrong note, or crashes.** The debounce fires 500 ms later and writes to whatever `currentNote` is at that moment, not the note that was edited. Sequence: type in note A's title, then click note B within 500 ms. `openNote` loads B's fields, and then the timer copies the editor contents (B's) into B. A's edit is lost. Even worse, if you edit A and click B, then edit B, A's text is never saved. Other sequence: edit a note, then click its 🗑 within 500 ms. `currentNote` becomes null (app.js:26), the timer fires, and `currentNote.title` throws a TypeError. The edit to the deleted note is also dropped. Closing the tab inside the 500 ms window loses the last edit, because there is no flush on `pagehide`.

2. **store.js:53 — a corrupt `notes` value in localStorage breaks the app.** `JSON.parse` is unguarded. If `notes` holds `{bad`, store.js throws at load and app.js never runs, so the page is permanently dead until the user clears site data. Valid JSON that isn't an array, such as `{}` or `"x"`, passes the `|| []` fallback and then fails later at `notes.filter` or `notes.push`. Old records missing `title` or `body` crash `n.title.toLowerCase()` (app.js:6) and the `.value` assignment at app.js:18. Rubric: State persistence, sandbox scenario 2.

3. **store.js:74-78 — write failures are swallowed, so the UI says "Changes save automatically" when nothing saved.** If localStorage is full or blocked, `catch (e) {}` hides it. The user keeps typing and loses everything on reload. Rubric: success shown while the work failed.

4. **app.js:10-12 and 46 — XSS from note titles and shared results.** `n.title` and `s.title` go into `innerHTML` unescaped. Create a note titled `<img src=x onerror=alert(1)>`: it runs on every `renderList` and on reload. A title like `</span><b>` also breaks the markup. Shared results from `/api/shared` are injected the same way, so any other user's shared note title runs script in the viewer's page. Rubric: Type safety and boundaries, sandbox scenario 10.

**Medium**

5. **store.js:58 — ids come from `Date.now()`.** Two `createNote` calls in the same millisecond, such as a fast double-click or a script, give two notes with the same id. `openNote` and `deleteNote` (store.js:81) then act on the wrong one. Deleting one deletes both. Rubric: State persistence, sandbox scenario 3.

6. **app.js:40-48 — stale search responses are applied out of order.** There is no abort and no sequence check. Type "ab", and the response for "a" arrives after the one for "ab". The older results are appended to a list already rendered for "ab". Also, each response appends to the list without clearing the previous shared items: `renderList(q)` clears the list, but a late response from an earlier keystroke still lands after it. Shared notes that no longer match are shown. A non-OK response (the `res.ok` check is missing) is parsed as JSON. If it returns an object instead of an array, `shared.map` throws, and the error goes only to `console.log`. The user never sees that the search failed.

7. **app.js:10-12 and 20 — wrong list row on interaction.** `removeNote` is called via inline `onclick="removeNote(${n.id}, event)"` on a `div`. It works with the mouse, but the `div` is not focusable, has no role, and has `opacity: 0` until hover. The keyboard cannot reach delete (styles.css:123). There is also no confirm or undo, so deleting is immediate and permanent. Rubric: Accessibility (WCAG 2.1.1, keyboard) and States, destructive action.

8. **app.js:8-9 — O(n²) rank computation.** For each shown note, the whole array is copied and sorted. Cost per keystroke in search is n·(n log n). 500 notes is about 250k comparisons per render at minimum, and every `openNote` and every search keystroke triggers it. Rubric: Scalability, sandbox scenario 7. A single sort before the loop fixes it. Also, `innerHTML +=` inside the loop (line 10) reparses the whole list on every iteration, so total work is quadratic in the number of rows.

9. **app.js:10-12 / store.js:69 — rank is wrong or confusing after search.** `#rank` is computed over all notes, but displayed on a filtered list. This is cosmetic. The real problem is that `updated` is only changed on a save, so the rank never changes while you're typing, and the list isn't re-rendered after a save (the timer in store.js:66-71 never calls `renderList`). Edit a title and the list keeps showing the old title until the next render. Reload, or click something, to see it.

10. **app.js:1-2 / 51 — first run, empty state.** With no notes, the editor inputs are still enabled. Typing triggers `scheduleSave` with `currentNote === null`, and 500 ms later it throws a TypeError. The text is silently lost. There is no empty-state message either. Sandbox scenario 1.

**Low (accessibility and layout)**

11. **styles.css:117 — focus outlines are removed** on buttons, inputs and the textarea, with no replacement. Keyboard users can't see focus (WCAG 2.4.7, AA).

12. **styles.css:113 and index.html:88 — fixed 1200 px width, and zoom is disabled** by `maximum-scale=1`. On a 390 px phone the page scrolls sideways, and the 300 px column plus the editor overflows. Pinch-zoom is blocked (WCAG 1.4.4). Sandbox scenario 9.

13. **styles.css:122, 126 — contrast.** `#bbb` on white (rank) and `#ccc` on white (hint) are both far below 4.5:1 (roughly 1.9:1 and 1.6:1). WCAG 1.4.3 AA failure.

14. **index.html:96, 102-103 — the search, title and body fields have no label** (`placeholder` only on search, nothing on the title input and textarea). Screen readers can't name them. Note list items are `li` elements with a click handler and no `tabindex`, so notes can't be opened by keyboard at all (WCAG 2.1.1, a keyboard blocker on the main task, which arguably makes this High).

**Nits (not counted):** the hero's "Lorem ipsum" placeholder copy and "✨ Welcome to NoteMaster" are boilerplate; the `Inter` font is referenced but never loaded; "Submit"-style generic copy is absent but the "🗑" button has no text name.