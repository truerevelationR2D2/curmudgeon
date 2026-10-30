**BLOCK** · Counts: 1 Critical, 11 High, 8 Medium, 3 Low

Three blind reviewers raised 70 findings and the script tally kept 23. Blind verifiers checked 21 of those and refuted none. I traced every finding from the code and ran three in Chromium (first run, corrupted saved data, hostile input). I haven't run the app. Contrast ratios are computed, not measured. The `/api/shared` server isn't in the repo.

The review changed no project files. It did write its own state to `.critic/` (the teardown is `.critic/last-review.md`), which `git status` will show as untracked.

**Critical**
- **C1** `app.js:46`: titles returned by `/api/shared` go into `insertAdjacentHTML` unescaped. A shared title like `<img src=x onerror=…>` runs script and can read and write the saved notes. Exploiting it needs another user able to share such a title.

**High**
- **C2** `app.js:11`: your own note titles are inserted unescaped too. A saved script title runs on every render and on page load.
- **C3** `app.js:32`: clicking a shared search result throws, because the row has no id. Typing afterwards throws too, so nothing saves until you open another note.
- **C4** `store.js:16`: the debounced save uses whichever note is current when the timer fires. If you switch notes within 500 ms, the first note's edit is lost. If you delete the open note, the timer throws.
- **C5** `store.js:18` and `:16`: typing with no note selected throws in the timer and the text is discarded. A new user hits this on first run.
- **C6** `store.js:26`: an empty catch hides write failures, while the page says "Changes save automatically".
- **C7** `app.js:10`: notes can only be opened with a mouse. The list rows aren't focusable.
- **C8** `styles.css:12`: delete is invisible until hover, has no confirm or undo, and is still tappable while invisible.
- **C9** `app.js:12`: delete is an unlabelled `div`. It has no keyboard access and no accessible name.
- **U1** `index.html:5`: `maximum-scale=1` blocks pinch zoom on Android Chrome (WCAG 1.4.4). This is the scan's one FAIL.
- **U2** `index.html:19`: the title and body fields have no label.
- **U3** `styles.css:6`: the focus outline is removed from every control with no replacement.

**Medium**
- **C10** `store.js:2`: an unguarded `JSON.parse` kills the whole app on bad saved data.
- **C11** `app.js:8`: each render is quadratic (a sort per row plus `innerHTML +=`).
- **C12** `app.js:36`: the list isn't refreshed after an edit, so titles and rank go stale.
- **C13** `app.js:46`: every keystroke fires a search with no debounce, and late responses are appended.
- **C14** `index.html:17`: first run shows a blank list and an editor that can't save.
- **C15** `store.js:15`: no flush on `pagehide`, so the last 500 ms of typing is lost on close or reload.
- **U4** `styles.css:2`: a fixed 1200 px container scrolls sideways on phones.
- **U5** `styles.css:15`: the hint text, rank numbers and input borders fall far below contrast minimums.

**Low**
- **C16** `app.js:27`: deleting a note drops the search filter and leaves the editor showing the deleted note.
- **C17** `store.js:7`: `Date.now()` ids can collide, and delete removes every note with the same id.
- **A1** `index.html:11`: placeholder copy shipped in the hero ("Lorem ipsum", "Welcome to NoteMaster").

Verifiers lowered three findings: C7 from Critical to High, C10 from High to Medium and C17 from Medium to Low. Two Nits are listed in the teardown but not counted. The variant hunt found nothing extra.

**Highest-value fixes**
1. Stop building list rows from HTML strings in both places (C1, C2).
2. Make the save capture the note when it's scheduled, guard the null case and flush on `pagehide` (C4, C5, C15).
3. Guard `JSON.parse` and show real save failures (C10, C6).
4. Use real buttons for notes and delete, add field labels and a visible focus style (C7, C9, U2, U3).
5. Use a fluid layout, drop the zoom block and darken the greys (U1, U4, U5).

To fix them, run `/curmudgeon:review fix` for all of them, or `/curmudgeon:fix patch [id]` for one.