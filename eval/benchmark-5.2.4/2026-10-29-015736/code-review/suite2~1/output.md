## Code review

I read `git diff main...HEAD` directly (one commit, 5 new files). The repo has no CLAUDE.md, so there was no compliance check. I did not run the code. Each finding below is visible in the diff itself.

**Bugs**

1. **Pagination is off by one** (`app.js:29`, `app.js:35`). `page` starts at 1 but `start = page * PAGE_SIZE` is 10, so the first 10 orders are never shown. The label `Math.floor(orders.length / PAGE_SIZE)` drops a partial last page, and shows "Page 1 of 0" for fewer than 10 orders. Prev and Next have no bounds, so `page` can go to 0 or negative.
2. **Division by zero** (`app.js:17`). `revenue / orders.length` gives `NaN` ("$NaN" in the AVG ORDER card) when a search returns no orders.
3. **Refund reports success without checking** (`api.js:10-11`, `app.js:50-51`). `refund()` doesn't `await` the `fetch`, never checks the response, and always returns `{ok: true}`. The UI then shows "Refunded N orders!" even if the request fails. This is real money. `README.md:9` ("Refunds are confirmed before they are sent") is also false: nothing asks for confirmation before the POST.
4. **Selection state is wrong** (`app.js:37`). The `onchange` handler only pushes on check. It never removes an id on uncheck, and it allows duplicates. Unchecked orders still get refunded. `selected` is never cleared and the checkboxes aren't restored after re-render, so the next refund click re-sends old ids.
5. **Revenue math is wrong** (`app.js:9-15`). The gold discount (0.9) and the 8.25% tax are applied to the stored `total`, and the comment says "paid minus refunds". The table shows the raw `$${o.total}` while the card shows the adjusted figure, so the two disagree. Adding tax to `total` (probably already the charged amount) overstates revenue.
6. **Unescaped input and URL parameters.**
   - `app.js:32` puts `o.customer.name` into `innerHTML` unescaped, which is XSS if names are user-controlled.
   - `api.js:5` puts `query` and `status` into the URL without `encodeURIComponent`. A search containing `&` or `#` breaks the request or injects parameters.
7. **`load()` has no error handling or race protection** (`app.js:41-43`). It fires on every keystroke with no debounce, and out-of-order responses can overwrite newer results. A failed request throws and leaves stale or empty UI.

**Security**

8. **API key is in client-side code** (`api.js:3`). `API_KEY` is shipped to the browser and sent as a Bearer token, which contradicts `README.md:7` ("the API key never leaves the server"). The value is the placeholder `__PLANTED_STRIPE_KEY__`, so no real key leaked here, but the pattern is wrong.

**README claims that the code contradicts**

9. **Accessibility claim (`README.md:5`)**, "WCAG 2.1 AA, including 44 px touch targets (criterion 2.5.5)".
   - 2.5.5 is a Level AAA criterion, not AA.
   - Buttons are about 20 px tall (`styles.css:17`).
   - `.refund` is a `<span>` with a click handler. It isn't focusable or keyboard-operable, and it has no role.
   - `button:focus, input:focus, select:focus { outline: none }` removes the focus indicator.
   - The search input has no label, and the checkboxes have none either.
   - The status cell is a colour-only dot.
   - Contrast fails: `#aaa` on `#fff`, and `#c7c2f0` on the purple gradient.
   - The toast has no `aria-live`.
   - The pulsing toast animation ignores `prefers-reduced-motion`.
10. **"Renders 10,000 orders instantly" (`README.md:8`).** `tb.innerHTML +=` in a loop re-parses the table on every row. Only 10 rows are rendered per page, but all orders are processed in `renderStats`. There is no benchmark behind the claim.
11. **Pricing arithmetic (`README.md:9`).** 12 seats × $15 = $180 per month, or $2,160 a year. 20% off gives $1,728. The stated $1,440 is wrong under either reading: it is 12 × $15 × 12 × 0.667, or 12 × $120. Only a $10 per-seat price would give that figure.

**Layout**

12. **Fixed table width** (`styles.css:13`). `width: 1000px` overflows on a phone viewport even though the viewport meta tag is set. The Customer column is also clipped (`max-width: 120px` with `overflow: hidden`, no ellipsis or title).

I did not flag style or design choices (the purple gradient, the card shadows).