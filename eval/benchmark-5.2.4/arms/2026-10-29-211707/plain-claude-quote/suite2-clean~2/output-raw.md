```json
[
  {
    "file": "api.js",
    "line": 17,
    "quote": "    return await res.json();",
    "title": "A successful refund is reported as failed when the server replies with no JSON body. The shared request() helper requires JSON on every OK response.",
    "failing_case": "POST /api/v1/refunds returns 204 No Content or an empty 200 after refunding. res.json() throws, so request() throws ApiError 'not valid JSON'. The money has already moved, but refundSelected shows 'The refund was not confirmed'. The user retries, and the retry gets a fresh idempotency key, so the orders are refunded twice."
  },
  {
    "file": "app.js",
    "line": 128,
    "quote": "    await refund(picked.map((o) => o.id), newIdempotencyKey());",
    "title": "A new idempotency key is generated on every click, so the key cannot protect a retry after a timeout or ambiguous failure. Nothing stops already-refunded orders from being selected and sent.",
    "failing_case": "The user selects orders and confirms. The refund succeeds on the server but the response is lost, which shows the error message. The user clicks Refund again. A new UUID is sent and the server treats it as a new request, so it refunds again. Separately, selecting a row whose status is 'refunded' or 'pending' and clicking Refund sends that id to the refund endpoint, because there is no status check."
  },
  {
    "file": "domain.js",
    "line": 35,
    "quote": "  return { revenue: cents / 100, count: orders.length, average: orders.length ? cents / orders.length / 100 : null };",
    "title": "'Average per order' divides revenue, which only counts paid orders, by the count of all orders, including refunded, pending and unknown ones. The average is understated and does not match the revenue shown.",
    "failing_case": "Orders: one paid at $100 standard tier, and nine pending. Revenue is $108.25. The average is shown as $10.83 instead of $108.25 per paid order."
  }
]
```