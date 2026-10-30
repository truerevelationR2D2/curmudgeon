## Code review: `git diff main...HEAD` (commit 39a536d, adds a note-taking app)

I found 3 high-signal issues. No `CLAUDE.md` exists in the repo, so I checked bugs only. I read the diff directly instead of launching subagents, because it is only 4 new files and 126 lines.

**1. Stored XSS: note titles and server-returned titles go into `innerHTML` unescaped**
- `app.js:11`: `<span class="t">${n.title}</span>` is built into `list.innerHTML`.
- `app.js:46`: `<li class="shared">${s.title}</li>` is built from the `/api/shared` response and passed to `insertAdjacentHTML`.
- A note titled `<img src=x onerror=...>` runs script as soon as the list renders, and again on every reload because the title is saved in localStorage.
- The shared-notes titles come from other users' data, so anyone who shares a note can run script in the viewer's page.
- Fix: set `textContent`, or escape the titles before building the HTML.

**2. `scheduleSave` throws when no note is selected, and loses edits when the selection changes**
- `store.js:15-17`: the timer callback dereferences `currentNote.title` without a null check.
- `currentNote` starts as `null` and `app.js` only calls `openNote` if a note exists. So on a fresh install, typing into the always-enabled `#title` or `#body` throws `TypeError: Cannot set properties of null` 500 ms later.
- `removeNote` also sets `currentNote = null`. Deleting the open note and then typing, or deleting it within 500 ms of the last keystroke, throws the same error.
- The callback reads the title and body from the DOM when it fires, not when you typed. If you switch notes within 500 ms, the previous note's edit is never saved.
- Fix: capture the note (or its id) when the save is scheduled, guard against null, and flush or cancel the pending save in `openNote` and `removeNote`.

**3. Shared-search results are appended with no ordering or cancellation, so they duplicate and go stale**
- `app.js:41-47`: each `input` event calls `renderList(q)` synchronously, then appends the fetched results to `#list` when the response arrives.
- Each keystroke starts its own fetch. Every response that returns appends its own batch to the same list, and nothing removes the earlier batches.
- Typing "abc" can leave results for "a", "ab" and "abc" in the list at once, in whatever order the responses arrive.
- A slow response can also arrive after you clear the search and add shared items to the unfiltered list.
- Fix: abort the previous fetch (an `AbortController` or a request counter), and discard any result whose query no longer matches the input.

Not flagged (style, or not definite bugs): the O(n² log n) rank computation inside the render loop, `Date.now()` used as the id, `maximum-scale=1` and `outline: none` hurting accessibility, and the fixed 1200px container width.