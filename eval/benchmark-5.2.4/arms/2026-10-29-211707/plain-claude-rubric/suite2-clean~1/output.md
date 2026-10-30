I traced the code against the two checklists (code rubric, and sandbox scenarios 1–7 and 10 for an interface-less run). Nothing was run, because there is no test harness and I was told to change no files. All findings below are **traced, not driven**. I changed no files.

## Findings, highest impact first

**1. High: a retried refund gets a new idempotency key, so it can pay twice.** `app.js:180` (`newIdempotencyKey()` is called inside every click), `app.js:183-185`.
- **Sequence:** The user selects order 42 and confirms. The server issues the refund, but the response is lost (network drop, proxy timeout, or a 502 after the work was done).
- **What happens:** The catch shows "refund was not confirmed". The selection is kept and the Refund button is re-enabled. The user clicks again and a fresh UUID is generated, so the server's `Idempotency-Key` protection (README line 9) cannot recognise the retry. Order 42 is refunded twice.
- **Why it matters:** The key exists to dedupe exactly this retry, but it is created per click, not per attempt. The "check statuses first" wording does not stop the second click.

**2. High: refund success is reported but the table can stay stale, inviting a second refund.** `app.js:181-182`, `app.js:157-160`.
- **Sequence:** The refund succeeds and the toast says "Refunded 1 order." Then `load()` fails, for example with a 500 or a dropped connection.
- **What happens:** `load()` catches the error and returns normally. `state.orders` and `state.selected` are not touched, so the old rows still show "paid" with the box ticked. The error line is `role=status` text under the toolbar, while the toast says success.
- **Result:** The refunded order still looks refundable and selected, and clicking Refund again sends a new key (see 1).

**3. High: already-refunded and pending orders can be refunded.** `app.js:93-96`, `app.js:127-136`, `app.js:171-175`.
- **Sequence:** Filter to "refunded", tick a row and click Refund.
- **What happens:** Nothing checks `order.status`. The confirm dialog adds up `o.total` and sends the ids.
- **Result:** Refunding a refunded order depends entirely on the server. The same applies to "pending" and "unknown" status. Domain code treats these as zero revenue, so the UI contradicts it.

**4. High: a missing or null total becomes a valid $0.00 order, and `[]` and `""` do too.** `domain.js:211-212`.
- **Input:** `{"id":"7","total":null,"customer":{...}}`, or `"total":""`, or `"total":[]`.
- **What happens:** `Number(null)`, `Number("")` and `Number([])` all give `0`, which is finite, so the record passes. The README and comment at `domain.js:207` say records with no numeric total are skipped and counted in "could not be shown".
- **Result:** The row shows $0.00, and `Number(true)` gives 1. The incomplete-data warning never appears, so bad data is shown as a real value.
- **Related:** Negative totals pass too. In `orderRevenueCents`, `Math.round` of a negative half rounds the wrong way for "half up".

**5. Medium: a 204 or empty-body success is reported as a failed refund.** `api.js:29-33`, called from `app.js:180`.
- **Input:** A server that answers `POST /refunds` with 200/204 and no body.
- **What happens:** `res.json()` throws, so `request` throws "not valid JSON".
- **Result:** The money has moved, but the UI says "The refund was not confirmed" and skips the reload. Combined with 1, this invites a duplicate. The refund path should not require a JSON body.

**6. Medium: money rounding uses `Math.round(order.total * 100)`.** `domain.js:227`.
- **Input:** `total: 1.005` gives `100.49999999999999`, which rounds to 100 cents, not 101. `0.285` gives 28, not 29.
- **Result:** This contradicts the comment "rounded half up" and the basis-point goal of avoiding binary-fraction drift. It only bites on totals with fractional cents.

**7. Medium: the stats mix pending and refunded orders into the average.** `domain.js:233-235`.
- **Input:** Orders: one paid at $100.00 (standard tier) and one pending at $100.00.
- **What happens:** Revenue is $108.25 and the count is 2, so "Average per order" is $54.13.
- **Result:** Pending and refunded orders contribute $0 but are divided in. Either label it "per listed order" or divide by paid orders. Separately, the "Revenue" stat applies gold discount and 8.25% tax on top of `order.total`. If `total` is already the charged amount, revenue is overstated or understated. That is an unconfirmed domain question for Ryan.

**8. Low: stale stats and table after a failed reload, with a selection that may include removed rows.** `app.js:157-160`.
- **Input:** A search that returns 500.
- **What happens:** An error line shows, but the stats and table still show the previous query's data, and the Refund button stays live for those rows.
- **Result:** The stale page looks current, apart from the error line.

## Claims I could not verify
- README lines 5 and 11 (axe-core clean, under 100 ms with 10,000 orders) have no test or measurement in the repo to recompute.
- The README line 12 pricing arithmetic is correct: 12 × 15 × 12 = 2160, and 20% off gives 1728.
- Server behaviours (cookie auth, CSRF, idempotency) cannot be checked from this code.

## Not bugs, checked
- The load/abort race is handled: `latestRequest` is rechecked after `await` and in `finally`.
- Row rendering uses `textContent`, so hostile names such as `<img onerror>` are inert.
- The fallback key in `newIdempotencyKey()` is fine.