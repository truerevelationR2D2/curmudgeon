```json
[
  {
    "file": "app.js",
    "line": 114,
    "quote": "return state.orders.filter((o) => state.selected.has(o.id));",
    "title": "Orders that are already refunded or still pending can be selected and sent for refund. Nothing checks the status, in the UI or before the request.",
    "failing_case": "Tick a row whose status is 'refunded' and click Refund. The confirm dialog appears and the id is POSTed to /refunds. If the server does not reject it, the customer is refunded twice."
  },
  {
    "file": "app.js",
    "line": 167,
    "quote": "await refund(picked.map((o) => o.id), newIdempotencyKey());",
    "title": "A fresh idempotency key is generated on every click. A retry after an unconfirmed failure therefore carries a new key and defeats the server-side de-duplication.",
    "failing_case": "Click Refund, and the POST succeeds on the server but the response times out. The UI shows 'not confirmed'. The user clicks Refund again, which sends a new key, and the order is refunded twice."
  },
  {
    "file": "api.js",
    "line": 17,
    "quote": "return await res.json();",
    "title": "Every successful response must contain a JSON body. A refund that succeeds with an empty body (204 or 200) is reported as failure.",
    "failing_case": "POST /refunds returns 204 No Content after refunding. res.json() throws, the code raises 'not valid JSON', and the UI says 'The refund was not confirmed' even though the money was sent. This invites a retry and a duplicate refund."
  },
  {
    "file": "domain.js",
    "line": 198,
    "quote": "const total = Number(raw.total);",
    "title": "Number() coerces null, '', [] and false to 0 and true to 1, so records with a missing total pass the 'numeric total' check. The record should be dropped as incomplete.",
    "failing_case": "The API returns {id:'7', total:null, status:'paid'}, or total:''. normaliseOrder returns total 0 instead of null. The order is shown as $0.00 and counted in 'Orders' and the average, and it is not counted as skipped."
  }
]
```