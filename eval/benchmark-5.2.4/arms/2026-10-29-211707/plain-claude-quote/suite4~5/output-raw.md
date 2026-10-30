```json
[
  {
    "file": "guards.js",
    "line": 5,
    "quote": "  return String(text).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");",
    "title": "escapeHtml does not escape double quotes, but app.js uses it inside a quoted HTML attribute (title=\"...\"). A client name can break out of the attribute, which is an XSS hole.",
    "failing_case": "Enter the client name `x\" onmouseover=\"alert(1)` and add a line. render() emits title=\"x\" onmouseover=\"alert(1)\", so the handler runs when the mouse moves over the link."
  },
  {
    "file": "guards.js",
    "line": 10,
    "quote": "  if (user.roles.indexOf(\"admin\")) {",
    "title": "indexOf returns -1 (truthy) when the role is missing and 0 (falsy) when admin is the first role. The check is inverted for these cases, so non-admins can void and some admins cannot.",
    "failing_case": "With user = {roles:[\"viewer\",\"billing\"]}, indexOf is -1, canVoid returns true, and the viewer voids the invoice. With roles:[\"admin\"], indexOf is 0, canVoid returns false, and the admin is blocked."
  },
  {
    "file": "guards.js",
    "line": 18,
    "quote": "  return !isNaN(qty);",
    "title": "validQuantity accepts any string that isNaN treats as numeric. This includes the empty string, whitespace-only strings, negative numbers, zero and fractions. The qty field is meant to be a whole quantity.",
    "failing_case": "Leave Quantity empty, or enter \"-5\" or \"0\" or \"2.5\", with a valid price. validQuantity returns true and a line is added with qty 0, -5, 0 or 2.5, which gives a zero or negative total."
  },
  {
    "file": "guards.js",
    "line": 24,
    "quote": "  return Date.now() - lastSend < 1000;",
    "title": "lastSend is never updated, in guards.js or in the send handler, so tooSoon always returns false. The rate limit never applies.",
    "failing_case": "Double-click \"Send invoice\". Both clicks pass tooSoon() and two POSTs to /api/invoices go out, so the invoice is sent twice."
  },
  {
    "file": "app.js",
    "line": 16,
    "quote": "  const client = document.getElementById(\"client\").value.trim();",
    "title": "The client is trimmed after the HTML `required` check, and the empty result is never validated. A whitespace-only client passes `required`, becomes an empty string, and is pushed as a line with no client.",
    "failing_case": "Type three spaces in Client, enter qty 1 and price 5, and submit. A line with client \"\" is added and shows as \": 1 × 5.00\"."
  },
  {
    "file": "app.js",
    "line": 26,
    "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
    "title": "The fetch call is not wrapped in try/catch, so a network failure rejects the handler. The user sees no error message. The request also sends no Content-Type header, so a JSON-expecting server may not parse it.",
    "failing_case": "Go offline and click Send. fetch rejects with TypeError, the handler throws an unhandled rejection, and the \"not sent\" alert never shows."
  }
]
```