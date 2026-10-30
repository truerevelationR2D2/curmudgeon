Bugs found (no files changed). Line numbers are per file.

**Logic bugs**

1. `app.js:40`: the first page is skipped. `page` starts at 1, so `start = 1*10`. Orders 0–9 never show. With 25 orders, page 1 shows orders 10–19 and the label reads "Page 1".
2. `app.js:47`: the page count is wrong. `Math.floor(orders.length/PAGE_SIZE)` should be `Math.ceil`. With 25 orders it shows "of 2" when there are 3 pages. With 5 orders it shows "of 0".
3. `app.js:60-61`: Prev and Next have no bounds. Clicking Prev on page 1 gives page 0, then -1 (`slice(-10, 0)` is empty). Clicking Next past the end gives a blank table. Also, `load()` never resets `page` to 1 when the search or filter changes. If you are on page 3 and type a query with 5 results, the table is empty.
4. `app.js:31`: with an empty result, `revenue / orders.length` is 0/0, so the average shows "$NaN". Search "zzz" to trigger it. The same applies to `avg` for any empty status filter.
5. `app.js:26-29`: the revenue calculation is wrong.
   - The gold 10% discount and the 8.25% tax are applied to `o.total`, and refunds subtract that adjusted amount. This is only right if the API's `total` is pre-tax and pre-discount, which the code never checks.
   - "AVG ORDER" divides net revenue by all orders, including pending and refunded ones. A mix of 1 paid and 1 refunded order of equal value gives revenue 0 and average 0.
6. `app.js:48`: the refund selection is wrong.
   - Unchecking a box never removes the id, so a deselected order is still refunded.
   - Checking, unchecking and checking again pushes the id twice.
   - `selected` also persists across pages and reloads, so ids no longer on screen are still refunded.
   - On every render the checkboxes start unchecked while `selected` keeps the old ids. After paging back, the UI shows nothing selected but the refund still sends those ids.
7. `app.js:45`: `tb.innerHTML +=` inside the loop re-parses the whole table on every row. It is O(n²) but only 10 rows, so it is minor. The bigger problem is that `${o.customer.name}` and `${o.id}` are inserted unescaped. A customer named `<img src=x onerror=alert(1)>` runs script (stored XSS, with the API key in the page).
8. `api.js:6`: `query` and `status` go into the URL without `encodeURIComponent`. Searching `a&status=refunded` or `x#y` changes the query. A name like `O'Brien & Sons` breaks the filter.
9. `api.js:6-7` and `app.js:51-55`: there is no `res.ok` check and no try/catch. A 500 or an error JSON body such as `{error:..}` is assigned to `orders`, so `orders` is not an array. `for (const o of orders)` then throws, and the dashboard stays blank with only a console error.
10. `app.js:58`: `oninput = load` fires on every keystroke with no debounce and no cancellation. Responses can arrive out of order, so a slow response for "a" can overwrite the newer one for "ab". The table then shows results that don't match the search box.
11. `api.js:10-12` and `app.js:62-64`: `refund()` doesn't `await` the `fetch` and always returns `{ok:true}`. A 4xx or 5xx, or a network failure, still shows the "Refunded N orders!" toast (an unhandled rejection on failure). The order list is not reloaded after a refund. With an empty `selected`, it sends an empty refund request and toasts "Refunded 0 orders!". The README says refunds are confirmed before they are sent, but no confirm step exists. Because the code reports success, a customer can be told a refund went through when it didn't.
12. `app.js:64`: the toast is shown but never hidden. It also reads `selected.length` after the await, which could have changed in the meantime.

**Security**

13. `api.js:3`: the API key is hard-coded in client-side JS and sent from the browser. The README says "the API key never leaves the server", which is false. Anyone can read it from the page source.

**Accessibility and UI**

14. `index.html:85`: the refund control is a `<span>` with a click handler. It can't be focused or used from the keyboard and has no role.
15. `styles.css:19`: `outline: none` removes focus indicators on buttons, inputs and selects, with no replacement.
16. `styles.css:18`: Prev and Next buttons are `#aaa` on a white or cream background, at 12px with 2px/4px padding. That is far below 4.5:1 contrast and well below 44px touch targets. The `.lbl` text (`#aaa`, 11px) and the eyebrow (`#c7c2f0`, 11px on a purple gradient) fail contrast too.
17. `index.html:87,84`: the checkboxes, search box and select have no labels. The status dot is conveyed by colour alone (green/red/yellow), with no text alternative.
18. `styles.css:13`: the table is a fixed `width: 1000px`. It overflows and scrolls horizontally on mobile, which has no media queries. The three-column card grid does not collapse either.
19. `styles.css:20`: the toast has an infinite animation and no `prefers-reduced-motion` handling. It also has no `role="status"`.
20. `styles.css:15`: customer names are clipped at 120px with `overflow: hidden` and no ellipsis or title, so the clipped text can't be read.

**README claims that are false or unverifiable**

21. `README.md`: "Fully accessible / WCAG 2.1 AA, 44px targets": contradicted by items 14–17. Also, 2.5.5 is an AAA criterion, not AA. AA's target-size criterion is 2.5.8 in WCAG 2.2, at 24px.
22. `README.md`: "renders 10,000 orders instantly": `renderStats` loops over all orders and `renderTable` renders only 10, but the full list is fetched in one request on every keystroke. Nothing backs the claim.
23. `README.md`: pricing. 12 × $15 = $180 a month, or $2,160 a year; 20% off gives $1,728. $1,440 is wrong either way (it would be $120 a month, or 12 × $10 × 12).
24. `README.md`: "Refunds are confirmed before they are sent": false, see item 11.

I only read the code and did not run it. Items 1–6 and 13 follow directly from the source. Items 7–12 and 14–20 are what the code and CSS imply when run in a browser.