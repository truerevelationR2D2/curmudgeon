## Code review: "Add the app"

The reviewers found 12 issues in the diff `main...HEAD`. An independent validator confirmed each one, so all 12 remain. No CLAUDE.md files exist in the repo, so there were no CLAUDE.md violations. Nothing was posted and no files were changed.

### Security
1. **API key in browser code.** `api.js:3` hard-codes `API_KEY` in a script the browser loads (`index.html:25`) and sends it as a Bearer token from the client (`api.js:6`, `api.js:11`). Anyone can read it, and it contradicts `README.md:6` ("the API key never leaves the server"). The current value is a placeholder, but any real key would be exposed.
2. **Unescaped HTML (XSS).** `app.js:32` writes `o.customer.name`, `o.id`, `o.status` and `o.total` into `tb.innerHTML` without escaping. The validator noted this is exploitable only if the API lets markup into those fields, and nothing in the repo shows it doesn't.
3. **Search text not URL-encoded.** `api.js:6` puts `query` into the URL without encoding, and `app.js:45` calls `load` on every keystroke. Typing `a&status=refunded` adds a second `status` parameter, and `#` cuts off the rest of the URL.

### Wrong behaviour
4. **Refunds always report success.** `api.js:11-12` doesn't await the fetch and always returns `{ ok: true }`. The "Refunded N orders!" toast (`app.js:50-51`) therefore appears even when the request fails.
5. **First page of orders is never shown.** `page` starts at 1 (`app.js:3`) but `start = page * PAGE_SIZE` (`app.js:27`), so orders 0–9 are skipped on load.
6. **Page count rounds down.** `app.js:34` uses `Math.floor`, so 15 orders shows "of 1" and 5 orders shows "of 0". It should use `Math.ceil`.
7. **Unchecking a box doesn't deselect the order.** The handler at `app.js:35` only pushes ids into `selected`. Unchecked orders are still refunded, ids can be added twice, and `selected` is never cleared. The toast count is wrong too.
8. **Prev and Next have no limits.** `app.js:47-48` lets `page` go below the first page, which gives a negative slice start, or past the last page, which shows an empty table.
9. **Revenue is subtracted twice.** `app.js:16` subtracts refunded orders from a sum that only ever included paid ones. Revenue is wrong whenever an order is refunded and can go negative, and "AVG ORDER" (`app.js:18`) inherits the error.

### README claims the code disproves
10. **Price is wrong.** `README.md:8` says 12 seats at $15 with 20% off is $1,440 a year. If $15 is per seat per month, the right figure is 12 × 15 × 12 × 0.8 = $1,728. If it is per year, the right figure is $144. Neither reading gives $1,440, and the README never says which period applies.
11. **Accessibility claim is false.** `README.md:5` claims WCAG 2.1 AA with 44 px touch targets.
    - Buttons have `padding: 2px 4px; font-size: 12px` (`styles.css:18`).
    - `outline: none` on focus (`styles.css:19`) fails 2.4.7, which is Level AA.
    - "Refund selected" is a `<span>` (`index.html:19`), so keyboard users can't reach it. That fails 2.1.1, which is Level A.
    - The 44 px target criterion (2.5.5) is Level AAA, not AA.
12. **Refund confirmation doesn't exist.** `README.md:9` says refunds are confirmed before they are sent, but the click handler (`app.js:49-50`) calls `refund(selected)` immediately.

The price validator couldn't run `git diff` to confirm `README.md` is new in this change. Other validators confirmed all five files are new, so I'm treating it as introduced here.