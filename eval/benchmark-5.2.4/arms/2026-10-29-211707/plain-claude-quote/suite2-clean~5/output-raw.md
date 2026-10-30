```json
[
  {
    "file": "domain.js",
    "line": 11,
    "quote": "  const total = Number(raw.total);",
    "title": "Null, empty or non-numeric-looking totals are coerced to 0 and accepted as valid orders instead of being skipped. Number(null), Number(\"\"), Number([]) and Number(false) are all 0, so the Number.isFinite check passes. The record is shown as $0.00 and counted in the order count and average, and it is never reported as skipped.",
    "failing_case": "The API returns {\"id\":\"A1\",\"total\":null,\"status\":\"paid\",\"customer\":{\"name\":\"Bob\"}}. normaliseOrder returns an order with total 0 instead of null. The table shows $0.00, the Orders count includes it, and the 'could not be shown because the data is incomplete' message never appears."
  },
  {
    "file": "app.js",
    "line": 120,
    "quote": "  const picked = selectedOrders();",
    "title": "Any listed order can be selected and refunded, whatever its status. Orders that are already refunded, still pending or have an unknown status are not excluded. The refund button is enabled for them, and the confirmation dialog states an amount that includes them.",
    "failing_case": "Filter by 'refunded', tick an order whose status is already refunded and click Refund. The client sends its id to POST /refunds. The confirmation promises 'sends money back to the customers', and the client relies on the server to reject a double refund. Selecting a 'pending' order, which was never charged, shows the same problem."
  },
  {
    "file": "app.js",
    "line": 128,
    "quote": "    await refund(picked.map((o) => o.id), newIdempotencyKey());",
    "title": "A fresh idempotency key is generated on every click, so the key cannot protect the retry that it exists for. If the first request reached the server but the response was lost, for example a timeout or dropped connection, the user retries. The retry carries a new key and the server treats it as a new refund.",
    "failing_case": "Select order X and click Refund. The server processes the refund, but the response is lost and the client shows 'The refund was not confirmed'. The user clicks Refund again on the still-selected X. The retry sends a different Idempotency-Key, so X is refunded twice."
  }
]
```