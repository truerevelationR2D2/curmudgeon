```json
[
 {
  "file": "guards.js",
  "line": 10,
  "quote": "  if (user.roles.indexOf(\"admin\")) {",
  "title": "canVoid tests the truthiness of indexOf's return value, so the admin check is inverted. indexOf returns -1 (truthy) when the role is absent and 0 (falsy) when it is first in the list.",
  "failing_case": "user.roles = [\"viewer\",\"billing\"] (the app's own user, no admin role): indexOf is -1, so canVoid returns true and a non-admin can void invoices. user.roles = [\"admin\"]: indexOf is 0, so canVoid returns false and a real admin is blocked."
 },
 {
  "file": "guards.js",
  "line": 18,
  "quote": "  return !isNaN(qty);",
  "title": "validQuantity accepts any string that coerces to a number. That includes an empty or whitespace string, zero, negatives, fractions, Infinity and hex. The field is meant to be an integer quantity.",
  "failing_case": "Leave Quantity empty (or type ' ', '0', '-5', '2.5', '0x10' or '1e999') and submit with a valid price. isNaN('') is false, so a line is added with qty 0, -5, 2.5, 16 or Infinity. A negative quantity reduces the total, and Infinity makes the total Infinity."
 },
 {
  "file": "guards.js",
  "line": 24,
  "quote": "  return Date.now() - lastSend < 1000;",
  "title": "lastSend is never updated, because neither tooSoon nor the send handler assigns it. It stays 0, so tooSoon always returns false and the one-second duplicate-send guard never works.",
  "failing_case": "Double-click 'Send invoice'. Both clicks pass tooSoon(), two POSTs to /api/invoices go out, and the invoice is sent twice."
 },
 {
  "file": "guards.js",
  "line": 5,
  "quote": "  return String(text).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");",
  "title": "escapeHtml does not escape double or single quotes, but render() uses it inside a double-quoted title attribute. That allows attribute injection (XSS).",
  "failing_case": "Enter the client name `x\" onmouseover=\"alert(document.cookie)` and add a line. The rendered `<a title=\"x\" onmouseover=\"alert(document.cookie)\">` runs script when the user hovers over it."
 },
 {
  "file": "app.js",
  "line": 20,
  "quote": "  lines.push({ client, qty: Number(qtyText), price });",
  "title": "The client name is only trimmed and never checked for empty, so the HTML `required` check can be bypassed with whitespace. Price is checked with `price > 0` only, so Infinity passes.",
  "failing_case": "Enter ' ' as the client (required passes because the value is non-empty, then trim() gives ''). Enter qty 1 and price 5. A line with an empty client is added and sent. Entering price '1e999' gives Infinity, which makes the total Infinity."
 },
 {
  "file": "app.js",
  "line": 26,
  "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
  "title": "The send handler has no empty check, sets no Content-Type, and does not catch fetch rejections. It never updates the page after a successful send, and it never resets or clears the lines (sentCount is incremented but never used). A network error becomes an unhandled rejection with no message to the user.",
  "failing_case": "Click 'Send invoice' with no lines: an empty invoice '[]' is POSTed. With the network down, fetch rejects, no alert is shown, and the user gets no feedback."
 }
]
```
