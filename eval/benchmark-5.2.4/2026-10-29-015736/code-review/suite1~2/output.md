## Code review: `git diff main...HEAD` (1 commit, 4 new files)

No CLAUDE.md files exist in the repo, so I checked bugs only. I read the diff myself and did not launch the agent pipeline, because 126 lines was small enough to trace directly. I found 3 high-signal issues.

**1. Stored XSS: titles are inserted as raw HTML** (`app.js:11-13`, `app.js:46`)
- `renderList` puts `n.title` into `list.innerHTML` unescaped.
- The search handler puts `s.title` from `/api/shared` into `insertAdjacentHTML` unescaped.
- A note titled `<img src=x onerror=alert(1)>` runs script on the next render. It is saved in localStorage, so it runs again on every load.
- Shared notes come from the server, so another user's title executes in the viewer's session.
- Fix: build the elements with `textContent`, or escape the titles before interpolating them.

**2. Autosave throws when no note is open** (`store.js:14-17`)
- `scheduleSave` dereferences `currentNote` inside the timeout without a null check.
- `currentNote` starts as `null`, and `removeNote` sets it back to `null` after a delete.
- If the user types in the title or body in that state, the timer fires and throws `TypeError: Cannot set properties of null`. The same happens if they delete the open note within 500 ms of typing.
- Fix: guard with `if (!currentNote) return;`, and call `clearTimeout(saveTimer)` when the current note is deleted.

**3. Switching notes within 500 ms loses the edit** (`store.js:12-21`, `app.js:17-22`)
- The save timer reads `currentNote` and the DOM fields when it fires, not when the user typed.
- Edit note A, then click note B within 500 ms. `openNote` sets `currentNote = B` and loads B's text into the fields. The timer then writes B's own text back to B.
- A's edit is never saved.
- Fix: capture the note and its values when `scheduleSave` is called, or flush the pending save at the start of `openNote`.

Things I saw but did not flag, because they are lower confidence or style:
- Stale `/api/shared` responses can be appended out of order.
- `removeNote` drops the active search filter.
- The sort inside the `forEach` is O(n² log n).
- `maximum-scale=1` and `outline: none` hurt accessibility.