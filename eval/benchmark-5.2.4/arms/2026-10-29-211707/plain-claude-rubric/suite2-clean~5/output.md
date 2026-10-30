I read all six files, using `rubrics.md` and `sandbox.md` as the checklist. This is a UI payload, so I ran scenarios 0–10 by reading the code. I did not run the app (no running server or Playwright). Every finding below is traced from the code, not driven. I changed no files.

## Findings

1. **High: a refund that succeeded can be reported as failed, and the retry uses a fresh key.** This is at `api.js:16-20`, with `app.js:128` and `app.js:131-133`.
   - **What is wrong:** `request()` always calls `res.json()`. A refund endpoint that answers `200` or `204` with an empty body makes this throw, so it becomes `ApiError("…not valid JSON")`. `refundSelected` then shows "The refund was not confirmed… before trying again", even though the money has been sent.
   - **What makes it worse:** `newIdempotencyKey()` runs on every click (`app.js:128`). A retry therefore gets a new key, so the server's duplicate protection never applies. The same happens when the network drops after the server has processed the request (`api.js:13`).
   - **Failing sequence:**
     1. Select order 5 and click Refund. The server refunds it and replies `204`.
     2. The UI says the refund failed and tells the user to try again.
     3. The user clicks Refund again, which sends a new `Idempotency-Key`. The refund is paid twice.

2. **High: orders that are already refunded or still pending can be selected and refunded.** This is at `app.js:39-44`, `app.js:75-77` and `app.js:120-128`.
   - **What is wrong:** Every row has a checkbox. Nothing checks `order.status`, so the client never limits refunds to `paid` orders. The confirm dialog also adds up the totals of refunded orders.
   - **Failing sequence:** Filter to "refunded", tick a row and click Refund. The dialog says "Refund 1 order totalling $X? This sends money back". Confirm it, and the refund request goes out for an order that was already refunded. If the server doesn't enforce the status check, that is a second payout, and the fresh key from finding 1 doesn't help.

3. **Medium: a missing or null `total` is shown as a valid $0.00 order.** This is at `domain.js:11-12`.
   - **What is wrong:** `Number(raw.total)` is finite for `null`, `""`, `[]`, `false` and `true`, so the `Number.isFinite` guard doesn't reject them. The comment on `normaliseOrder` promises that records with "no numeric total" are dropped.
   - **Failing input:** `{"id":"7","total":null,"status":"paid"}` becomes `total: 0`, shows as `$0.00`, can be selected for refund and is counted in the "Orders" total. It is not counted in `skipped`, so the "incomplete data" note never appears.
   - **Also:** `total: true` becomes `$1.00`.

4. **Medium: ticked orders stay selected when you change page, so the refund count includes rows you can't see.** This is at `app.js:145-146`, `app.js:82` and `app.js:120`.
   - **What is wrong:** `state.selected` is only cleared in `load()`. `prev` and `next` leave it alone.
   - **Failing sequence:** Tick 3 rows on page 1, then go to page 2. The button reads "Refund 3 orders", and the user sees no ticked boxes on that page. Clicking it sends all 3 hidden orders. The confirm dialog shows only a count and a total, not which orders.

5. **Medium: a failed reload leaves stale data on screen and the old selection in place.** This is at `app.js:105-108` and `app.js:98`.
   - **What is wrong:** The `catch` path never clears `state.orders`, `state.selected` or the stats.
   - **Failing sequence:** After a successful refund, `await load()` fails with a 500. The toast says "Refunded", but the table still shows the refunded orders as `paid` with their boxes ticked (`state.selected` was never cleared). The refund button is enabled again, so a second click refunds the same orders under a new key.

## Not findings, and what I could not check
- The README's pricing arithmetic is correct: 12 × 15 × 12 = 2160, and 2160 × 0.8 = 1728.
- The README's WCAG notes are also correct: 2.5.5 is AAA in 2.1, and 2.5.8 is AA in 2.2.
- I did not check the claims about axe-core results and the 10,000-order render time, because I couldn't run them.
- The debounced search captures the input value when the timer fires, and `latestRequest` correctly discards stale responses. I found no race there.
- Nit: `.table-wrap` (`overflow-x: auto`) is not keyboard-focusable. This only matters when the table overflows at narrow widths. I did not verify it in a browser.