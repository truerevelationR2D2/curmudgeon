## Code review

No issues found. Checked for bugs and CLAUDE.md compliance.

I reviewed `git diff main...HEAD` (one commit, six new files: `README.md`, `api.js`, `app.js`, `domain.js`, `index.html`, `styles.css`) myself rather than launching the parallel subagent pipeline. The change is small and there is no pull request to check. No `CLAUDE.md` exists in the repo, so there was nothing to check compliance against. I changed no files.

What I checked:
- **Script load order:** `index.html` loads `domain.js`, then `api.js`, then `app.js`. `api.js` calls `normaliseOrder` from `domain.js`, and `app.js` calls `summarise`, `clampPage` and `pageCount`, so every reference resolves.
- **Search races:** `load()` aborts the previous request. The `latestRequest !== controller` guards stop a stale response from overwriting newer state. The `finally` block resets `loading` only for the current request.
- **Refund flow:** it asks for confirmation, blocks double clicks with `state.refunding`, and reports success only after `refund()` resolves. Errors from the follow-up `load()` are caught inside `load()` itself.
- **Paging:** `clampPage` and `pageCount` handle an empty list, and the prev/next buttons are disabled correctly at both ends.
- **Rendering:** rows are built with `textContent`, so there is no HTML injection from order data.
- **README arithmetic:** 12 × $15 × 12 = $2,160, and 20% off is $1,728, which is correct.
- **README accessibility figures:** the CSS matches the stated 44 px control height and 24 px checkboxes.

Three things I saw but did not flag, because they are design choices or can't be proven wrong from the diff:
- `refundSelected` makes a new idempotency key on every attempt. A retry after a lost response therefore gets a fresh key. The error message tells the user to check order statuses before retrying.
- Refunded and pending orders count as zero revenue, but the "Average per order" figure still divides by all orders. This reads as intentional.
- The README's axe-core and 10,000-order timing claims can't be checked from the diff.