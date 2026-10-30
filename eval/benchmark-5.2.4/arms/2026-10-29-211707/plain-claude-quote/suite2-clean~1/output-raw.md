```json
[
  {
    "file": "domain.js",
    "line": 198,
    "quote": "  const total = Number(raw.total);",
    "title": "normaliseOrder accepts a missing or non-numeric total as 0 or 1. The comment above it says such records are dropped, and Number.isFinite does not catch these values.",
    "failing_case": "The API returns {id: 7, total: null, status: 'paid'}, or total: '' or total: true. Number(null) and Number('') give 0, and Number(true) gives 1. The record passes Number.isFinite and shows as a $0.00 order. It is not counted in 'skipped', and it skews the order count and the average."
  },
  {
    "file": "app.js",
    "line": 159,
    "quote": "  const picked = selectedOrders();",
    "title": "Orders that are already refunded or still pending can be selected and sent for refund. Nothing filters on status before the confirm dialog or the POST.",
    "failing_case": "With the status filter on 'All', tick a row whose status is 'refunded' and click 'Refund 1 order'. The dialog says it will send money back, and POST /refunds is sent with that id. A second click after the load completes gets a fresh Idempotency-Key, so the server's idempotency check does not stop a double refund."
  },
  {
    "file": "app.js",
    "line": 167,
    "quote": "    await refund(picked.map((o) => o.id), newIdempotencyKey());",
    "title": "A new idempotency key is generated on every click. Retrying after a timeout or lost response is therefore never recognised as the same attempt, so the key does not prevent double refunds.",
    "failing_case": "The refund POST succeeds on the server but the response is lost, so fetch rejects. The UI says 'not confirmed'. The user clicks Refund again with the same selection. A new UUID is sent, and the server refunds the same orders a second time."
  },
  {
    "file": "domain.js",
    "line": 222,
    "quote": "  return { revenue: cents / 100, count: orders.length, average: orders.length ? cents / orders.length / 100 : null };",
    "title": "'Average per order' divides revenue by all orders, including refunded, pending and unknown ones. These contribute 0 revenue, so the average is understated.",
    "failing_case": "Two orders: one paid for $100 and one pending for $100. Revenue is $108.25 and the count is 2, so the average shows $54.13. Averaged over paid orders only, it would be $108.25."
  }
]
```