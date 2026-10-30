# Curmudgeon review: **BLOCK**

Counts: 2 Critical, 14 High, 6 Medium, 3 Low. No files were changed. The full teardown is saved at `/tmp/dm-3pbcqqk5/work/.critic/last-review.md`.

Three blind reviewers raised 68 raw findings. The script counts kept 25 after dedup and verification. Verifiers confirmed 19 of the 23 packets and downgraded four (none refuted), which are the downgraded rows below. Three single-vote claims were dropped as unproven, and the variant hunt found nothing.

**Critical**
1. **Stored XSS in note titles** (`app.js:11`, 3 of 3 reviewers). Titles go into `innerHTML` unescaped. A title like `<img src=x onerror=…>` runs on every render and every load.
2. **Server titles injected as raw HTML** (`app.js:46`, 2 of 3). The same flaw applies to shared-note titles from `/api/shared`, so another user's note could run script and read your local notes. The server isn't in the repo, so I assumed a hostile response without seeing one.

**High**
3. **Corrupt saved data kills the app** (`store.js:2`). The load has no try and no shape check, so bad JSON leaves the list unrendered.
4. **Save timer throws with no note selected** (`store.js:16`, `app.js:26`). This happens on first run and after a delete, and the typed text is lost.
5. **Debounced save hits the wrong note.** Switching notes within 500 ms discards the edit and re-stamps the other note, which changes its rank.
6. **No flush on page close** (`store.js:15`). Edits in the last 500 ms are lost.
7. **Write failures are swallowed** (`store.js:26`). The page keeps saying "Changes save automatically".
8. **Layout has a fixed 1200 px width** (`styles.css:2`). It scrolls sideways on a phone and at 200% zoom.
9. **Notes and the delete control can't be used by keyboard.** Rows are plain `<li>`s and delete is a `<div onclick>`, hidden until hover. Verifiers lowered the original Critical to High.
10. **Accessibility defects:**
    - Zoom is blocked by `maximum-scale=1` (`index.html:5`). That is the one FAIL the scripted scan raised.
    - Title and body fields have no label.
    - The focus outline is removed with no replacement.
    - Rank and hint text contrast is about 1.9:1 and 1.6:1.

**Medium and Low**
- Six Medium findings. They cover quadratic list rendering, delete with no confirm or undo, and a crash when you click a shared result. They also cover stale titles after a save, search replies applied out of order, and white-on-indigo contrast just under 4.5:1.
- Three Low findings: `Date.now()` ids can collide, delete ignores the active search filter, and lorem ipsum hero copy shipped.

**Not checked or unproven**
- Reviewers A and B traced everything and ran nothing. Reviewer C drove most scenarios.
- The contrast ratios were computed by hand, and a verifier agreed with them.
- The "1.3 s at 500 notes" figure comes from reviewer C and I didn't re-run it.
- A verifier showed one claim in finding 3 was overstated. The unusable app is confirmed, but the claim that the next save overwrites your remaining data is not.
- No page was passed to the scan, so the browser checks (axe, keyboard reach, layout) didn't run.
- A two-tab overwrite of notes was dropped as unproven. It's plausible and worth a test.

**Decisions for you**
1. **Spot-check.** Four items are in `/tmp/dm-3pbcqqk5/work/.critic/spotcheck.md` for you to judge real, wrong or unsure. They are the viewport zoom block, the invisible delete control, the missing page-close flush, and the keyboard downgrade. Skipping is fine.
2. **Fixing.** I changed nothing, as asked. Run `/curmudgeon:review fix` for everything or `/curmudgeon:fix patch [id]` for one finding. My recommendation is to start with the XSS and the load guard.