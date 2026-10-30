I read all five source files (354 lines) and ran nothing. These are the bugs I could trace to a concrete failure, most serious first.

1. **A new idempotency key is made for every attempt** (`app.js:180`, `README.md:9`)
   - **What is wrong:** `refundSelected` calls `newIdempotencyKey()` on each click. The key therefore never matches between a failed attempt and its retry, so the server's duplicate protection can't work.
   - **Failing sequence:** select order 5 and click Refund. The server processes it, but the response is lost, for example a proxy timeout or a dropped connection. `request()` throws, and the error message tells the user to check statuses before trying again. If they click Refund again anyway, the selection is still set, so a second request goes out with a different key. The server treats it as new and refunds order 5 twice.
   - **Fix direction:** keep the key until the attempt is confirmed or the selection changes.

2. **A failed reload after a successful refund leaves the refunded orders selected and shown as `paid`** (`app.js:181-182`, `app.js:157-160`)
   - **What is wrong:** `load()` catches its own errors, so `refundSelected` never sees them. `state.selected` is only cleared inside a successful `load()`, at `app.js:150`.
   - **Failing sequence:** refund orders A and B and get a success toast. The follow-up `GET /orders` returns 500. The table still shows A and B as `paid` and still selected, and the Refund button is enabled. Clicking it again sends another refund for A and B, with a new key because of bug 1.

3. **`Number()` accepts values that aren't numbers** (`domain.js:211`, comment at `domain.js:207`)
   - **What is wrong:** `Number(null)`, `Number("")`, `Number([])` and `Number(false)` all give `0`, which passes `Number.isFinite`. `Number(true)` gives `1`, and `Number(" ")` gives `0`. The comment says records with no numeric total are dropped.
   - **Failing input:** `{id:"1", total:null}` is accepted as a $0.00 order. It is not counted in `skipped`, and the "incomplete data" message never appears. It still counts toward `count` and drags the average down. A record with `total:""` behaves the same way.

4. **Refunded and unknown-status orders can be selected and refunded** (`app.js:88-96`, `app.js:127-129`)
   - **What is wrong:** `renderRow` gives every row a checkbox, and nothing filters by status.
   - **Failing sequence:** filter by `refunded`, tick the rows and click Refund. The confirm dialog reports a dollar amount, and a second refund request goes to the server for orders that were already refunded.

5. **Duplicate order ids are toggled and refunded together** (`app.js:94`, `app.js:128`, `app.js:180`)
   - **What is wrong:** selection is keyed only by `order.id`. `normaliseOrder` doesn't deduplicate ids.
   - **Failing input:** the API returns two records with `id:"7"`. Ticking one box leaves the other row unticked (its checkbox was rendered before the change), but `selectedOrders()` returns both. The confirm dialog and the refund then cover two orders, and `ids` is `["7","7"]`.

6. **Selection is applied to rows the user can't see** (`app.js:127-129`)
   - **What is wrong:** `selected` spans all pages, and `selectedOrders()` filters the whole `state.orders`. The button label counts every selected order, but only 10 rows are visible.
   - **Failing sequence:** tick rows on page 1, go to page 2 and click Refund. Page 1's orders are refunded too, although none of them are on screen. The dialog gives only a count and a total, so nothing shows which orders are included.

7. **Revenue adds tax on top of `order.total`** (`domain.js:228-229`) — suspected, not confirmed. If the API's `total` already includes tax, then `total: 100.00` shows as $108.25 of revenue. Nothing in the repo says which it is, and the README only quotes pricing. Please confirm the API contract before treating this as a bug.