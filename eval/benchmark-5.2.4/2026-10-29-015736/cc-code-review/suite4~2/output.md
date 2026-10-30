```json
[
  {
    "file": "guards.js",
    "line": 10,
    "summary": "canVoid uses indexOf's return value as a boolean, so the permission check is inverted and unreliable.",
    "failure_scenario": "user.roles = [\"viewer\",\"billing\"] gives indexOf(\"admin\") = -1, which is truthy, so canVoid returns true and any non-admin can void. A real admin at index 0 gives 0, which is falsy, so canVoid returns false and a sole-role admin is denied. The check needs `!== -1` or `includes`."
  },
  {
    "file": "guards.js",
    "line": 24,
    "summary": "lastSend is never updated, so the double-send guard tooSoon() never blocks anything.",
    "failure_scenario": "lastSend stays 0 and Date.now() is far larger than 1000, so tooSoon() always returns false. Double-clicking Send posts the invoice twice. app.js only increments sentCount and never records the send time."
  },
  {
    "file": "app.js",
    "line": 25,
    "summary": "The send handler is not protected against re-entry while the fetch is in flight, and it doesn't check for an empty invoice.",
    "failure_scenario": "A second click while the first fetch is pending passes tooSoon() (which is also broken), and a fetch rejection (offline) throws an unhandled promise error with no user feedback. With lines = [] it posts an empty invoice. The request also has no Content-Type header, so the server receives text/plain."
  },
  {
    "file": "guards.js",
    "line": 18,
    "summary": "validQuantity uses isNaN on a string, so it accepts empty, whitespace, negative, zero and fractional quantities.",
    "failure_scenario": "An empty qty input gives isNaN(\"\") = false, so it passes and Number(\"\") = 0. A line with qty 0 is added. \"-5\" and \"1.5\" also pass although the field is meant for whole quantities, which makes the total wrong or negative."
  },
  {
    "file": "guards.js",
    "line": 5,
    "summary": "escapeHtml does not escape double quotes, but it is used inside a quoted title=\"...\" attribute.",
    "failure_scenario": "A client name such as `x\" onmouseover=\"alert(1)` closes the title attribute and injects an event handler into the <a> tag. This is stored XSS in the render() output in app.js, line 8."
  },
  {
    "file": "app.js",
    "line": 16,
    "summary": "The client name is only trimmed, and `required` is not enforced in the handler, so a whitespace-only client is accepted.",
    "failure_scenario": "Entering \"   \" satisfies the browser's `required` check, trims to \"\", and the handler pushes a line with an empty client. The list then shows a blank link."
  },
  {
    "file": "app.js",
    "line": 31,
    "summary": "The void request has no invoice identifier and no body, and the permission check exists only on the client.",
    "failure_scenario": "POST /api/invoices/void is sent with nothing saying which invoice to void. The only authorization is the client-side canVoid on a user object defined in the browser, so a direct request bypasses it. The success path also gives no feedback and does not clear `lines`."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "Invalid input is dropped silently with no message, and the price check is inconsistent with the quantity check.",
    "failure_scenario": "A price of \"\" or \"abc\" fails `price > 0` and the handler returns with no error shown. The user clicks Add line and nothing happens. A comma decimal like \"1,5\" gives NaN and is rejected the same way."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The anchor href=\"#\" is a dead link and a pointless focusable element in the list, and clicking it jumps the page to the top.",
    "failure_scenario": "Each line renders a focusable <a href=\"#\"> that does nothing. Keyboard users tab through meaningless links, and activating one scrolls to the top and changes the URL hash."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "The total is computed with floating-point multiplication and summation, with no rounding to cents.",
    "failure_scenario": "Lines such as 3 × 0.1 and 1 × 0.2 accumulate binary floating-point error, and the intermediate sum is not rounded per line. The total can drift from the sum of the displayed per-line amounts, for example 0.30000000000000004 before toFixed."
  }
]
```