Line numbers below for `app.js` are the file's own (the listing above continued numbering across files: `api.js` 1–13, `app.js` 14–66 shown as 1–52 in-file offset of 14, `index.html` from 67).

**Bugs** (in-file line numbers):

1. **`api.js:6` – unencoded query string.** `q` and `status` are interpolated raw. Typing `a&status=refunded` or `bob#x` in the search box changes or truncates the request. A search for `O'Brien & Sons` sends `q=O'Brien & Sons`, so `q` is cut at `&` and the rest becomes a bogus parameter. Use `encodeURIComponent`.

2. **`api.js:7` – no `res.ok` check.** On a 401/500 the error JSON is returned as if it were orders. Then `app.js:24` (`for (const o of orders)`) throws "orders is not iterable" and the UI freezes on stale data.

3. **`api.js:11-12` – refund is fire-and-forget.** The `fetch` isn't awaited and its result is ignored, so `refund` always returns `{ok:true}`. With the network down or a 500 response, the toast still says "Refunded N orders!". A rejected promise also goes unhandled. It also has no confirmation step, though the README claims one.

4. **`api.js:3` – hardcoded secret in client code.** `API_KEY` ships to every browser, which contradicts the README's "key never leaves the server." Anyone can read it from DevTools.

5. **`app.js:40` – off-by-one paging.** `page` starts at 1 but `start = page * PAGE_SIZE`, so the first 10 orders are never shown. With 10 orders, page 1 is empty. The label says "Page 1" while showing rows 11–20.

6. **`app.js:47` – wrong page count.** `Math.floor(length / 10)` should be `Math.ceil`. With 25 orders it says "of 2" (3 pages needed). With 5 orders it says "Page 1 of 0".

7. **`app.js:60-61` – unbounded paging.** Prev/Next never clamp. Click Prev on page 1 and `page` becomes 0, then −1, and the table is empty with a "Page -1" label. Next runs past the end the same way.

8. **`app.js:58-59` – page not reset on new search or filter.** If you're on page 3 and type a query returning 5 results, the table is empty. Also, `oninput` fires a request per keystroke with no debounce or cancellation, so out-of-order responses can overwrite newer results with older ones.

9. **`app.js:31` – divide by zero.** An empty result gives `0/0` and the card shows `$NaN`. The status cards also compute from all orders, not the current page. That is probably intended, but it's inconsistent with the table.

10. **`app.js:26-29` – revenue logic.** Discount and tax are applied per order, but `revenue` is documented as "paid minus refunds." The refunded amount is also discounted and taxed again, and `total` is displayed raw in the table (`:45`, no discount or tax). So the table's totals don't sum to the Revenue card. Money is also summed with floating point (`0.9 * 1.0825`) instead of integer cents. Check this against the business rule. It may be intended, but it's inconsistent.

11. **`app.js:45` – XSS.** `o.customer.name` goes into `innerHTML` unescaped. A customer named `<img src=x onerror=alert(1)>` runs script. `o.id` and `o.status` are also injected unescaped into attributes and classes.

12. **`app.js:44-48` – quadratic re-render, and selection state lost.** `tb.innerHTML +=` inside the loop re-parses the whole body each iteration (contradicting "renders 10,000 orders instantly", though paging caps it at 10). Re-rendering also drops the checked state, but `selected` still holds the ids.

13. **`app.js:48` – selection tracking.** Only pushes on check, never removes on uncheck. Check order 5, uncheck it, click Refund: order 5 is still refunded. Checking, unchecking and rechecking gives duplicate ids. `selected` is never cleared after a refund, so a second click re-refunds the same orders, which is a double-refund risk. An empty selection still POSTs and shows "Refunded 0 orders!".

14. **`app.js:62-65` – no error handling.** If `refund` throws, nothing is shown. After success, the list isn't reloaded, so statuses stay stale.

15. **`index.html:85` – "Refund selected" is a `<span>`.** It isn't keyboard-focusable and has no role, so keyboard and screen-reader users can't refund. `styles.css:19` removes focus outlines everywhere, which fails WCAG 2.4.7.

16. **`index.html:84` – `<option>` values.** The "All" option has an empty value (fine), but the checkboxes (`:45`) have no label or aria-label, and the status column is a color-only dot (`.dot`, no text), which fails WCAG 1.4.1.

17. **`styles.css:13` – fixed `width: 1000px` table.** It overflows on any viewport under about 1050px, and the viewport meta is set, so this breaks on mobile.

18. **`styles.css:15` – `max-width` on a `td` is ignored in auto table layout.** Names aren't truncated as intended, and the table can stretch.

19. **README claims that are false against the code:**
    - "WCAG 2.1 AA, 44px targets": `button` is about 12px font with 2px 4px padding (`styles.css:18`), and `.dot` is 10px.
    - `.lbl` `#aaa` on white and `.eyebrow` `#c7c2f0` on the purple gradient are well under 4.5:1 contrast.
    - "Key never leaves the server": see #4.
    - "Refunds are confirmed": there is no confirmation anywhere.
    - "10,000 orders instantly": all orders are fetched with no server-side pagination, and revenue is recomputed on every keystroke.
    - **Pricing arithmetic:** 12 × $15 = $180 per month. Annual is 2,160, and 20% off gives $1,728, not $1,440 ($1,440 is only right if the seat price is $12.50). Either the seat price or the total is wrong.

20. **`styles.css:20` – toast animates forever** (`infinite alternate`) and is never hidden or dismissed. It has no `role="status"`, so it isn't announced, and it ignores `prefers-reduced-motion`.

I didn't run anything (static read only). Items 1–3, 5–9, 11 and 13 follow directly from the code. 10 and the pricing line in 19 depend on the intended business rules.