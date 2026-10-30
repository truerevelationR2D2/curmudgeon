```json
[
 {
  "file": "app.js",
  "line": 16,
  "quote": "const client = document.getElementById(\"client\").value.trim();",
  "title": "A whitespace-only client name passes the HTML `required` check. After trimming it is an empty string, and nothing re-checks it before the line is added.",
  "failing_case": "Type three spaces in Client, enter qty 1 and price 5, and submit. `required` is satisfied, `client` becomes \"\", and a line with a blank client is pushed and rendered as an empty link."
 },
 {
  "file": "app.js",
  "line": 19,
  "quote": "if (!validQuantity(qtyText) || !(price > 0)) return;",
  "title": "The price check accepts Infinity. `Number(\"Infinity\")` is Infinity, which is greater than 0, so it is treated as valid. The total then becomes \"Infinity\". Huge quantities of digits also pass the quantity check and lose precision.",
  "failing_case": "Enter price \"Infinity\" (or \"1e999\") with qty 1. The line is added and the Total shows \"Infinity\"."
 },
 {
  "file": "app.js",
  "line": 25,
  "quote": "if (tooSoon()) return;",
  "title": "The guard sets the timestamp before the request runs. A failed send, or one that ends in a network error, blocks a retry made within 1 second with no message. The guard also does not stop duplicates: there is no in-flight lock, so a request that takes longer than 1s can be sent again.",
  "failing_case": "Click Send, get the 'not sent' alert, and click Send again within 1s. The second click is silently ignored. Alternatively, click Send, wait 1.1s while the request is still pending, and click again. A duplicate invoice is POSTed."
 },
 {
  "file": "app.js",
  "line": 26,
  "quote": "const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
  "title": "There is no try/catch, so a network failure makes `fetch` reject and the handler throws an unhandled rejection with no user feedback. The JSON body is sent without a Content-Type header, so it goes out as text/plain. Nothing checks that `lines` is non-empty, so an empty invoice can be sent.",
  "failing_case": "Go offline and click Send: `fetch` rejects, nothing is shown, and `lastSend` is already set. With no lines added, click Send: `[]` is POSTed as an invoice. A server that expects application/json rejects the request."
 },
 {
  "file": "app.js",
  "line": 33,
  "quote": "const res = await fetch(\"/api/invoices/void\", { method: \"POST\" });",
  "title": "The void request carries no invoice identifier, so the server cannot know which invoice to void. Authorization rests only on the client-side `canVoid` check, and a rejected `fetch` is unhandled.",
  "failing_case": "An admin clicks Void. The POST has no body or ID, so the server either errors or voids the wrong invoice. A non-admin can call the endpoint directly, so the server has to enforce the role check."
 }
]
```
