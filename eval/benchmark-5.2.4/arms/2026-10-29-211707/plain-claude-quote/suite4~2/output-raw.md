Bugs: indexOf truthiness; escapeHtml misses quotes (title attribute); validQuantity accepts "" / whitespace / negative / fractional; lastSend never updated; empty client not checked (required not enforced? form required works on submit, but trim whitespace passes).

```json
[
  {
    "file": "guards.js",
    "line": 10,
    "quote": "  if (user.roles.indexOf(\"admin\")) {",
    "title": "indexOf result is used as a boolean. It is truthy for -1 (not an admin) and falsy for 0 (admin in first position), so the check is inverted.",
    "failing_case": "The user is { roles: [\"viewer\", \"billing\"] }, with no admin role. indexOf returns -1, so canVoid returns true and a non-admin can void. A user with roles [\"admin\"] gets 0, so canVoid returns false and the admin is blocked."
  },
  {
    "file": "guards.js",
    "line": 5,
    "quote": "  return String(text).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");",
    "title": "escapeHtml does not escape double or single quotes, but app.js uses it inside a double-quoted title attribute. This allows attribute injection (XSS).",
    "failing_case": "The client name is `x\" onmouseover=\"alert(1)`. The title attribute closes early and an onmouseover handler is injected into the anchor."
  },
  {
    "file": "guards.js",
    "line": 18,
    "quote": "  return !isNaN(qty);",
    "title": "validQuantity accepts an empty or whitespace-only string (isNaN('') is false). It also accepts zero, negative, fractional and Infinity values, even though the field is meant for a whole-number quantity.",
    "failing_case": "The user leaves Quantity blank. qtyText is '', so validQuantity returns true and a line with qty 0 is added. Entering '-5' adds a negative line that reduces the total. Entering '1.5' or 'Infinity' is also accepted."
  },
  {
    "file": "guards.js",
    "line": 24,
    "quote": "  return Date.now() - lastSend < 1000;",
    "title": "lastSend is never updated, so the duplicate-send guard never triggers. The first send also sees Date.now() - 0, which is large, so tooSoon is always false.",
    "failing_case": "The user double-clicks 'Send invoice'. Both clicks pass tooSoon() and two POSTs are sent, so the invoice is duplicated."
  },
  {
    "file": "app.js",
    "line": 16,
    "quote": "  const client = document.getElementById(\"client\").value.trim();",
    "title": "The client is trimmed after the browser's `required` check, and the trimmed value is never checked for being empty. A whitespace-only name passes `required` and is added as an empty client.",
    "failing_case": "The user types three spaces in Client, with a valid quantity and price, and submits. A line with client '' is pushed."
  },
  {
    "file": "app.js",
    "line": 26,
    "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
    "title": "There is no Content-Type header, no empty-lines check and no try/catch around fetch. A network failure produces an unhandled rejection. An empty invoice can also be sent.",
    "failing_case": "The user clicks Send with no lines, and an empty invoice is posted. If the network is offline, fetch rejects and the user sees no message."
  }
]
```