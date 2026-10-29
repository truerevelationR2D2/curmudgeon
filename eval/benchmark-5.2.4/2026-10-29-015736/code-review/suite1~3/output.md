## Code review: `git diff main...HEAD` (commit `cc7a3a5`, "task")

I found 3 issues. The branch adds a new notes app (`index.html`, `app.js`, `store.js`, `styles.css`). There is no `CLAUDE.md` in the repo, so I checked only for bugs. I read the code and traced each issue by hand. I did not run the app or launch the validation subagents.

**1. Stored XSS: note titles are injected as raw HTML** (`app.js:12`, `app.js:46`)
- `renderList` interpolates `${n.title}` straight into a template string and appends it with `list.innerHTML +=`.
- The `/api/shared` results are interpolated the same way, as `${s.title}` into `insertAdjacentHTML`.
- A title such as `<img src=x onerror=alert(1)>` runs script as soon as the list renders. For shared notes, the server response is the source, so another user's title would run in the viewer's page.
- Fix: set `textContent` on elements built with `createElement`, or escape the title before interpolating.

**2. `scheduleSave` crashes when no note is open** (`store.js:14-21`)
- The 500 ms timer callback dereferences `currentNote.title` without a null check.
- `currentNote` is `null` on first load with no notes (`notes[0]` is falsy, so `openNote` is never called). It is also set to `null` in `removeNote` after deleting the open note.
- The `#title` and `#body` inputs stay editable in both cases. Typing in either one throws `TypeError: Cannot set properties of null` half a second later, and the typed text is never saved.
- Fix: guard with `if (!currentNote) return;`, or disable the inputs while nothing is open.

**3. Switching notes within 500 ms loses the pending edit** (`store.js:14-21`, `app.js:16-21`)
- The debounced save reads the current values of `#title` and `#body` from the DOM when it fires, and writes them to whichever note is `currentNote` at that moment.
- Edit note A, then click note B within 500 ms. `openNote` loads B's content into the inputs and sets `currentNote = B`.
- The timer then fires and saves B's own content back to B. A's edit was never written.
- Fix: flush or cancel the pending save, bound to the correct note, at the start of `openNote`, or capture the note and its values when the timer is scheduled.

I did not flag the following as defects: the O(n² log n) re-sort inside the `forEach` in `renderList`, the possible out-of-order `/api/shared` responses, and the CSS and accessibility choices (`maximum-scale=1`, `outline: none`, fixed 1200px width).