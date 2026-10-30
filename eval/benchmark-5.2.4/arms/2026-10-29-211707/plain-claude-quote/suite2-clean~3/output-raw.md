```json
[
  {
    "file": "domain.js",
    "line": 198,
    "quote": "  const total = Number(raw.total);",
    "title": "Missing, null, empty or boolean totals are coerced to a number instead of being rejected as incomplete. Negative totals are accepted too.",
    "failing_case": "The API returns {id:\"7\", total:null, status:\"paid\"}, or total:\"\", or total:true. Number(null) and Number(\"\") are 0 and Number(true) is 1, so Number.isFinite passes. The order is shown as $0.00 or $1.00 and is not counted in `skipped`. It can be selected and refunded, and it skews the revenue and average figures."
  },
  {
    "file": "app.js",
    "line": 159,
    "quote": "  const picked = selectedOrders();",
    "title": "Any order can be selected and refunded, whatever its status. Orders that are already refunded or still pending are not excluded, so the confirm dialog totals them as money going back to customers.",
    "failing_case": "Filter by 'refunded', tick an order that is already refunded, and click Refund. The confirm dialog says it will send money back, and the POST /refunds request is sent. If the server does not reject it, the customer is refunded twice."
  },
  {
    "file": "api.js",
    "line": 17,
    "quote": "    return await res.json();",
    "title": "A successful response with an empty body, such as 204 No Content from POST /refunds, throws 'not valid JSON'. A refund that went through is then reported as failed.",
    "failing_case": "The server processes the refund and answers 204 or 200 with an empty body. res.json() throws, refund() rejects, and the UI shows 'The refund was not confirmed'. There is no success toast and the list is not reloaded. The user retries, and the retry gets a new idempotency key, so the customer can be refunded twice."
  },
  {
    "file": "app.js",
    "line": 167,
    "quote": "    await refund(picked.map((o) => o.id), newIdempotencyKey());",
    "title": "A fresh idempotency key is generated on every click. A retry after a timeout or network error is therefore a new attempt and is not deduplicated.",
    "failing_case": "The refund POST succeeds on the server but the response is lost, or the 200 response has no JSON body. The user clicks Refund again. The second request carries a different Idempotency-Key, so the server refunds the same orders twice."
  },
  {
    "file": "domain.js",
    "line": 222,
    "quote": "  return { revenue: cents / 100, count: orders.length, average: orders.length ? cents / orders.length / 100 : null };",
    "title": "The average per order divides revenue by all orders, including pending and refunded ones that contribute 0. The average is understated and does not match the revenue figure.",
    "failing_case": "Two orders: one paid for $100 and one pending for $100. Revenue is $108.25, but the average is shown as $54.13, which is neither order's value. Ten refunded orders and one paid order drag the average toward zero."
  }
]
```