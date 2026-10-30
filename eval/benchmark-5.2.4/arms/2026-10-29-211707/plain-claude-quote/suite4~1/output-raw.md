```json
[
  {
    "file": "guards.js",
    "line": 10,
    "quote": "  if (user.roles.indexOf(\"admin\")) {",
    "title": "canVoid tests the truthiness of indexOf's return value instead of comparing it to -1, so the admin check is inverted",
    "failing_case": "The user in app.js has roles [\"viewer\",\"billing\"]. indexOf(\"admin\") returns -1, which is truthy, so canVoid returns true and the non-admin can void invoices. A user whose roles are [\"admin\"] gets index 0, which is falsy, so canVoid returns false and the admin is blocked."
  },
  {
    "file": "guards.js",
    "line": 24,
    "quote": "  return Date.now() - lastSend < 1000;",
    "title": "lastSend is never updated, so tooSoon always returns false and the double-send guard does nothing",
    "failing_case": "lastSend stays 0 forever, so Date.now() - 0 is far greater than 1000. Double-clicking \"Send invoice\" posts the invoice twice and sentCount goes up by 2."
  },
  {
    "file": "guards.js",
    "line": 18,
    "quote": "  return !isNaN(qty);",
    "title": "validQuantity accepts empty, whitespace-only, negative, fractional and zero values, and the string \"Infinity\"",
    "failing_case": "Leave Quantity blank. The input value is \"\", isNaN(\"\") is false, so validation passes and Number(\"\") is 0. A line with qty 0 is added. Entering \"-5\" or \"1.5\" also passes, which gives a negative or fractional quantity and a wrong total. \"Infinity\" passes too and makes the total Infinity."
  },
  {
    "file": "guards.js",
    "line": 5,
    "quote": "  return String(text).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");",
    "title": "escapeHtml does not escape double or single quotes, but its output is used inside a quoted HTML attribute",
    "failing_case": "app.js uses the output in title=\"...\". Enter the client name `x\" onmouseover=\"alert(1)` and the title attribute closes early and injects an event handler, which is XSS."
  },
  {
    "file": "app.js",
    "line": 8,
    "quote": "    `<li><a href=\"#\" title=\"${escapeHtml(l.client)}\">${escapeHtml(l.client)}</a>: ${l.qty} × ${l.price.toFixed(2)}</li>`",
    "title": "The attribute-context injection is exploitable here because escapeHtml leaves quotes untouched",
    "failing_case": "Add a line with client `\" autofocus onfocus=\"alert(document.cookie)` and the markup produced by render() runs script."
  },
  {
    "file": "app.js",
    "line": 26,
    "quote": "  const res = await fetch(\"/api/invoices\", { method: \"POST\", body: JSON.stringify(lines) });",
    "title": "The send handler never records the send time, has no in-flight guard, and doesn't catch fetch rejection; it also posts an empty invoice and sets no JSON Content-Type",
    "failing_case": "Click Send with no lines and it posts []. If the network is offline, fetch rejects, the exception is unhandled and the user sees no message. Two rapid clicks send two requests, because the lastSend that tooSoon reads is never set."
  },
  {
    "file": "app.js",
    "line": 19,
    "quote": "  if (!validQuantity(qtyText) || !(price > 0)) return;",
    "title": "The client name is trimmed after the required check, so whitespace-only names pass, and invalid input is rejected silently",
    "failing_case": "Type \"   \" into Client, which satisfies the browser's `required` check. After trim() it is \"\", and no check rejects it, so a line with an empty client is pushed. Bad quantity or price input shows no error to the user."
  }
]
```