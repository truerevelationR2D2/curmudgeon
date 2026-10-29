## Code review: `git diff main...HEAD` (commit f335fe5, new OrderDesk dashboard)

I found 9 high-signal issues. There are no `CLAUDE.md` files, so there is no compliance check. I read the diff myself and did not launch subagents, because the change is small and every issue can be confirmed from the diff text alone.

**Bugs**

1. **Pagination skips the first page.** `app.js` `renderTable`: `page` starts at 1, but `start = page * PAGE_SIZE` makes page 1 begin at index 10. Orders 0–9 can never be shown. The label `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}` is also wrong, because it should round up. Next/Prev have no bounds, so they can go past the last page or below 1.
2. **`refund()` always reports success.** `api.js`: the `fetch` isn't awaited and its result is never checked, so it returns `{ ok: true }` whatever the server says. `app.js` then shows "Refunded N orders!" even if the request failed or hasn't finished. This is a money-moving action. It also sends a refund with no confirmation, which contradicts the README line "Refunds are confirmed before they are sent."
3. **Selection state is wrong.** `app.js`: the `onchange` handler only pushes ids and never removes them on uncheck. Re-checking adds duplicates, and ticked boxes aren't restored after paging or reloading. So a refund can include orders the user unticked, or the same order twice.
4. **Empty result gives NaN.** `app.js` `renderStats`: `revenue / orders.length` divides by zero for an empty list and shows `$NaN` for AVG ORDER.
5. **XSS.** `app.js`: `o.customer.name` is written straight into `innerHTML` with no escaping. A customer named `<img onerror=…>` runs script in the dashboard, which holds the API key.
6. **Search parameters aren't URL-encoded.** `api.js`: `q=${query}` is not passed through `encodeURIComponent`. Input such as `a&status=refunded` or `#` changes the query.

**Security**

7. **API key is in the client.** `api.js` hard-codes `API_KEY` (a Stripe-key placeholder) in a script served to the browser and sends it as a bearer token. The README claims "the API key never leaves the server", and the code does the opposite. A real key here would be exposed to every visitor.

**README claims the code contradicts**

8. **The pricing example is wrong.** `README.md`: 12 seats × $15 × 12 months = $2,160, and 20% off gives $1,728, not $1,440. The README doesn't say whether $15 is monthly or annual. If it is annual, 12 seats at 20% off is $144. Neither reading gives $1,440.
9. **The accessibility claims are false.** The README says "meets WCAG 2.1 AA, including 44 px touch targets", but the code breaks this in several places:
   - **Focus outlines removed.** `styles.css` has `button:focus, input:focus, select:focus { outline: none; }`, which fails 2.4.7.
   - **Refund control isn't a control.** It is a `<span id="refundBtn">` with no role, tabindex or key handling, so keyboard users can't reach it.
   - **Targets are tiny.** Buttons are 12px text with 2px 4px padding, and checkboxes are default size.
   - **Contrast is too low.** `#aaa` on white or `#F4F1EA`, and `#c7c2f0` on the purple gradient, fall below 4.5:1.
   - **Status relies on colour alone.** The status dots carry no text.
   - **Toast has no live region.** It lacks `aria-live`.
   - **Animation can't be stopped.** The infinite toast animation ignores `prefers-reduced-motion`.

   "Renders 10,000 orders instantly" is also unsupported. `tb.innerHTML +=` inside the loop re-parses the table on every row, and `load()` re-renders on every keystroke with no debounce and no handling of out-of-order responses.

**Not flagged:** layout and style nits, such as the fixed `width: 1000px` table that overflows narrow screens.