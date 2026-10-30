Bugs found, grouped by severity. Nothing was run or changed. Each failure below comes from reading the code. I did not run it in a browser.

**Functional bugs**

1. `app.js:40` – the table starts on the wrong page. `page` starts at 1 and `start = page * PAGE_SIZE`, so the first view skips orders 0–9. Input: load 25 orders. The table shows orders 10–19 under "Page 1". The first 10 are never shown, and Prev goes to page 0 (the first 10 orders).
2. `app.js:60-61` – paging has no bounds. Prev and Next change `page` without clamping. Input: click Prev twice. `page` becomes -1, `slice(-10, 0)` returns `[]`, and the label reads "Page -1". Next past the end gives an empty table.
3. `app.js:47` – the page count is wrong. `Math.floor(length / 10)` should be `Math.ceil`, with a minimum of 1. Input: 25 orders shows "of 2" when there are 3 pages. Input: 5 orders shows "of 0".
4. `app.js:31` – with an empty result set, `revenue / orders.length` is `0/0`, so `NaN`. Input: search for "zzz". The average card shows "$NaN".
5. `app.js:28-29` – the revenue calculation is wrong in two ways.
   - Refunded orders are subtracted but never added, because only `paid` orders add. A refunded order is therefore a net negative. Input: one refunded order with a total of 100 gives revenue of -108.25.
   - The gold discount and tax are applied to the refund amount too.
   - Avg is also computed over all orders, including pending and refunded ones, which the "AVG ORDER" label doesn't suggest.
6. `app.js:48` – selection is broken in three ways.
   - Unchecking never removes the id.
   - Re-checking adds duplicates. Input: tick order A, untick it, tick it again. `selected = ["A","A"]` and it still refunds A.
   - `renderTable` rebuilds the DOM on every page change and filter, so checkboxes reset visually while `selected` keeps the stale ids. Input: tick A, click Next, click Refund. A is refunded though nothing is ticked.
7. `app.js:45-46` – `tb.innerHTML +=` inside the loop re-parses the whole table on every row. This is O(n²) and drops handlers. It contradicts the README's "instantly" claim.
8. `api.js:10-12` and `app.js:62-64` – refund reports success without checking the result.
   - `fetch` is not awaited and not error-checked, and the function always returns `{ok:true}`.
   - Input: the server returns 500 or the network is down. The toast still says "Refunded N orders!".
   - Input: nothing selected. A POST with `ids: []` is sent and the toast says "Refunded 0 orders!".
   - The README claims refunds are confirmed before sending, but no confirm step exists. One click on a `span` refunds immediately.
9. `api.js:6` – `query` and `status` are interpolated into the URL without `encodeURIComponent`. Input: search for `a&status=paid` or `x#y`. It injects a parameter or truncates the query. It also doesn't check `res.ok`, so a 4xx or 5xx error body reaches `orders.length` and `for (const o of orders)` and throws.
10. `app.js:51-58` – `load` fires on every keystroke with no debounce and no cancellation. Responses can arrive out of order, so a stale response can overwrite a newer one. Input: type "ab" quickly, and if the "a" response returns last, the table shows results for "a" while the box says "ab". `page` also isn't reset on a new search, so the user can be left on an empty page.
11. `app.js:45` and `app.js:33-35` – `o.customer.name` goes into `innerHTML` unescaped (stored XSS). Input: customer name `<img src=x onerror=alert(1)>`. `o.customer` being null also throws.

**Security**

12. `api.js:3` – a hardcoded API key in client-side JS. It is shipped to every browser. The README says "the API key never leaves the server", which is false.

**README claims that the code contradicts**

13. `README.md` WCAG and touch-target claims versus `styles.css` and `index.html`:
    - `styles.css:20` removes the focus outline on `button, input, select` with no replacement.
    - Buttons are about 20px tall (`padding: 2px 4px`, 12px font), well under 44px.
    - `.refund` is a `<span>` with a click handler, so it can't be reached by keyboard.
    - `.lbl` (#aaa on white) and `.eyebrow` (#c7c2f0 on the purple gradient) fail AA contrast.
    - The status is shown by colour alone, with no text, which fails WCAG 1.4.1.
    - The search input has no label.
    - The toast has no `aria-live`, and its infinite animation ignores `prefers-reduced-motion`.
14. `README.md` – "$15 per seat; 12 seats at 20% off is $1,440 a year" is wrong. 15 × 12 × 12 months = $2,160. At 20% off that is $1,728.
15. `styles.css:12` – `table { width: 1000px }` overflows the viewport on phones, giving horizontal scroll, even though `index.html` sets a viewport meta tag for mobile. `td:nth-child(2)` has `overflow: hidden` with no ellipsis, so long names are clipped silently.
16. `app.js:45` – the Total column prints `$${o.total}` with no `toFixed`, so it shows `$19.9` or `$20.000000001`. The stats cards do format.