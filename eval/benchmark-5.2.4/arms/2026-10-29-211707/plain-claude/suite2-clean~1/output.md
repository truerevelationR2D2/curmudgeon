I read all five files (`app.js`, `domain.js`, `api.js`, `index.html`, `styles.css`) plus the README, and changed nothing. I did not run the code; each failure below comes from reading it and from standard JavaScript behaviour. The bugs are ordered by impact.

1. **`app.js:128` with `api.js:16-20`: a refund that succeeded can be reported as failed, and the retry refunds again.**
   - **What is wrong:** `refundSelected` makes a new idempotency key on every click. `request()` also throws "not valid JSON" when the response body is empty. The README says the key stops a repeated request refunding twice, but a retry carries a different key, so the server cannot recognise it.
   - **Failing sequence:** Select order A and click Refund. The server refunds it and replies `204 No Content`, or the connection drops after the server has processed the request. `res.json()` throws, so the user sees "The refund was not confirmed". The user clicks Refund again, which sends a new key, and A is refunded twice.
   - **Fix direction:** Keep one key per attempt and reuse it for retries. Treat an empty 2xx body as success.

2. **`domain.js:11-12`: orders with no real total get through as $0.00.**
   - **What is wrong:** `Number(raw.total)` turns `null`, `""`, `[]` and `false` into `0`, and `true` into `1`. All of these pass `Number.isFinite`. The comment on line 7 says records with "no numeric total" are dropped.
   - **Failing input:** `{id: "1", total: null}`, or `total: ""`. The order shows as $0.00, can be selected and refunded, and is not counted in "records could not be shown". `total: "12abc"` is rejected, which is correct.
   - **Fix direction:** Require `typeof raw.total === "number"`, or a non-empty numeric string.

3. **`app.js:75-76,121-123`: nothing stops refunding orders that are already refunded or still pending.**
   - **What is wrong:** Every row has a checkbox, whatever its status. The confirm dialog and the request treat all selected rows as refundable.
   - **Failing sequence:** Select a row whose status is "refunded", and click Refund. The dialog says "Refund 1 order totalling $X" and the request is sent. If the server doesn't reject it, the customer is refunded twice.
   - **Fix direction:** Disable the checkbox unless `status === "paid"`.

4. **`domain.js:33-36`: the average per order is wrong whenever some orders aren't paid.**
   - **What is wrong:** `average` divides revenue from paid orders only by `orders.length`, which includes refunded, pending and unknown orders.
   - **Failing input:** One paid order of $100 and one pending order of $100 gives an average of about $54, not $108.25 per paid order. It also changes with the status filter. "Orders" (`count`) counts all rows, so it doesn't match revenue either. This may be intended, but the label "Average per order" is ambiguous.

5. **`domain.js:27`: rounding is wrong for negative totals.**
   - **What is wrong:** `normaliseOrder` accepts negative totals. `Math.round` rounds a half toward positive infinity, so the "half up per order" comment (line 24) doesn't hold for them.
   - **Failing input:** `total: -0.025` gives `Math.round(-2.5) = -2`, not -3. This is minor and only affects credits.

6. **`domain.js:17` with `index.html:22`: unrecognised statuses can't be found.**
   - **What is wrong:** Any status other than paid, refunded or pending becomes `"unknown"`. The filter dropdown has no "unknown" option, and those orders get no status colour in the CSS.
   - **Failing input:** An order with status `"failed"` shows "unknown". It can only be seen under "All". It is also selectable and refundable (see 3).

7. **README claims I couldn't check.**
   - The axe-core result, the "under 100 ms with 10,000 orders" figure and the 44 px target are not backed by any test or script in the repo. The README itself says the performance figure is a mock and that screen readers were not tested.
   - The pricing arithmetic is correct: 12 × $15 × 12 = $2,160, and 20% off is $1,728.

I found no bugs in the debounce and abort handling, the stale-response guard in `load`, or the page clamping. The CSS looks fine.