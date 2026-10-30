```json
[
 {
  "file": "api.js",
  "line": 17,
  "quote": "return await res.json();",
  "title": "Every successful response must contain a JSON body. A refund that succeeds with an empty body (204 or 200) is reported as failure.",
  "failing_case": "POST /refunds returns 204 No Content after refunding. res.json() throws, the code raises 'not valid JSON', and the UI says 'The refund was not confirmed' even though the money was sent. This invites a retry and a duplicate refund."
 }
]
```
