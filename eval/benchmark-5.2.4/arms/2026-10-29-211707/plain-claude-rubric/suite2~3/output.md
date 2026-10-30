I read all five files (`app.js`, `api.js`, `index.html`, `styles.css`, `README.md`) using `rubrics.md` and `sandbox.md` as the checklist. I changed no files. I traced the code by hand and ran nothing. The line numbers are from the files as read.

## Critical

1. **`api.js:3`: the API key is hardcoded in client code.** The Stripe-shaped key ships in `api.js` and is sent as `Authorization` from every browser. Open the page, look at the Network tab or `api.js`, and copy the key. `README.md:6` says "the API key never leaves the server", which is false. Rotate the key and move the calls behind a server.

2. **`app.js:32`: XSS through `o.customer.name`.** The name goes into `innerHTML` unescaped. A customer named `<img src=x onerror=alert(1)>` runs script in the dashboard for whoever views that page. `o.id` in `data-id` and `o.status` in `class` are unescaped too. Use `textContent` or escape every field.

3. **`api.js:11-12` with `app.js:49-52`: refund reports success without checking the result.** `refund()` doesn't `await` the `fetch` and always returns `{ok:true}`. Go offline, or have the server return 500, select an order and click Refund. The toast still says "Refunded 1 orders!" and the rejection is unhandled. Money is not refunded while the user is told it was. The fix is to `await` the fetch and return `res.ok`, with the error shown to the user.

4. **`app.js:35`: `selected` is never pruned, so unselected orders can be refunded.** The handler only does `selected.push` when the box is checked. Check order A, uncheck it, click Refund: `refund(["A"])` is sent. Checking A twice sends `["A","A"]`. `selected` also survives page changes and re-renders. After a refund it is not cleared, so a second click re-sends the same IDs. A wrong refund is a money-moved-wrongly case.

## High

5. **`app.js:27`: the first page of orders is unreachable.** `page` starts at 1 but `start = page * PAGE_SIZE`, so with 25 orders the first view shows orders 10–19. Orders 0–9 only appear after clicking Prev to page 0.

6. **`app.js:34`: the page count is wrong.** `Math.floor(orders.length / PAGE_SIZE)` gives 2 for 25 orders, so it reads "Page 1 of 2" when there are 3 pages. It gives "Page 1 of 0" for 5 orders.

7. **`app.js:47-48`: Prev and Next have no bounds.** Click Prev twice and `page` is -1, so the table is empty. Click Next past the end and the table is empty with no way to tell why. `load()` doesn't reset `page` either. Go to page 3, then type a search that returns 5 orders, and you get a blank table.

8. **`app.js:18`: "AVG ORDER" shows `$NaN` when there are no orders.** A search with no matches gives `0/0`. The divisor is also all orders, including pending ones, though revenue counts only paid and refunded.

9. **`api.js:6`: the query and status are not URL-encoded.** Search `a&status=refunded` or `x#` and the extra parameters change the request or the rest of the URL is cut off. Wrap both in `encodeURIComponent`.

10. **`api.js:7`: `res.ok` is never checked.** A 401 or 500 with a JSON body (`{error:..}`) becomes `orders`, and `renderStats` throws "orders is not iterable". Network failures reject out of `load()` unhandled. In both cases the UI shows stale data with no message.

11. **`app.js:45`: a request per keystroke, with no debounce and no stale-response guard.** Type "ab" quickly. If the "a" response arrives after the "ab" response, the table and stats show results for "a" while the box says "ab".

12. **`index.html:19`: the Refund control is a `<span>`.** It can't be focused or activated by keyboard and has no role. The main destructive action is unusable without a mouse (WCAG 2.1.1, level A). It is also missing a confirm step.

13. **`styles.css:19`: focus outlines removed** on button, input and select, with nothing to replace them (2.4.7, AA).

14. **`index.html:17-18`: the search input and the status select have no accessible name.** The input uses a placeholder as its label and the select has none (4.1.2 and 3.3.2). The row checkboxes at `app.js:32` are unlabelled, and `th` is empty at `index.html:21`.

15. **`app.js:32`, `styles.css:17`: status is shown only as a colour dot.** There is no text and no accessible name (1.4.1), so refunded and paid can't be told apart without colour.

16. **`styles.css:9`: contrast is too low.**
    - `.lbl` is `#aaa` on white, about 2.3:1.
    - `.eyebrow` is `#c7c2f0` on the purple gradient.
    - `button` text is `#aaa` at 12px.
    - All fail the 4.5:1 minimum (1.4.3, AA).

17. **`styles.css:13`: the table is a fixed `width:1000px`.** At 390px width the page scrolls sideways.

18. **`app.js:51`: the toast has no `aria-live` and is never hidden.** It also pulses forever (`styles.css:20`, `infinite`) with no `prefers-reduced-motion` handling. Screen-reader users get no announcement, and it covers the corner after a refund.

## Medium

19. **`app.js:8-17`: the pricing rules live in render code.** The 10% gold discount and 8.25% tax are computed in the view and applied to float totals with no rounding. Move them to one pure, tested function.

20. **`app.js:32`: `$${o.total}` is not formatted.** A total of 19.9 shows as `$19.9`.

21. **`app.js:49-52`: refund can be double-submitted.** There's no disabling during the request. It also sends an empty list, showing "Refunded 0 orders!" when nothing is selected. The orders and stats aren't reloaded after a refund, so refunded rows still show as paid.

22. **`app.js:32`: `tb.innerHTML +=` in a loop** rebuilds the table on each row. It's harmless at 10 rows, but it contradicts the 10,000-orders claim in the README.

23. **`styles.css:15`: customer names are clipped** at 120px with `overflow:hidden` and no ellipsis or `title`, so the full name can't be read.

## README claims that are false

- **`README.md:8`: the pricing arithmetic is wrong.** 12 seats × $15 × 12 months = $2,160. At 20% off that is $1,728, not $1,440.
- **`README.md:5`: two errors.** 2.5.5 (44px targets) is level AAA, not part of AA. The app also has 12px buttons and the AA failures above, so "fully accessible" is false.
- **`README.md:6`:** the key is in `api.js` (finding 1).
- **`README.md:9`:** "Refunds are confirmed" is false. Nothing asks for confirmation (finding 12).
- **`README.md:7`: the "10,000 orders instantly" claim is unmeasured.** The app fetches every order and loops over all of them on every keystroke, with no test or number behind the claim.