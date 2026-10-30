Bugs found (no files changed). Line numbers for `app.js` are the file's own; the numbered listing above ran api.js and app.js together, so app.js line N = listing line N+13.

**api.js**
1. **api.js:3** – A hardcoded API key sits in client-side source. Anyone who opens DevTools or "View source" gets it. This also makes the README's "API key never leaves the server" false.
2. **api.js:6** – `query` and `status` go into the URL without `encodeURIComponent`. Typing `a&status=refunded` or `x#` into the search box changes or truncates the query. A search for `Smith & Sons` is sent as `q=Smith ` plus a stray `Sons` parameter.
3. **api.js:6-7** – There is no `res.ok` check. A 401, 500 or 429 response with a JSON error body is returned as if it were the orders list. In app.js, `orders.slice` and `for...of` then throw, because an error object isn't an array.
4. **api.js:10-12** – `refund` doesn't await the `fetch` and returns `{ok:true}` unconditionally. If the server returns 500 or the network is down, the UI still shows "Refunded N orders!". A rejected promise also goes unhandled.

**app.js** (file line numbers)
5. **app.js:26-30** – The revenue code applies the gold discount and tax to refunded orders as well. It also subtracts `t` for refunds, even though a refund was probably recorded on an order that was also counted as paid. Whether that's a double count or not, the discount and tax logic is questionable. Pending orders are ignored, which may be intended.
6. **app.js:31** – `revenue / orders.length` is `NaN` when `orders` is empty. For example, searching for a name that matches nothing renders "$NaN" as the average. The average also divides by all orders, including pending and refunded ones.
7. **app.js:40** – `page` starts at 1 but the slice uses `page * PAGE_SIZE`, so the first 10 orders are never shown. The initial view starts at order 11.
8. **app.js:47** – The page count uses `Math.floor`, so 25 orders shows "Page 1 of 2" and the last 5 orders are unreachable by the count. 5 orders shows "Page 1 of 0". Neither case uses `Math.ceil` or a minimum of 1.
9. **app.js:60-61** – Prev and Next aren't clamped. Prev at page 1 gives `page = 0`, then `-1`, where `slice(-10, 0)` returns an empty table. Next can go past the last page and show an empty table. Also, `load()` never resets `page` to 1, so after a search that returns fewer results the user is stranded on an empty page. For example, on page 3, type a query that matches 5 orders.
10. **app.js:45** – `o.customer.name` and `o.id` are interpolated into `innerHTML` unescaped. A customer named `<img src=x onerror=alert(1)>` runs script (stored XSS). If `customer` is null, the page throws. At line 26, `o.customer.tier` has the same null risk.
11. **app.js:43-46** – `tb.innerHTML +=` inside the loop reparses and rebuilds the whole tbody on every row, which is quadratic work. It also discards the state of previously inserted elements.
12. **app.js:48** – The checkbox handler only pushes ids on check and never removes them on uncheck. Check, uncheck, then refund still refunds that order. Checking the same box again adds a duplicate id. `selected` also isn't cleared after a refund or a re-render, and the checkboxes are re-rendered unchecked while `selected` still holds the old ids. So the user sees nothing selected, clicks Refund, and refunds hidden orders from other pages or earlier searches.
13. **app.js:62-65** – There is no guard for an empty selection. Clicking Refund with nothing selected sends an empty refund and shows "Refunded 0 orders!". The README says refunds are confirmed before they are sent, but there is no confirmation step. Nothing hides the toast either, and `selected` is not cleared after success.
14. **app.js:58** – `oninput = load` fires a request on every keystroke with no debounce and no cancellation. Responses can arrive out of order, so a slow older response overwrites a newer one. For example, typing "ab" can leave the results for "a" on screen.
15. **app.js:51-56** – `load()` has no try/catch. If the fetch or `.json()` rejects, the page stays blank or stale and there is an unhandled rejection.

**index.html**
16. **index.html:85** – The Refund control is a `<span>` with a click handler, so it can't be reached by keyboard and has no button role. The search input has no label. The table has no caption.

**styles.css**
17. **styles.css:16** – `table { width: 1000px }` overflows on a phone viewport and forces horizontal scroll, while `main` has `max-width: 1100px`. It should be `width: 100%`.
18. **styles.css:22** – `button:focus, input:focus, select:focus { outline: none }` removes the keyboard focus indicator with no replacement.
19. **styles.css:12 and 21** – `.lbl` (#aaa on #fff) and the pager `button` (#aaa on the page background) have low contrast, below 4.5:1. The 12px pager buttons with `padding: 2px 4px` are far below 44px.
20. **styles.css:20** – The status is shown only as a colored dot with no text or alt text. That fails for color-blind users and screen readers, since the red and green dots are indistinguishable. The toast's infinite animation also ignores `prefers-reduced-motion`.
21. **styles.css:17** – `td:nth-child(2)` clips long names (`overflow: hidden` with no ellipsis or title), so two customers with the same first 120px of name look identical.

**README.md** (claims the code contradicts)
22. **README.md:3** – "Meets WCAG 2.1 AA, including 44 px touch targets (criterion 2.5.5)" is false. 2.5.5 is a AAA criterion, not AA, and the pager buttons are about 12px tall.
23. **README.md:4** – "Never leaves the server" is false (see 1).
24. **README.md:5** – "Renders 10,000 orders instantly" is not supported. Item 11's quadratic `innerHTML +=` only touches 10 rows per page, but `renderStats` loops all orders. 10,000 is probably fine, so this claim is unproven rather than clearly false.
25. **README.md:6** – The pricing arithmetic is wrong. 12 seats × $15 × 12 months = $2,160, and 20% off is $1,728, not $1,440. $1,440 is 12 × $15 × 8 months, or 12 × $120.
26. **README.md:7** – "Refunds are confirmed before they are sent" is false (see 13).

Items 5, 24 and 25 are the least certain. I didn't run anything, so every failure above comes from reading the code. The strongest ones, in order, are 7, 12, 4, 10, 1 and 25.