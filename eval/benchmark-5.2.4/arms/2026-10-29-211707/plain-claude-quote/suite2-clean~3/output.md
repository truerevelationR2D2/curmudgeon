```json
[
 {
  "file": "api.js",
  "line": 17,
  "quote": "    return await res.json();",
  "title": "A successful response with an empty body, such as 204 No Content from POST /refunds, throws 'not valid JSON'. A refund that went through is then reported as failed.",
  "failing_case": "The server processes the refund and answers 204 or 200 with an empty body. res.json() throws, refund() rejects, and the UI shows 'The refund was not confirmed'. There is no success toast and the list is not reloaded. The user retries, and the retry gets a new idempotency key, so the customer can be refunded twice."
 }
]
```
