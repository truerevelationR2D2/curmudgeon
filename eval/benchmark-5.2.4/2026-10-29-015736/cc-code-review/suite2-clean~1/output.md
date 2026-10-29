```json
[
  {
    "file": "app.js",
    "line": 128,
    "summary": "A new idempotency key is generated on every click, so retrying a refund whose first response was lost sends a different key.",
    "failure_scenario": "The user confirms a refund and the server processes it, but the response is dropped (timeout or network error). `refund()` throws, and the message tells the user to retry. The retry gets a fresh UUID, so the server's `Idempotency-Key` dedup never matches and the customer is refunded twice. The key should be kept per attempt (per set of ids) and reused until the outcome is known. The README's claim that a repeated request does not refund twice only holds if the client reuses the key."
  },
  {
    "file": "app.js",
    "line": 76,
    "summary": "Any order can be selected and refunded, including ones already refunded or still pending, and the confirm dialog totals them anyway.",
    "failure_scenario": "The user ticks a row with status 'refunded' or 'pending' (or 'unknown', which comes from `normaliseOrder` for any other status string). `selectedOrders()` does not filter by status, so the confirm dialog says 'Refund 1 order totalling $X' and POSTs the id. If the server does not reject it, the customer is refunded again. The dialog amount is also wrong for orders that cannot be refunded."
  },
  {
    "file": "domain.js",
    "line": 13,
    "summary": "`Number(raw.total)` turns null, empty string, true and [] into valid totals (0 or 1), so incomplete records are shown instead of skipped.",
    "failure_scenario": "The API returns `{id:'7', total:null}` or `total:''`. `Number(null)` is 0, which is finite, so the order is accepted and shown as $0.00. It is not counted in 'skipped', and the 'incomplete data' message never appears. A refund of it would be confirmed at $0.00. Negative and huge totals are also accepted."
  },
  {
    "file": "domain.js",
    "line": 40,
    "summary": "Summary 'Revenue' includes sales tax and 'Average per order' divides by all orders, including refunded and pending ones that contribute 0.",
    "failure_scenario": "A $100 paid standard-tier order shows revenue of $108.25, because the 8.25% tax is added to the order total. Add a refunded order and a pending order and the average becomes $36.08 instead of $108.25. The 'Average per order' label does not say which of the two it is."
  },
  {
    "file": "app.js",
    "line": 98,
    "summary": "`load()` clears the selection and resets the page on every reload, including when the refund itself fails.",
    "failure_scenario": "While the user is paging, or has ticked orders across pages, a late search timer or status change fires `load()`. This silently drops the selection and returns to page 1, and the confirm dialog count no longer matches what the user ticked. Selections also persist invisibly across pages, so a refund can include orders that are not on screen."
  },
  {
    "file": "app.js",
    "line": 142,
    "summary": "A pending search debounce timer is not cleared when the status filter changes (or on a refund), so two loads can fire.",
    "failure_scenario": "The user types in the search box, then changes the status within 250 ms. `load` runs immediately, then the stale timer fires a second `load` that aborts the first and flashes 'Loading…' again. The same timer can fire mid-refund and wipe the selection while the refund is in flight."
  },
  {
    "file": "api.js",
    "line": 12,
    "summary": "There is no timeout or abort on requests, and the refund POST has no abort path.",
    "failure_scenario": "If the proxy hangs, the 'Refunding…' button stays disabled forever (`state.refunding` never resets) and the user cannot retry. On a slow link `fetch` can wait indefinitely."
  },
  {
    "file": "domain.js",
    "line": 33,
    "summary": "`Math.round(order.total * 100)` suffers float error, which contradicts the 'whole cents, no drift' comment.",
    "failure_scenario": "A total of 1.005 gives 100.49999999999999 and rounds to 100 cents instead of 101. Applying the tax and discount in basis points afterwards cannot recover the lost cent, so the summary can be off by a cent per order. Totals should be handled as integer cents from the API, or rounded via a decimal string."
  },
  {
    "file": "README.md",
    "line": 3,
    "summary": "Quantitative and compliance claims (axe-core clean, under 100 ms with 10,000 orders) have no test, script or fixture in the repo, and the 'rotate the leaked key' instruction refers to history that is not here.",
    "failure_scenario": "A reviewer cannot recompute the 'axe-core reports no WCAG 2.1 A or AA violations' or '<100 ms' claims. The commit adds no test files, so the stated behaviour (late-response cancel, rounding, clampPage) is unverified. The 'status in words, not colour alone' claim also has no style for the 'unknown' status, which renders a muted dot with the word 'unknown'."
  },
  {
    "file": "app.js",
    "line": 110,
    "summary": "If a load is aborted by a newer one that then fails with an error for the older controller, `state.loading` is only reset by the newest request, and the refund button can briefly be enabled on stale orders.",
    "failure_scenario": "A load completes and the user selects rows. A new search starts and sets `loading = true`. Meanwhile the refund button's enabled state is recomputed only through `renderRefundButton`, and `state.selected` still holds ids from the old result set until the new response arrives. A refund click in that window sends ids that are no longer displayed."
  }
]
```