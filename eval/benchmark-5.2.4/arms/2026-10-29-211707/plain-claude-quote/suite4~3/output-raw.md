```json
[
  {
    "file": "guards.js",
    "line": 10,
    "quote": "  if (user.roles.indexOf(\"admin\")) {",
    "title": "canVoid tests the raw indexOf result, so the check is inverted. indexOf returns -1 (truthy) when the role is absent and 0 (falsy) when \"admin\" is the first role.",
    "failing_case": "The user {roles:[\"viewer\",\"billing\"]} has no admin role, but indexOf returns -1, so canVoid returns true and the void request is sent. A user with roles:[\"admin\"] gets index 0, so canVoid returns false and a real admin cannot void."
  },
  {
    "file": "guards.js",
    "line": 18,
    "quote": "  return !isNaN(qty);",
    "title": "validQuantity accepts an empty or blank string, and also negative, fractional and Infinity values. isNaN(\"\") is false because \"\" coerces to 0. The quantity input is a plain text field with no other check.",
    "failing_case": "Leave Quantity empty (or type a space) and enter price 5. validQuantity(\"\") is true, so a line with qty 0 is added. Typing \"-3\", \"1.5\" or \"Infinity\" is also accepted, giving a negative or NaN/Infinity total."
  },
  {
    "file": "guards.js",
    "line": 5,
    "quote": "  return String(text).replace(/&/g, \"&amp;\").replace(/</g, \"&lt;\").replace(/>/g, \"&gt;\");",
    "title": "escapeHtml does not escape double or single quotes, but app.js uses it inside a double-quoted HTML attribute (title=\"...\"). A client name can break out of the attribute and inject handlers (XSS).",
    "failing_case": "Enter client `x\" onmouseover=\"alert(1)` and add a line. The rendered markup is title=\"x\" onmouseover=\"alert(1)\", which runs script when the user hovers the link."
  },
  {
    "file": "guards.js",
    "line": 24,
    "quote": "  return Date.now() - lastSend < 1000;",
    "title": "lastSend is never updated, either in guards.js or in the send handler in app.js. It stays 0, so tooSoon() is always false and the double-send guard never works.",
    "failing_case": "Double-click \"Send invoice\". Both clicks pass tooSoon(), so two POSTs to /api/invoices are sent and the invoice is duplicated."
  },
  {
    "file": "app.js",
    "line": 16,
    "quote": "  const client = document.getElementById(\"client\").value.trim();",
    "title": "The client is trimmed but never checked for emptiness. The HTML `required` attribute accepts whitespace-only input, so a line with an empty client name is stored.",
    "failing_case": "Type three spaces in Client, with quantity 2 and price 3. The browser's required check passes, trim() yields \"\", and a line with a blank client is added and sent."
  }
]
```