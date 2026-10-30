I read both references, then all five files (`app.js`, `api.js`, `index.html`, `styles.css`, `README.md`). I changed nothing and ran nothing. These are traced from the code, not driven, and I assumed `getOrders` returns an array of `{id, total, status, customer:{name,tier}}`.

## Critical / High

1. **`api.js:11-12`: refund is reported as success whether or not it worked.**
   - `fetch` is neither awaited nor checked, and the function always returns `{ok:true}`.
   - Fail it by going offline (or getting a 500) and clicking Refund. `app.js:51` shows "Refunded N orders!" and no refund happened.
   - Also, `refund()` returns before the request completes, and nothing re-fetches orders afterwards.

2. **`api.js:3`: an API credential sits in client code that ships to the browser.**
   - Anyone can read it with View Source, and the app sends it in an `Authorization` header from the browser.
   - The README's "API key never leaves the server" (line 6) is false.

3. **`app.js:32`: stored XSS from the customer name.**
   - `o.customer.name` goes into `innerHTML` unescaped.
   - Fail it with a customer named `<img src=x onerror=alert(1)>`. It runs on every page load.
   - `o.id` goes unescaped into the `data-id` attribute too.

4. **`app.js:27`: pagination skips the first page of orders.**
   - `page` starts at 1, so `start = 1*10 = 10`. With 25 orders the first view shows orders 11–20, and orders 1–10 are only reachable by pressing Prev to page 0.
   - Prev has no lower bound and Next has no upper bound. Prev below 0 gives a negative `start`, so `slice(-10, 0)` is empty and the table goes blank.
   - Fail it with 5 orders: the table is empty on load.

5. **`app.js:35`: the `selected` list is wrong, and refunds the wrong orders.**
   - It only ever adds. Unchecking never removes the id, and checking again pushes a duplicate.
   - Re-rendering (paging, search) drops the checkbox state, but `selected` keeps the old ids. The screen shows nothing ticked while ids from earlier pages and filters remain.
   - It is never cleared after a refund.
   - Fail it by ticking order 5, unticking it, then pressing Refund. Order 5 is refunded anyway.
   - Fail it with nothing selected: `refund([])` runs and the toast says "Refunded 0 orders!".

6. **`app.js:45` with `api.js:6`: the query string is not encoded, so search is wrong.**
   - Typing `a&status=refunded` or `x#` changes the request the server sees.
   - Fail it by searching for `AT&T`, which sends `q=AT&T`.

7. **`app.js:45` and `app.js:38-43`: out-of-order responses and no error handling.**
   - There is no debounce, abort or sequence check. Typing "ab" fires two requests. If the "a" response arrives after the "ab" response, the table shows results for "a".
   - `res.ok` is never checked. A 500 with a JSON error body makes `orders` a non-array, and `for…of` throws.
   - A network failure is an unhandled rejection, and the screen stays stale with no message.

8. **`app.js:11-22`: the revenue and stats calculation has two defects.**
   - `avg = revenue / orders.length` gives `$NaN` for an empty list, which also happens on first run or with a filter that matches nothing.
   - Money is computed in floats with `toFixed`.
   - Pricing rules (tax 8.25%, gold 10% discount) live in the render function. This is a domain leak, and the same rule is not applied to the `$${o.total}` shown in the table at line 32. The table shows the raw total, so it disagrees with revenue.
   - Also, `o.customer.tier` throws if `customer` is missing on an old record.

9. **`app.js:34`: the page label is wrong.**
   - `Math.floor(n/10)` undercounts the pages. 25 orders gives "Page 1 of 2" but there are 3 pages, and 5 orders gives "of 0".
   - Search or filter changes never reset `page`. Go to page 3, search, and you see an empty page.

## Medium

10. **`app.js:32`: `tb.innerHTML +=` in a loop** re-parses the whole body on every row, so the cost is quadratic. This undercuts the README's "10,000 orders instantly" claim. The page slices to 10 rows, so the table is not the cliff. The stats loop is one pass per keystroke.

11. **`index.html:19`: the Refund control is a `<span>`.** It cannot be focused or activated by keyboard and has no role. A keyboard user cannot refund at all (WCAG 2.1.1, level A).

12. **`styles.css:19`: `outline:none` on button, input and select removes the focus indicator** (WCAG 2.4.7).

13. **`styles.css:13`: the table has a fixed `width:1000px`**, so at 390 px or 200% zoom the page scrolls sideways.

14. **Contrast failures.**
    - `.lbl` (`#aaa` on white) is about 2.3:1.
    - `.eyebrow` (`#c7c2f0` on `#6366f1`) is about 3.3:1 at 11 px.
    - Pager buttons (`#aaa` on `#F4F1EA`) are low as well.
    - All fall below the 4.5:1 minimum.

15. **Status is conveyed by colour only** (`app.js:32`, `styles.css:17`). The dot has no text or label.

16. **Missing labels and announcements.**
    - The row checkboxes have no label, and the search input has only a placeholder.
    - The toast has no `aria-live` and never hides.
    - It pulses forever with no `prefers-reduced-motion` handling (`styles.css:20`).

17. **`styles.css:15`: customer names are clipped.** `max-width:120px` with `overflow:hidden` and no ellipsis or title cuts names off silently.

## README claims that the code contradicts (`README.md`)

18. **Line 5:** "WCAG 2.1 AA including 44 px targets (2.5.5)" is wrong on two counts.
    - 2.5.5 is **AAA** in 2.1.
    - The controls fail even the claim: pager buttons are about 12 px text with 2–4 px padding.
    - Findings 11–14 are further AA failures.

19. **Line 8: the pricing arithmetic is wrong.** 12 seats × $15 × 12 months = $2,160. At 20% off that is **$1,728**, not $1,440.

20. **Line 9:** "Refunds are confirmed before they are sent" is false. `app.js:49-52` sends immediately with no confirm step.

## Nits
- `app.js:51` builds the toast text with the exclamation mark and "orders" even for 1 order.
- The `selected` and `page` globals are shared, mutable state.

For scenario 11 (tests of the tests): there are no tests in the repo, so none to break.