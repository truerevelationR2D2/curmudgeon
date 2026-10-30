## Code review: "Add the app"

No GitHub comments were posted and no files were changed. The CLAUDE.md agents found nothing, because the repo has no CLAUDE.md. The review of the diff turned up 10 validated issues, listed below. I dropped one finding after validation. A few validators couldn't run `git diff main...HEAD` and read the working tree instead. They matched the diff on every line I compared.

### Bugs
1. **`refund()` always reports success** (`api.js:10-13`, `app.js:49-51`). The `fetch` is neither awaited nor checked, and the function always returns `{ok: true}`. A failed refund shows "Refunded N orders!".
2. **The first page of orders never shows** (`app.js:3`, `app.js:27`). `page` starts at 1 but `start = page * PAGE_SIZE` is 0-based, so orders 0–9 are skipped on load. Clicking Prev shows them under the label "Page 0".
3. **The page total is wrong** (`app.js:34`). `Math.floor` should be `Math.ceil`: 25 orders show "of 2" and 5 orders show "of 0".
4. **The refund selection never shrinks** (`app.js:35`). Unchecking a box doesn't remove its id, re-checking adds a duplicate, and nothing clears `selected` on reload, page change or refund. "Refund selected" can therefore refund orders the user unchecked or can no longer see, and the toast count is wrong.
5. **Search text isn't URL-encoded** (`api.js:6`). `query` goes into the URL raw, so `&`, `#` and `+` in a search such as "Smith & Sons" send the wrong request. The validator narrowed this to `query` only: `status` comes from a fixed `<select>`.

### Security
6. **Stored XSS** (`app.js:32`). `o.customer.name`, `o.id` and `o.status` go into `tb.innerHTML` unescaped. A hostile customer name would run script in a staff member's session, where the page can use the API key and issue refunds.
7. **The API key is in browser code** (`api.js:3`, `index.html:25`). It is sent as a Bearer header from the client, and the change has no server code at all. The value is a placeholder, but the design exposes whatever real key replaces it.

### README claims the code contradicts
8. **`README.md:6`, "the API key never leaves the server"** is false, for the reason in 7.
9. **`README.md:9`, "Refunds are confirmed before they are sent"** is false. The click handler calls `refund()` directly, with no `confirm()` or modal.
10. **`README.md:5`, "meets WCAG 2.1 AA, including 44 px touch targets"** is false in several places:
    - `styles.css:19` removes focus outlines.
    - `styles.css:18` sets buttons to `padding: 2px 4px; font-size: 12px` with `#aaa` text.
    - `index.html:19` makes "Refund selected" a `<span>`, so the keyboard can't reach it.
    - The status dot is colour only, and the search box has no label.
    - Criterion 2.5.5 (44 px targets) is Level AAA, not AA.

    The same README section also contains an arithmetic error: `README.md:8` says 12 seats at $15, annual, 20% off, is $1,440 a year. Neither a per-month nor a per-year price gives that: $15 per seat per month gives $1,728, and $15 per seat per year gives $144.

### Filtered out
- **"Renders 10,000 orders instantly"** (`README.md:7`) was rejected. The row loop covers only the 10 orders on the current page, so the code doesn't definitely contradict the claim.