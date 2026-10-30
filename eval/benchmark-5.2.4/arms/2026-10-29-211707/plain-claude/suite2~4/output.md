Bugs found (no files changed). Line numbers are per file (api.js, app.js, index.html, styles.css, README.md each start at 1).

**Functional bugs**

1. **app.js:40: page indexing is off by one.** `page` starts at 1, but `start = page * PAGE_SIZE`. Load 25 orders and the first view shows rows 10–19, so orders 0–9 are never shown. Prev goes to page 0, which shows rows 0–9 but is labelled "Page 0".
2. **app.js:47: wrong page count.** `Math.floor(orders.length / PAGE_SIZE)` should be `Math.ceil`, with a minimum of 1. With 25 orders it says "Page 1 of 2" and the last 5 are unreachable. With 5 orders it says "Page 1 of 0".
3. **app.js:60-61: no bounds on the pager.** Prev and Next never clamp. Click Prev twice and `page` is -1, so `slice(-10, 0)` returns an empty table. Next past the end gives an empty table.
4. **app.js:58, 54: `page` isn't reset when the search or filter changes.** Go to page 3, type in the search box, and the new, shorter result list renders from page 3 and looks empty.
5. **app.js:31: division by zero.** With zero orders (a search with no matches), `avg = 0/0 = NaN`, so the card shows "$NaN".
6. **app.js:26-29: revenue calculation is wrong.**
   - Adding 8.25% tax to revenue is dubious.
   - Refunded orders are subtracted. If a refunded order is also counted as paid elsewhere, that's fine, but a refunded order that was never counted as paid pushes revenue negative.
   - A refunded order with `total: 100` shows revenue as -$108.25.
7. **app.js:48: `selected` handling is broken.** Checking pushes the id, but unchecking never removes it, and re-checking adds a duplicate.
   - Check A, uncheck A, click Refund: A is still refunded.
   - Check A twice: `selected = ["A","A"]`.
8. **app.js:45, 48: selections are lost on re-render.** `tb.innerHTML +=` rebuilds the whole tbody on every row, which is O(n²) and recreates the nodes. The new checkboxes are never re-checked from `selected`. Select a row, go to Next, then Prev: the box shows unchecked but the id is still in `selected`, so a hidden refund happens.
9. **api.js:11-12: `refund` doesn't await the fetch.** It returns `{ok:true}` immediately, so the success toast shows even if the request fails (network error, 4xx or 5xx). The promise rejection is also unhandled. Refund with the API down: the toast still says "Refunded N orders!".
10. **api.js:5-7: no `res.ok` check.** On a 401 or 500 whose body is a JSON error object, `orders` becomes an object. `for (const o of orders)` then throws "orders is not iterable", and the UI breaks.
11. **api.js:6: query values aren't URL-encoded.** Searching `a&status=paid` or `O'Brien & Sons` corrupts the query string. Use `encodeURIComponent`.
12. **app.js:58: `oninput = load` fires on every keystroke with no debounce, and responses can arrive out of order.** A slow earlier response overwrites a newer one, so the table shows results for a stale query.
13. **app.js:62-65: Refund with nothing selected still sends a request.** It posts `ids: []` and shows "Refunded 0 orders!". `selected` is also never cleared after a refund, so a second click refunds the same ids again. The orders aren't reloaded either, so statuses stay stale.
14. **README.md:9 says "Refunds are confirmed before they are sent", but app.js:62-65 has no confirmation step.** The refund fires immediately.

**Security**

15. **app.js:45: XSS.** `o.customer.name` is interpolated into `innerHTML` unescaped. A customer named `<img src=x onerror=alert(1)>` runs script. `o.id` in the `data-id` attribute is also unescaped, so an id containing `"` breaks out of the attribute.
16. **api.js:3, 6, 11: the API key is shipped in client JS and sent from the browser.** Anyone can read it in View Source. README.md:6 claims "the API key never leaves the server", which is false. Even though the value is a placeholder, the pattern is wrong.
17. **api.js:11 and app.js:62: a state-changing refund call has no CSRF or user-auth protection.** It relies on a shared bearer token embedded in the page.

**Accessibility and CSS (the README claims WCAG 2.1 AA)**

18. **index.html:85: the "Refund selected" control is a `<span>` with a click handler.** It can't be reached by keyboard and has no role, so keyboard-only users can't refund.
19. **styles.css:28: `outline: none` on button, input and select focus** removes the visible focus indicator (WCAG 2.4.7).
20. **styles.css:18, 27, 13: low contrast.** `#aaa` on white is about 2.3:1 (the 4.5:1 minimum applies). Button text `#aaa` on the page background is similar. `.eyebrow` `#c7c2f0` on the purple gradient is also low.
21. **styles.css:25-26 and app.js:45: status is conveyed by colour alone.** The `<span class="dot">` has no text, so it's invisible to screen readers and colour-blind users. Paid, refunded and pending are only red, green and yellow.
22. **styles.css:27: touch targets.** Buttons have 2px 4px padding and 12px font, far below the 44 px the README claims (README.md:5). Checkboxes and rows are also small.
23. **styles.css:29: infinite pulsing toast animation** with no `prefers-reduced-motion` guard (WCAG 2.3.3). The toast also has no `role="status"` or `aria-live` (index.html:89), so screen readers never announce it. It never hides either, because nothing sets `display:none` again.
24. **index.html:83: the search input has no `<label>`** (only a placeholder), and neither does the `<select>` (lines 83-84). The checkboxes (app.js:45) have no accessible name either.

**Layout**

25. **styles.css:22: `table { width: 1000px }` is fixed.** It overflows on small screens, even though main is `max-width: 1100px` and there's a viewport meta tag. At 375px width, the table forces horizontal scroll.
26. **styles.css:24: `td:nth-child(2)` has `max-width:120px; overflow:hidden` with no `text-overflow`.** Customer names are silently clipped with no ellipsis or title.
27. **styles.css:15: the 3-column stats grid has no responsive fallback.**

**Unsupported README claims (README.md)**

- **Line 7, "renders 10,000 orders instantly".** The code is O(n²) because of `innerHTML +=` and the revenue loop. It also paginates only after fetching everything. This is untested and unsupported.
- **Line 8, pricing.** 12 seats × $15 = $180 a month, so $2,160 a year, and 20% off gives $1,728. $1,440 is wrong. $1,440 would be $15 × 12 × 12 × 0.667, or no discount. The correct annual figure is $1,728.

I haven't run the code; these come from reading it. Items 1–5, 7, 9 and 15 are the clearest failures with a concrete input.