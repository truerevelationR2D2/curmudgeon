## Code review

Reviewed `git diff main...HEAD` ("Add the app"): `app.js`, `index.html`, `store.js` and `styles.css`. Nothing was posted and no files were changed.

**CLAUDE.md compliance:** there are no CLAUDE.md files in the repo, so both compliance agents found nothing to check against.

**Bugs:** four issues were found and confirmed by independent validators. Both bug agents found the first two. Only one bug agent found each of the others.

1. **Clicking a shared search result always crashes** (`app.js:17-18`, `app.js:46`, click handler near `app.js:30-33`).
   - Shared results are added as `<li class="shared">` with no `data-id`.
   - The list click handler doesn't skip them, so it calls `openNote(Number(undefined))`, which is `openNote(NaN)`.
   - `notes.find` returns `undefined`, and `currentNote.title` on line 18 throws a TypeError.
   - `currentNote` is left `undefined`, and the later `scheduleSave` also throws, so further edits are lost.

2. **Typing with no note open throws and loses the edit** (`store.js:16`, reached via `app.js:36-37`).
   - `scheduleSave` writes to `currentNote.title`, `.body` and `.updated` with no null check.
   - `currentNote` is `null` on first load with no saved notes, because `app.js:51` only opens a note if one exists.
   - It is also `null` after the open note is deleted, because `removeNote` nulls it but leaves the old text in the editor.
   - The timer throws before `persist()` runs, so nothing is saved.

3. **The note list goes stale after edits** (`store.js:13-21`).
   - After the 500 ms debounce, `scheduleSave` updates `title` and `updated` and saves, but never calls `renderList`.
   - `renderList` is only called from `openNote`, `removeNote`, the search handler and initial load.
   - The sidebar keeps the old title and `#rank` until one of those runs.

4. **Server-supplied shared titles are inserted as raw HTML (XSS)** (`app.js:46`).
   - `s.title` from `/api/shared` goes through `insertAdjacentHTML` with no escaping and no CSP.
   - A title like `<img src=x onerror=...>` runs script on every search.
   - I assumed the server returns titles unsanitised, because the endpoint isn't in the repo.
   - `app.js:11` has the same unescaped `${n.title}` in `innerHTML`. On its own that is mostly self-XSS, because notes only come from the user's own input. But it lets a payload from issue 4 persist in `localStorage` and rerun on every load, and it mangles titles containing `<` or `&`. Fixing both with `createElement` and `textContent` covers it.

Left out as not high signal: performance, accessibility, the `res.ok` check, duplicated shared results, and the placeholder text. These came from the summary agent and weren't confirmed as definite bugs.