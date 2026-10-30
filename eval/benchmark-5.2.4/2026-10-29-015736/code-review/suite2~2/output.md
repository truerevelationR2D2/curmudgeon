## Code review: `git diff main...HEAD` (commit 7becb4a, 5 new files)

There is no CLAUDE.md in the repo, so I checked for bugs and for README claims the code contradicts. I read the diff directly and did not launch subagents, because the change is small. I did not run the app. Each finding below is visible in the diff text.

**Bugs**

1. **The first page of orders is never shown.**
   - `app.js:6` starts with `page = 1`, but `app.js:31` computes `start = page * PAGE_SIZE`, so the first 10 orders are skipped.
   - The label at `app.js:37` uses `Math.floor(orders.length / PAGE_SIZE)`. That undercounts the pages whenever the total isn't a multiple of 10.
   - Prev and Next at `app.js:48-49` have no bounds, so `page` can go to 0 or negative, or past the last page.

2. **The refund is never awaited, so the UI reports success it hasn't confirmed.**
   - `refund()` in `api.js:10-13` calls `fetch(...)` without `await` and always returns `{ ok: true }`.
   - `app.js:52` then shows "Refunded N orders!" even if the request fails or the server rejects it.
   - The README says "Refunds are confirmed before they are sent", but no confirmation step exists.
   - The click handler also doesn't check that anything is selected.

3. **The selection list can only grow.**
   - The handler at `app.js:39` pushes the id when a box is checked and never removes it when the box is unchecked.
   - Unchecked orders are therefore still refunded, and checking a box twice puts the id in the list twice.
   - The list is also not cleared when you change page or filter.

4. **The API key is hardcoded in the client.**
   - `api.js:3` holds `API_KEY` in a script that `index.html` loads in the browser.
   - The README says "the API key never leaves the server". That is false, since the key is in the page source and every request header.

5. **The pricing example in the README is wrong.**
   - $15 × 12 seats × 12 months is $2,160. With 20% off that is $1,728 a year, not $1,440.

6. **The accessibility claims in the README are false.**
   - It says "Fully accessible… WCAG 2.1 AA, including 44 px touch targets".
   - The "Refund selected" control is a `<span>` (`index.html:19`). It can't be reached or activated from the keyboard.
   - `styles.css:19` removes the focus outline on buttons and inputs.
   - The Prev and Next buttons are about 12 px text with 2px 4px padding, and `#aaa` text on the near-white background has far too little contrast.
   - The status is shown only as a coloured dot, with no text.
   - The table is fixed at `width: 1000px`, so it overflows on small screens.
   - There are no `<label>` elements for the search box or the status select.

**Security**

7. **Cross-site scripting through the customer name.** `app.js:34` builds table rows by interpolating `o.customer.name` and `o.id` into `innerHTML` without escaping. A name like `<img onerror=…>` runs script in a page that holds the API key.

8. **The search and status values are not URL-encoded.** `api.js:6` puts `query` and `status` straight into the URL. Characters such as `&` or `#` break or inject query parameters.

**Smaller issues, same files**

- `renderStats` divides by `orders.length`, so an empty result shows `$NaN` as the average order (`app.js:19`).
- The README's "renders 10,000 orders instantly" has no benchmark. Every search keystroke refetches and recomputes stats over all orders, with no debounce.