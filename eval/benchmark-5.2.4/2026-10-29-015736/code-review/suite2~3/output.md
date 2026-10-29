## Code review: `git diff main...HEAD` (1 commit, 5 new files)

I read the diff directly because it is small. There are no `CLAUDE.md` files in the repo, so there was nothing to check for compliance. I did not run the subagent validation pass. I confirmed each issue below by reading the code.

### Bugs

1. **Pagination skips the first page and mislabels the count.** `app.js` `renderTable` starts at `page * PAGE_SIZE`, but `page` starts at 1. The first 10 orders are never shown, and "Prev" never gets back to them. The label `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}` is also wrong. It rounds down, so 25 orders reads as 2 pages, and 5 orders reads as "Page 1 of 0".

2. **Refunds report success without checking the request.** In `api.js` `refund`, the `fetch` is not awaited and the function always returns `{ ok: true }`. The toast in `app.js` then says "Refunded N orders!" even if the request fails or is rejected, and even if nothing is selected. No confirmation step exists either, which contradicts the README line "Refunds are confirmed before they are sent."

3. **A secret key is hardcoded in client-side JS.** `api.js` defines `API_KEY` and sends it as a Bearer token from the browser. It is a placeholder here, but the pattern still exposes any real key to every visitor. This contradicts the README claim "the API key never leaves the server."

4. **Average order is NaN when there are no orders.** `renderStats` computes `revenue / orders.length`. A search or status filter with no matches shows `$NaN`.

5. **Stored XSS and query-string bugs.**
   - `renderTable` writes `o.customer.name` into `innerHTML` unescaped.
   - `getOrders` puts `query` and `status` into the URL without `encodeURIComponent`. A search containing `&` or `#` corrupts the request.

6. **The selection list is never cleaned up.** The `onchange` handler in `app.js` only pushes ids. Unchecking a box does not remove it, and re-rendering or paging leaves stale and duplicate ids. "Refund selected" can therefore refund orders the user unticked.

7. **The refund control is not keyboard accessible.** In `index.html`, `#refundBtn` is a `<span>` with no role, tabindex or key handler.

### README claims that the code contradicts

8. **The pricing arithmetic is wrong.** 12 seats × $15 × 12 months = $2,160. At 20% off that is $1,728, not $1,440.

9. **The accessibility claims are false.**
   - "Meets WCAG 2.1 AA, including 44 px touch targets": the Prev and Next buttons are 12px text with 2px padding.
   - `styles.css` removes the focus outline (`button:focus, input:focus, select:focus { outline: none; }`).
   - The `.lbl` text (#aaa on white) and the `.eyebrow` text (#c7c2f0 on the purple gradient) are too low in contrast.
   - The `.dot` status indicator uses colour alone.
   - Criterion 2.5.5 is also AAA, not AA.

10. **"Renders 10,000 orders instantly" is unsupported.** `renderTable` does `tb.innerHTML +=` in a loop, which is quadratic, and no benchmark backs the claim. It only renders 10 rows at a time, so the claim doesn't describe what the code does.

### Other defects

11. **The orders table is a fixed width.** `table { width: 1000px }` overflows on phones, even though the viewport meta tag is set.

12. **The customer name column silently clips.** `td:nth-child(2)` is `max-width: 120px; overflow: hidden` with no ellipsis.

**What Ryan needs to decide:** nothing blocking. Items 1–6 are code fixes. Items 8–10 mean either changing the README or fixing the code to match it.