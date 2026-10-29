## Code review: `git diff main...HEAD` (commit a25253f, "task")

I reviewed this directly instead of launching sub-agents. The change is four new files and 126 lines. There is no CLAUDE.md in the repo, so I checked bugs only. I did not run the app; each finding comes from reading the diff.

### Issues found

1. **Stored XSS through note titles.** `app.js:10` puts `n.title` into `innerHTML` unescaped. `app.js:47` does the same with `s.title` from `/api/shared`. A note titled `<img src=x onerror=...>` runs script as soon as the list renders, and it stays in localStorage. Shared notes from the server make this exploitable by other users. Fix: build the `<li>` with `textContent`, or escape the title.

2. **Clicking a shared search result throws.** The shared `<li class="shared">` (`app.js:47`) has no `data-id`. The delegated click handler (`app.js:30-33`) matches any `li` and calls `openNote(Number(undefined))`. That is `openNote(NaN)`, so `notes.find` returns `undefined`. `currentNote` is then `undefined`, and `currentNote.title` on `app.js:16` throws a TypeError. Fix: ignore `li.shared`, or only act on `li[data-id]`.

3. **`scheduleSave` crashes, or saves into the wrong note.** `store.js:14-19` reads the global `currentNote` when the 500 ms timer fires, not when you typed.
   - **No note selected.** `currentNote` is `null` after the open note is deleted (`removeNote`, `app.js:22`). The editor fields keep the old text, so typing in them throws `Cannot set properties of null`. Edits are lost.
   - **Switching notes within 500 ms.** Typing and then clicking another note makes the pending timer write the first note's edited text (the fields now hold the second note's text) into the newly selected note. This corrupts the second note. Fix: capture the note (or its id) when scheduling, and guard against `null`.

4. **Overlapping shared-search responses duplicate results.** The `/api/shared` handler (`app.js:41-49`) appends results with `insertAdjacentHTML('beforeend', ...)`, and only `renderList` clears them. Each keystroke starts its own fetch. If responses arrive out of order, or overlap, the list shows stale and duplicate shared entries for the wrong query. Fix: track the latest query and drop stale responses, or render shared results into their own container.

I did not flag style issues such as the O(n²) rank sort in the render loop, the `outline: none` focus styling, `maximum-scale=1`, or the fixed 1200px container.