## Code review: "Add the app" (`git diff main...HEAD`)

I found 6 issues. Two Opus bug agents proposed them and a separate Opus validator confirmed each one. Nothing was posted and no files were changed.

The repo has no CLAUDE.md files, so the two compliance agents found nothing to check against.

1. **Stored XSS from shared note titles** (`app.js:46`). Titles from `/api/shared` are written by other users. They go into `insertAdjacentHTML` unescaped, so a title like `<img src=x onerror=…>` runs script in anyone who searches. Fix: build the elements and set `textContent`.
   - The same unescaped pattern is on `app.js:10-11`, where `${n.title}` goes into `list.innerHTML`. A title containing `<` visibly breaks the list. That one is self-XSS only, because local titles never leave the user's browser.

2. **Clicking a shared search result crashes** (`app.js:30-33` and `46`, then `18`). Shared `<li>` items have no `data-id`. The click handler calls `openNote(Number(undefined))`, which is `openNote(NaN)`. `notes.find` returns `undefined`, so `currentNote.title` throws a TypeError. After that, edits are no longer saved either.

3. **`scheduleSave` dereferences a null `currentNote`** (`store.js:15-18`). `currentNote` is `null` on a first visit with no notes, and after the open note is deleted (`app.js:26`). The editor fields stay editable, so typing throws a TypeError 500 ms later and the text is never saved.

4. **Edits lost when switching notes within 500 ms** (`store.js:13-21`, `app.js:16-21`). `openNote` and the "New" handler change `currentNote` and the fields without cancelling or flushing the pending timer. The timer then copies the new note's own fields back onto it. The previous note's last edits are lost, and the new note's `updated` timestamp changes for no reason.

5. **Stale and duplicated shared results** (`app.js:40-48`). Each keystroke clears and redraws the list, then appends its own response, with no abort or sequence check. Typing quickly leaves earlier queries' results in the list, and items that match several queries appear more than once.

6. **Sidebar goes stale after an edit** (`store.js:15-20`, `app.js:36-37`). The save callback never calls `renderList`. After you rename a note, the sidebar still shows the old title and `#rank` until something else redraws it.

Not flagged because they are style, input-dependent or the validators didn't treat them as high signal: the O(n²) re-sort in `renderList`, `maximum-scale=1`, `outline: none`, the fixed 1200px container, low-contrast greys, `Date.now()` id collisions, the unguarded `JSON.parse`, and the leftover "Lorem ipsum" hero text.