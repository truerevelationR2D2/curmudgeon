```json
[
  {
    "file": "guards.js",
    "line": 45,
    "summary": "canVoid uses the truthiness of indexOf(\"admin\"), which inverts the permission check.",
    "failure_scenario": "indexOf returns -1 when the role is absent. -1 is truthy, so a non-admin such as sam (roles viewer and billing) gets true and can void invoices. An admin at index 0 gets 0, which is falsy, so canVoid returns false and the admin is denied. The check should be indexOf(\"admin\") !== -1, or includes(\"admin\")."
  },
  {
    "file": "app.js",
    "line": 25,
    "summary": "The send rate limit never works because lastSend is never updated.",
    "failure_scenario": "lastSend stays 0, so Date.now() - 0 is far above 1000 and tooSoon() is always false. Double-clicking Send posts the invoice twice. The handler should set lastSend = Date.now() before the await. It also has no in-flight guard and does not disable the button, so slow requests overlap."
  },
  {
    "file": "guards.js",
    "line": 53,
    "summary": "validQuantity uses !isNaN on a string, so it accepts empty, whitespace, negative, zero and fractional quantities.",
    "failure_scenario": "An empty qty field gives isNaN(\"\") === false, so it is accepted and Number(\"\") becomes 0. A line with quantity 0 gets added. Quantities of -5 or 2.5 also pass. Negative quantities reduce the total and can produce a negative invoice. The check should require an integer greater than 0 (for example Number.isInteger(Number(q)) && Number(q) > 0, after rejecting blank input)."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "escapeHtml does not escape double quotes, so the title=\"...\" attribute can be broken out of (XSS).",
    "failure_scenario": "A client name of `x\" onmouseover=\"alert(1)` is trimmed and stored, then injected into title=\"...\" with the quote intact. This adds an event-handler attribute to the anchor and runs script on hover. escapeHtml needs to replace \" with &quot; and ' with &#39;."
  },
  {
    "file": "app.js",
    "line": 16,
    "summary": "The client name is not checked for emptiness after trim(), and the required attribute only blocks the empty case before trimming.",
    "failure_scenario": "Entering only spaces passes the browser's required check but trims to an empty string. A line with a blank client is added and rendered as an empty link."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "The send POST has no Content-Type header, no network-error handling, and sends an empty invoice.",
    "failure_scenario": "fetch with a string body defaults to text/plain, so a JSON-expecting server may reject or misparse it. A network failure makes fetch throw, which gives an unhandled rejection and no user message. The click handler also posts even when lines is empty. The same applies to the void request at line 33, which gives no success feedback."
  },
  {
    "file": "app.js",
    "line": 28,
    "summary": "After a successful send, the lines are not cleared and the user gets no confirmation. sentCount is also unused state.",
    "failure_scenario": "The invoice lines stay on screen after sending, so clicking Send again resends the same invoice and creates a duplicate. sentCount is incremented but never read."
  },
  {
    "file": "app.js",
    "line": 18,
    "summary": "Number(\"\") is 0 and Number accepts forms like \"1e3\" or \"Infinity\". The price > 0 check lets Infinity through, and the line is added with no feedback when validation fails.",
    "failure_scenario": "A price of \"Infinity\" passes `price > 0`, then price.toFixed(2) renders \"Infinity\" and the total becomes Infinity. When validation fails, the function returns silently, so the user has no idea why the line was not added."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "Every rendered line is an `<a href=\"#\">` with no handler and no purpose.",
    "failure_scenario": "Clicking the client link jumps the page to the top and adds a #-entry to browser history. Nothing in the diff gives the link a function, and it is a keyboard-focusable stop with no action. It should be plain text."
  },
  {
    "file": "app.js",
    "line": 2,
    "summary": "The user and roles are hardcoded on the client, so the client-side canVoid guard is only cosmetic.",
    "failure_scenario": "Anyone can edit the user object in the console, or call POST /api/invoices/void directly. Authorization has to be enforced on the server. The comment says the guard is for admins only, but nothing in this diff enforces that anywhere that matters."
  }
]
```