I read `rubrics.md` and `sandbox.md` first, then traced the five files by hand. Nothing was run or edited. Line numbers are per file. This is a UI payload, so I applied sandbox scenarios 0–10 by tracing, not driving.

## Critical

1. **`api.js:3`: API key shipped in client code.** `API_KEY` sits in a script served to every browser and goes out as `Authorization: Bearer` from `api.js:6` and `api.js:11`.
   - Failing input: open DevTools → Sources → `api.js`, or view the page source. The key is readable.
   - README line 6 ("the API key never leaves the server") is false, since the key is in the page.
   - Fix: rotate the key and move the calls behind a server.

2. **`api.js:10–13`: `refund()` reports success without checking the request.** The `fetch` is not awaited and its status is never read. The function returns `{ ok: true }` at once.
   - Failing sequence: select an order, click Refund while offline, or against a 500 or 403. The toast still says "Refunded 1 orders!" (`app.js:51`), and no refund happened.
   - A rejected promise is also unhandled.

3. **`app.js:35` together with `app.js:49–51`: the selection is wrong in two ways.**
   - Unchecking a box never removes the id (`if (c.checked) selected.push`).
   - Checking the same box twice, or re-checking after a re-render, pushes duplicates.
   - `renderTable` rebuilds the checkboxes unchecked but keeps `selected`, so ticked-looking state and the real list drift apart.
   - Failing sequence: check order 5, uncheck it, click Refund. Order 5 is refunded anyway. Checking A, going to the next page and back also leaves A in the list while its box shows unchecked. Both are wrong refunds, which is money moved wrongly.
   - `selected` is also never cleared after a refund, so a second click refunds the same ids again.

4. **`index.html:19`: the Refund control is a `<span>`.** There is also no confirmation step.
   - A span can't be reached or activated by keyboard, and has no role or name. This is a WCAG 2.1.1 (A) failure on the main destructive action.
   - README line 9 ("Refunds are confirmed before they are sent") is false: one click sends the request.

5. **`app.js:32`: stored XSS from `o.customer.name`.** It is interpolated unescaped into `innerHTML`; `o.id` at the same spot is also unescaped inside an attribute.
   - Failing input: a customer named `<img src=x onerror=alert(1)>` runs script in the dashboard. Combined with finding 1, the script can read the key.

6. **`api.js:6`: query and status are put into the URL unencoded.**
   - Failing input: typing `a&status=refunded#` in the search box changes the request parameters.
   - A name such as `Tom & Jerry` truncates the query. This is the hostile input from sandbox scenario 10.

## High

7. **`app.js:27`: pagination is off by one.** `start = page * PAGE_SIZE` with `page` starting at 1 means page 1 shows rows 10–19, so the first 10 orders are never shown.
   - Failing input: load 25 orders. Page 1 shows orders 11–20.

8. **`app.js:34`: the page count is wrong.** `Math.floor(orders.length / PAGE_SIZE)` is used instead of `ceil`.
   - Failing input: 25 orders shows "Page 1 of 2" when there are 3 pages. 5 orders shows "Page 1 of 0".

9. **`app.js:45–46` and `app.js:38–42`: paging and stale responses.**
   - `prev` and `next` are unbounded. Prev at page 1 gives page 0 with `start = 0`, and page −1 gives `slice(-10, 0)`, an empty table. Next past the end shows an empty table.
   - `load()` runs on every keystroke with no debounce and no stale-response guard. If the response for "ab" arrives after the one for "abc", the older results overwrite the newer ones.
   - `page` is not reset when the filter changes, so a search can leave you on an empty page.

10. **`app.js:11–18`: the revenue arithmetic and its domain logic are wrong.**
    - The 8.25% tax and the gold discount sit inside render code (the rubric's "domain leak").
    - Tax is added on top of `o.total`, but the table shows `o.total` untaxed, so the two figures disagree.
    - Failing input: `orders = []` gives `avg = 0/0 = NaN`, shown as `$NaN`. The empty state is not handled.
    - A failed `load()` fails with no message. A non-array response, such as an error JSON, makes `orders.slice` throw.

11. **`app.js:32` (also line 5 in `api.js`): `innerHTML +=` inside a loop.** Each row re-parses the whole table body, which is O(n²) per render. The README's "renders 10,000 orders instantly" is unproven, and the page size is capped at 10 anyway. `renderStats` is also recomputed on every keystroke.

12. **`styles.css:19` and `styles.css:18`: focus outlines are removed.** `outline: none` on `button`, `input` and `select` leaves no replacement focus style. The Prev/Next buttons are `#aaa` on `#F4F1EA`, a contrast of roughly 2:1, under the 4.5:1 AA threshold.

13. **`styles.css:4` and `styles.css:9`: low-contrast text.** `.eyebrow` is `#c7c2f0` on a purple gradient and `.lbl` is `#aaa` on white (about 2.3:1). Both are WCAG AA failures.

14. **`styles.css:13`: `table { width: 1000px }`.** At 390 px width, or at 200% zoom, the page scrolls sideways. This fails WCAG 1.4.10 and sandbox scenario 9.

15. **Missing states and labels.**
    - `index.html:17`: the search input has only a placeholder, with no label. `index.html:21`: the first `<th>` is empty and the checkboxes have no accessible name.
    - `styles.css:15`: the toast is shown with `display: block`, not an `aria-live` region, so it isn't announced.
    - The status column is a coloured dot only, with no text, so colour is the sole signal (1.4.1).

## Medium

16. **`app.js:51`: the toast text and behaviour.**
    - "Refunded 1 orders!" is wrong for a count of 1, and the exclamation mark confirms an unverified action.
    - The toast never hides.
    - `styles.css:20` makes it pulse forever (`animation: ... infinite`), with no `prefers-reduced-motion` guard. This fails 2.3.3 AAA and is bad practice.

17. **`styles.css:14`: truncated names.** `td:nth-child(2)` has `max-width: 120px; overflow: hidden` with no ellipsis or title, so long names are clipped silently.

18. **`app.js:34` and `app.js:32`: `o.total` is shown raw.** `$${o.total}` has no formatting (`$12.5`), and the number is unformatted in the stats too.

## README claims that don't match the code

- Line 5: "meets WCAG 2.1 AA, including 44 px touch targets (criterion 2.5.5)". That is wrong twice. 2.5.5 is AAA in 2.1, not AA. The code also fails AA outright (findings 4, 12–15), and the buttons are about 12 px text with 2 px padding.
- Line 8: 12 seats × $15 = $180 a month, or $2,160 a year. With 20% off that is $1,728, not $1,440. $1,440 is neither of those, so the figure is wrong.
- Line 6 and line 9 are false (findings 1 and 4).
- Line 7 is unmeasured.

## Not done
I did not drive the page with `browse.py` or Playwright. Every finding above is traced from the source, not run in a browser. The `lenses.md` scripted lenses were not applied because that file wasn't in your brief.