## Code review

**Scope:** `git diff main...HEAD` ("Add the app"), 5 new files, 124 lines. No CLAUDE.md exists in the repo, so both compliance agents found nothing to check. Two Opus agents scanned for bugs (diff only, and introduced code). Each of the ten issues below was then checked by its own Opus validator, and every one was confirmed. I didn't run the app, and I posted nothing and changed no files.

### Bugs
1. **Pagination skips the first page** (`app.js:3`, `app.js:27-28`). `page` starts at 1, but the slice starts at `page * PAGE_SIZE`, so the first view shows orders 10–19. With fewer than 11 orders the table is empty. Prev/Next (`app.js:46-48`) have no bounds, so `page` can go below 0 or past the end.
2. **Page count is wrong** (`app.js:34`). `Math.floor(orders.length / PAGE_SIZE)` should round up. 15 orders reads "of 1", and 1–9 orders reads "of 0".
3. **Unticked orders still get refunded** (`app.js:35`). The checkbox handler only pushes ids onto `selected`. Nothing removes an id on uncheck, and the array is never cleared on reload or after a refund. Orders the user unticked, or that are no longer on screen, are still sent, and re-ticking adds duplicates.
4. **Refund always reports success** (`api.js:10-12`, `app.js:49-51`). `refund()` doesn't await `fetch` or check the response, and always returns `{ok: true}`. The "Refunded N orders!" toast appears even when the request fails.
5. **Search text isn't URL-encoded** (`api.js:6`). `query` goes into the URL raw, so a search for `Smith & Sons` is cut off at the `&`. A `#` drops the status filter. `status` comes from a fixed dropdown, so it isn't affected.

### Security
6. **API key shipped to the browser** (`api.js:3`, `api.js:6`, `api.js:11`). The key is sent as a Bearer token from client-side JS, so anyone can read it in DevTools. A real key would let any visitor issue refunds.
7. **Stored XSS** (`app.js:33`). `o.customer.name` from the API goes into `innerHTML` unescaped, as do `o.id` and `o.status`. A malicious customer name would run script for anyone viewing the table.

### README claims the code contradicts
8. **"API key never leaves the server"** (`README.md:6`) is false, for the reason in item 6.
9. **"Refunds are confirmed before they are sent"** (`README.md:9`) is false. The refund click handler at `app.js:49` calls `refund` immediately, with no confirmation step.
10. **Pricing is wrong** (`README.md:8`). 12 seats × $15 × 12 months is $2,160, and 20% off is $1,728, not $1,440. No reasonable reading of the line gives $1,440.
11. **"Fully accessible (WCAG 2.1 AA, 44 px targets)"** (`README.md:5`) is false.
    - `styles.css:19` removes focus outlines.
    - `styles.css:18` gives buttons 12px text with 2px/4px padding.
    - `index.html:19` makes "Refund selected" a `<span>` with only a click handler, so it can't be reached from the keyboard.
    - Criterion 2.5.5 (44 px targets) is Level AAA, not AA.

Items 8–11 are README claims rather than code bugs. I counted ten validated issues because items 6 and 8 share one root cause.

### Left out
- "AVG ORDER" showing `$NaN` with no orders. It only happens for certain inputs.
- The performance claim ("10,000 orders instantly"). It's a low-confidence performance concern.
- Out-of-order responses while typing, and the fixed 1000px table width. They depend on state, or are style.