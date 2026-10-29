```json
[
  {
    "file": "guards.js",
    "line": 10,
    "summary": "canVoid tests `indexOf(\"admin\")` for truthiness, but indexOf returns -1 when the role is absent and 0 when it is first.",
    "failure_scenario": "user.roles = [\"viewer\",\"billing\"] gives indexOf = -1, which is truthy, so canVoid returns true and any non-admin can void invoices. A user whose roles are [\"admin\"] gives 0, which is falsy, so a real admin is refused. The check is inverted for the common cases. The fix is `indexOf(\"admin\") !== -1` or `includes`."
  },
  {
    "file": "guards.js",
    "line": 22,
    "summary": "lastSend is never updated, so tooSoon() never throttles. Also, sentCount in app.js is write-only.",
    "failure_scenario": "lastSend stays 0, so Date.now() - 0 is always far above 1000 and tooSoon() is always false. Double-clicking Send posts the same invoice twice. Nothing sets lastSend after a send, and app.js has no way to do it because the variable is declared with `let` in guards.js."
  },
  {
    "file": "guards.js",
    "line": 18,
    "summary": "validQuantity uses isNaN on a string, so empty, whitespace, fractional, zero and negative values all pass.",
    "failure_scenario": "The qty input is empty: isNaN(\"\") is false (Number(\"\") is 0), so the line is added with qty 0. \"  \" passes the same way. \"-5\" gives a negative line and lowers the total. \"2.5\" is accepted even though the field is inputmode=numeric. \"0x10\" and \"1e3\" are accepted as 16 and 1000. The check should require a positive integer, for example /^\\d+$/ plus > 0."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "The send handler has no in-flight guard and no try/catch. A rejected fetch is unhandled, and the request has no Content-Type header.",
    "failure_scenario": "While offline, fetch rejects and the async click handler throws an unhandled promise rejection, so the user sees no error. Two quick clicks before the first response both post the invoice, because the sole throttle (tooSoon) is broken. The request has no `Content-Type: application/json`, so a server that parses JSON by content type will not read the body. An empty `lines` array can also be sent."
  },
  {
    "file": "app.js",
    "line": 31,
    "summary": "The void action is gated only by a client-side role check on a hard-coded user, and it sends no invoice id.",
    "failure_scenario": "The `user` object is a literal in browser JS, so the authorization check is meaningless. Anyone can call the endpoint, and the server must enforce roles itself. The POST to /api/invoices/void has no body or id, so it cannot say which invoice to void. There is also no confirmation prompt for a destructive action."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "escapeHtml does not escape double quotes, and the value is placed inside the title=\"...\" attribute.",
    "failure_scenario": "Entering a client name like `x\" onmouseover=\"alert(1)` closes the title attribute and injects an event handler (XSS), because escapeHtml only handles &, < and >. It needs to escape \" and ' as well. Separately, `<a href=\"#\">` is a link with no purpose, and clicking it jumps the page to the top."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "The price check and the submit handler give no feedback, and the handler rejects the form silently. The client value is never re-checked and the price is parsed loosely.",
    "failure_scenario": "A price of \"abc\" gives NaN, and `!(NaN > 0)` returns without a message, so the user sees nothing happen. An empty price gives 0, which is also dropped silently. A client entered as only spaces passes the HTML `required` check but trims to \"\", so a line with an empty client is added. A comma decimal such as \"1,50\" gives NaN, which fails silently for locales that use a comma."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "Totals are computed with floating-point arithmetic on money values, and fractional or huge quantities are not bounded.",
    "failure_scenario": "Summing qty*price in floats accumulates rounding error. For example, 3 × 0.1 gives 0.30000000000000004, and the per-line and total toFixed(2) displays can disagree by a cent across many lines. The amount that gets sent is the raw floats, not the rounded cents, so the server total can differ from the one shown. Integer cents should be used."
  },
  {
    "file": "app.js",
    "line": 28,
    "summary": "After a successful send, the lines are not cleared and sentCount is never read or shown. Nothing reflects the sent state.",
    "failure_scenario": "The user sends an invoice, sees no confirmation, and the same lines remain on screen. Clicking Send again posts the whole invoice a second time. sentCount is dead state that nothing displays or uses."
  },
  {
    "file": "guards.js",
    "line": 3,
    "summary": "Guards are implicit globals with a load-order dependency, and nothing checks that they exist.",
    "failure_scenario": "app.js calls escapeHtml, validQuantity, tooSoon and canVoid, which are defined only as globals in guards.js and depend on script order in index.html. Reordering the script tags, or a failed load of guards.js, throws a ReferenceError at the first call. The throw happens inside the render and click handlers, so the page silently stops working."
  }
]
```