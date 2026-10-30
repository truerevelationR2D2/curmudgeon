```json
[
  {
    "file": "app.js",
    "line": 19,
    "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
    "title": "The trimmed client name is never checked. The `required` attribute accepts whitespace-only input, so a line with an empty client name is added.",
    "failing_case": "Type three spaces in Client, 2 in Quantity and 5 in Unit price, then click Add line. `client` trims to \"\" and the line is pushed. The list shows an empty link and the total changes."
  },
  {
    "file": "app.js",
    "line": 19,
    "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
    "title": "The price check accepts Infinity, so an absurd price is stored and the total becomes Infinity.",
    "failing_case": "Enter a Unit price of 1e999. Number('1e999') is Infinity, which passes `price > 0`. The line is added and the total shows 'Infinity'."
  },
  {
    "file": "app.js",
    "line": 26,
    "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
    "title": "A network failure makes fetch reject, and nothing catches it. The user gets no error message. Nothing guards against sending an invoice with no lines either.",
    "failing_case": "Go offline and click Send invoice. fetch throws a TypeError, so the user sees an unhandled promise rejection and no alert. Separately, clicking Send with an empty list posts '[]'."
  },
  {
    "file": "guards.js",
    "line": 58,
    "quote": "  if (now - lastSend < 1000) return true;",
    "title": "`tooSoon()` records the send time before the request succeeds. After a failed send, the retry the alert suggests is silently blocked for a second.",
    "failing_case": "Click Send and get a 500 response. The alert says 'Try again'. Click Send again within 1 second and nothing happens: no request is made and no message is shown."
  },
  {
    "file": "app.js",
    "line": 33,
    "quote": "  const res = await fetch(\"/api/invoices/void\", { method: \"POST\" });",
    "title": "The void request is unguarded against network errors, and it has no body or invoice identifier. It cannot say which invoice to void. The role check exists only in the client, and a non-admin click returns without any message.",
    "failing_case": "For the default user (roles viewer and billing), clicking Void does nothing and shows no feedback. For an admin whose connection drops, fetch rejects uncaught. In both cases the request carries no invoice id."
  }
]
```