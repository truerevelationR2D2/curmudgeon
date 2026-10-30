```json
[
 {
  "file": "/tmp/dm-a152cjyy/work/app.js",
  "line": 20,
  "quote": "  lines.push({ client, qty: Number(qtyText), price });",
  "title": "A whitespace-only client name is accepted. The `required` attribute passes it, but the value is trimmed to an empty string and never checked.",
  "failing_case": "Type three spaces in Client, 2 in Quantity and 5 in Unit price, then click Add line. A line with an empty client name is added, and it is included in the total and sent."
 },
 {
  "file": "/tmp/dm-a152cjyy/work/app.js",
  "line": 26,
  "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
  "title": "The fetch is not wrapped in try/catch, so a network failure gives the user no message. `tooSoon()` has already started its 1-second lockout, so an immediate retry is silently ignored. The request also sends a JSON string with no Content-Type header, so it goes out as text/plain.",
  "failing_case": "Go offline and click Send invoice. fetch rejects, the promise rejects unhandled, and no alert appears. Go back online and click Send again within 1 second. The click is silently ignored. A server that parses only application/json would also reject the body."
 },
 {
  "file": "/tmp/dm-a152cjyy/work/guards.js",
  "line": 23,
  "quote": "  if (now - lastSend < 1000) return true;",
  "title": "The throttle is a fixed 1-second window set before the request finishes. It is not tied to the request being in flight or to its success. A slow request can be sent twice, and a failed send blocks the retry.",
  "failing_case": "The server takes 3 seconds to respond. Click Send, wait 1.1 seconds, and click again. A second POST goes out while the first is still pending, so the invoice is duplicated."
 },
 {
  "file": "/tmp/dm-a152cjyy/work/app.js",
  "line": 19,
  "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
  "title": "Invalid input is dropped with no feedback. The price check also accepts Infinity, so a huge value breaks the total.",
  "failing_case": "Enter a price of 1e999. Number() gives Infinity, which passes `price > 0`. The line is added, the total shows Infinity, and the JSON sent to the server contains null for the price. Entering a quantity of 0 or 1.5 does nothing and shows no message."
 }
]
```
