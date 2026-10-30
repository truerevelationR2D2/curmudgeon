```json
[
  {
    "file": "app.js",
    "line": 19,
    "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
    "title": "Price check accepts Infinity. It also gives the user no feedback when a line is rejected.",
    "failing_case": "Enter price '1e999' (or 'Infinity'). Number() gives Infinity, which is > 0, so the line is added. The line list shows 'Infinity' and the total shows 'Infinity'. The invoice sent to the server then contains a non-finite price. JSON.stringify turns Infinity into null, so the server receives price null."
  },
  {
    "file": "app.js",
    "line": 20,
    "quote": "  lines.push({ client, qty: Number(qtyText), price });",
    "title": "The client is trimmed but never checked for empty. The input's `required` attribute accepts whitespace-only text, and trimming then leaves an empty string.",
    "failing_case": "Type '   ' (spaces) in Client, qty 1, price 5, and submit. `required` passes because the value is non-empty. After trim() the client is '', and a line with a blank client is added and sent."
  },
  {
    "file": "app.js",
    "line": 25,
    "quote": "  if (tooSoon()) return;",
    "title": "tooSoon() stamps the time before the request succeeds. A failed send therefore blocks the user's retry for a second. The guard also does not stop a double send while a slow request is still in flight.",
    "failing_case": "Click Send and the server returns 500. The alert says 'Try again', but clicking again within 1s is silently ignored. Separately, if the POST takes 3s, a second click at 1.5s passes the guard and sends the invoice twice."
  },
  {
    "file": "app.js",
    "line": 26,
    "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
    "title": "Nothing prevents sending an empty invoice. fetch rejections are unhandled. No Content-Type header is set. Lines are not cleared after a successful send.",
    "failing_case": "Click Send with no lines: an empty array '[]' is POSTed. With the network offline, fetch rejects and the click handler throws an unhandled rejection, so the user sees no alert. After a successful send the lines stay, so another click more than 1s later duplicates the invoice. The body is sent as text/plain, so a server that expects JSON may not parse it."
  },
  {
    "file": "app.js",
    "line": 32,
    "quote": "  if (!canVoid(user)) return;",
    "title": "Voiding is silently refused for non-admins, and the permission check exists only in the client. The default user is not an admin, so the Void button does nothing and gives no feedback.",
    "failing_case": "The user {roles:['viewer','billing']} clicks Void. The handler returns without a request or a message, so the button looks broken. Because the check is only in the page, anyone can edit `user.roles` in the console, or POST to /api/invoices/void directly, unless the server also enforces it."
  }
]
```