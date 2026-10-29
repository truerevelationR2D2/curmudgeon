## Code review: `main...HEAD` (commit 802f56f)

I read the diff directly. It adds a new 5-file app and the repo has no `CLAUDE.md`, so there was nothing to check for compliance. The diff is small, so I did not launch the agent fan-out. These are the problems I'm confident are real.

### Bugs

1. **Pagination skips the first page** (`app.js`, `renderTable`).
   - `page` starts at 1 but `start = page * PAGE_SIZE`, so the first 10 orders are never shown.
   - `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}` should round up (`Math.ceil`). With 25 orders it says "of 2", but there are 3 pages.
   - Prev and Next have no bounds. Prev can reach page 0 or below, and Next can go past the last page into an empty table.
   - `page` is not reset when the search or status filter changes.

2. **Refund reports success whether or not it worked** (`api.js` `refund`, `app.js` refund handler).
   - `fetch` is not awaited and its result is not checked, and the function always returns `{ ok: true }`.
   - The toast says "Refunded N orders!" even when the request fails.
   - There is no confirmation step, which contradicts the README ("Refunds are confirmed before they are sent").
   - Refunding with nothing selected still shows "Refunded 0 orders!".

3. **The selection list is wrong** (`app.js`).
   - The `onchange` handler only pushes ids. Unchecking never removes them, and re-checking adds duplicates.
   - `selected` is never cleared after a refund or a re-render, so a later refund can include orders the user no longer sees ticked.
   - Together with the success toast in item 2, this can refund the wrong orders.

4. **`renderStats` gives `NaN` for an empty list.** `revenue / orders.length` divides by zero when a search returns nothing, so "AVG ORDER" shows `$NaN`.

5. **Stored XSS** (`app.js`). `o.customer.name` and `o.id` are put into `innerHTML` unescaped. A customer named `<img src=x onerror=...>` runs script in the page, and that page holds the API key.

6. **Query is not URL-encoded** (`api.js` `getOrders`). `q=${query}` breaks on `&`, `#` and similar characters, and lets a user inject extra parameters such as `&status=`.

7. **Stale responses can overwrite newer ones** (`app.js`). `oninput = load` fires on every keystroke with no debounce or cancel, so a slow earlier response can replace the results for the latest query.

### Security

8. **A hardcoded API key is shipped to the browser** (`api.js`).
   - `API_KEY` is in a client-side script and sent as a bearer token. That contradicts the README ("the API key never leaves the server"). Anyone can read it from the page source.
   - The value here is a placeholder, but the pattern is the problem. The key must be held by a server-side proxy.

### README claims that are false

9. **The pricing arithmetic is wrong.** 12 seats × $15 × 12 months = $2,160. With 20% off that is **$1,728**, not $1,440.
10. **"Meets WCAG 2.1 AA, including 44 px touch targets (2.5.5)" is incorrect on two counts.**
    - 2.5.5 Target Size (Enhanced) is level AAA. The AA criterion is 2.5.8, at 24 px, and that is in WCAG 2.2, not 2.1.
    - The code also fails the claim:
      - "Refund selected" is a `<span>` with a click handler, so it can't be reached by keyboard and has no role.
      - `button:focus, input:focus, select:focus { outline: none }` removes the focus indicator (2.4.7).
      - Prev and Next are about 12 px text with 2–4 px padding, well under any target-size minimum.
      - Status is shown only by dot colour with no text (1.4.1).
      - `#aaa` on white is about 2.3:1, below the 4.5:1 contrast needed (1.4.3).
      - The checkboxes have no labels.
      - The table is a fixed `width: 1000px`, which overflows at phone width.
11. **"Renders 10,000 orders instantly" is unsupported.** Nothing in the diff is virtualised, and `renderStats` loops over all orders on every keystroke. I did not benchmark it. Treat it as unproven until someone measures it.

### Lower confidence (not blocking)

- `renderStats` applies the 8.25% tax and the gold discount to refunded orders as well. If `o.total` is already the charged amount, revenue is mis-stated. I can't confirm the intended semantics from the diff.
- `tb.innerHTML +=` inside a loop reparses the table on every row. It is harmless at 10 rows, but it undercuts the "fast" claim.