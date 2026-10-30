All four candidate issues were validated. The CLAUDE.md agents found nothing, because the repo has no CLAUDE.md files. I posted nothing and changed no files.

## Code review: "Add the app" (`git diff main...HEAD`)

**Issues found (4):**

1. **Clicking a shared search result throws a TypeError** (bug) — `app.js:46`, `app.js:30-33`, `app.js:17-18`
   - Shared results are rendered as `<li class="shared">` with no `data-id`.
   - The delegated click handler calls `openNote(Number(li.dataset.id))`, which is `openNote(NaN)`.
   - `notes.find` returns `undefined`, so `currentNote.title` throws on every click of a shared result.

2. **Typing after `currentNote` is null throws and loses the edit** (bug) — `app.js:23-28`, `app.js:36-37`, `store.js:13-21`
   - `removeNote` sets `currentNote = null` but leaves the title and body inputs filled and enabled.
   - `currentNote` also starts as `null` on a first visit, and the inputs are enabled there too.
   - The next keystroke starts the debounced save. After 500 ms, `currentNote.title = …` throws a TypeError and the text is never saved.

3. **Unescaped titles go into `innerHTML`, which allows XSS** (security) — `app.js:46` (also `app.js:10-12`)
   - Titles from `/api/shared` go through `insertAdjacentHTML` with no escaping.
   - A shared note titled `<img src=x onerror=…>` runs script in the browser of anyone whose search returns it.
   - Local titles take the same route through `list.innerHTML +=`. That case is mostly self-XSS.
   - The code has no sanitiser and no Content-Security-Policy.

4. **Switching notes within 500 ms loses the last edits** (bug) — `app.js:16-21`, `store.js:13-21`
   - The save timer reads the global `currentNote` and the field values when it fires, not when you typed.
   - If you type in note A and open note B (or click "New") within 500 ms, the timer writes B's values back to B.
   - A's edits never reach `notes` or `localStorage`. `openNote` neither flushes nor cancels the pending save.

Issue 4 depends on timing: it only happens if you switch notes within 500 ms of typing. The validator still traced it as real.