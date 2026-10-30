```json
[
 {
  "file": "app.js",
  "line": 26,
  "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
  "title": "A network failure (fetch rejects) is not handled, so the user gets no error message and the `tooSoon` timestamp has already been consumed. An empty invoice can also be sent, and the lines are never cleared or marked as sent.",
  "failing_case": "Go offline and click Send. fetch throws a TypeError, the async handler rejects unhandled, and the user sees nothing, so the `!res.ok` alert is skipped. Separately, click Send with zero lines and an empty array `[]` is POSTed."
 },
 {
  "file": "guards.js",
  "line": 23,
  "quote": "  if (now - lastSend < 1000) return true;",
  "title": "The duplicate-send guard is a fixed 1-second timer, not an in-flight guard. A request that takes longer than 1s can be sent again, creating a duplicate invoice. A failed send also starts the lockout, so an immediate retry is silently ignored.",
  "failing_case": "The server takes 3s to respond. Click Send at t=0 and again at t=1.5s. Both POSTs go through and the invoice is created twice."
 },
 {
  "file": "app.js",
  "line": 19,
  "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
  "title": "Price validation accepts Infinity and absurdly large values, and a whitespace-only client name passes. The rejected-input path also gives the user no feedback.",
  "failing_case": "Enter client \"   \" (the `required` attribute passes, but trim() gives \"\"), qty 1, price \"1e999\". Number gives Infinity, so `Infinity > 0` is true. A line with an empty client is added and the total shows \"Infinity\"."
 },
 {
  "file": "app.js",
  "line": 10,
  "quote": "  const total = lines.reduce((sum, l) => sum + l.qty * l.price, 0);",
  "title": "The money total is summed in floating point and then rounded with toFixed, so it can differ from the sum of the displayed line amounts by a cent. There is also no cap on qty.",
  "failing_case": "Add a line with price 1.005 qty 1. toFixed(2) shows \"1.00\" because 1.005 is stored as 1.00499..., while a half-up rounding gives 1.01. Prices with more than 2 decimals are also accepted."
 },
 {
  "file": "app.js",
  "line": 33,
  "quote": "  const res = await fetch(\"/api/invoices/void\", { method: \"POST\" });",
  "title": "The void request carries no invoice identifier and no body. The only authorization check is client-side against a hard-coded `user` object, so it depends entirely on the server to enforce who may void and which invoice. A fetch rejection is also unhandled.",
  "failing_case": "A viewer calls fetch('/api/invoices/void', {method:'POST'}) from the console, or edits `user.roles` to add \"admin\". The client guard is bypassed and the server cannot tell which invoice to void."
 }
]
```
