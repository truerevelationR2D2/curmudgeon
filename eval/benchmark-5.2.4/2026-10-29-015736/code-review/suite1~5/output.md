## Code review

Branch `main...HEAD`, commit `b1cc2d5`, four new files. There is no `CLAUDE.md` in the repo, so I checked for bugs only. The change is small, so I read the diff myself and did not launch the subagent pipeline.

**1. Stored XSS: note titles are written into `innerHTML` unescaped** (`app.js:10`, also `app.js:46`)
- `renderList` interpolates `${n.title}` into a template string and assigns it with `list.innerHTML +=`.
- The search handler does the same with `${s.title}` from the `/api/shared` response, using `insertAdjacentHTML`.
- A note titled `<img src=x onerror=...>` runs script as soon as the list renders, and again on every reload because it is saved in `localStorage`.
- Shared titles come from the server, so another user's note can run script in the viewer's page.
- Fix: build the `<li>` with `textContent` / `createElement`, or HTML-escape titles before interpolating them.

**2. `scheduleSave` throws and loses edits when no note is selected** (`store.js:14-20`, wired at `app.js:37-38`)
- `currentNote` starts as `null`. It is also set back to `null` in `removeNote` (`app.js:26`), which leaves the title and body inputs showing the old text.
- On a fresh install with no notes, typing in `#title` or `#body` fires `scheduleSave`. 500 ms later the timeout runs `currentNote.title = ...` and throws `TypeError: Cannot set properties of null`.
- The same happens after deleting the open note and then typing, or after deleting it while a save is still pending.
- The "Changes save automatically" hint is then false: nothing is saved and nothing tells the user.
- Fix: return early in the timeout callback when `!currentNote`, or disable the inputs until a note is open.

Both issues are in the new code and neither depends on unusual input.