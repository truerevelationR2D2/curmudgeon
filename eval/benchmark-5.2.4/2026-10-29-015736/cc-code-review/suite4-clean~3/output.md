```json
[
  {
    "file": "app.js",
    "line": 31,
    "summary": "The Void button is client-side gated only, and the void request carries no invoice id.",
    "failure_scenario": "canVoid() only checks the in-page `user` constant, and the POST to /api/invoices/void has no invoice id or body. A viewer can call the endpoint directly, or edit `user.roles` in devtools. Unless the server enforces the admin check, any signed-in user can void. If the server does enforce it, it has no way to know which invoice to void."
  },
  {
    "file": "guards.js",
    "line": 56,
    "summary": "tooSoon() sets lastSend before the send succeeds, and the one-second window is not a real duplicate-send guard.",
    "failure_scenario": "A send that fails (!res.ok) still starts the 1s lockout, so a quick retry after the alert is silently ignored. A slow request longer than 1s lets a second click through while the first is still in flight, which sends a duplicate invoice. There is no in-flight flag or button disable."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "fetch is not wrapped in try/catch, and the send has no error handling for network failures.",
    "failure_scenario": "If the network is down, fetch rejects and the async handler throws an unhandled rejection. The user gets no alert. The lockout from tooSoon() is already consumed, so the next retry within 1s is also dropped. The same applies to the void handler at line 33."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "The send request has no Content-Type header and no CSRF token, and it sends the lines array without an invoice header.",
    "failure_scenario": "fetch with a string body defaults to text/plain. A server that expects application/json may reject or mis-parse it. The POST is also a cookie-authenticated state-changing request with no CSRF protection."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "Sending an empty invoice is not blocked, and `lines` is never cleared or reset after a successful send.",
    "failure_scenario": "Clicking Send with no lines POSTs `[]`. After a successful send, `lines` stays populated, so the next send re-submits the same lines. `sentCount` is incremented but never used or shown."
  },
  {
    "file": "app.js",
    "line": 16,
    "summary": "The client name is only trimmed, and an empty-after-trim value is accepted. The `required` attribute is bypassed by whitespace.",
    "failure_scenario": "Entering '   ' in the client field passes the browser `required` check but trims to ''. A line with an empty client is added, which gives an empty link in the list."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "Validation accepts any positive price, including Infinity and values with extra decimals, and does not bound qty.",
    "failure_scenario": "Number('1e999') is Infinity, which passes `price > 0`. The total then becomes 'Infinity'. A huge qty such as 99999999999999999999 is accepted, so the total loses precision. Float arithmetic on money (qty * price summed) gives rounding errors, for example 0.1*3."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "Each rendered line uses `<a href=\"#\">`, a dead link with a title attribute. It scrolls to top and adds a history entry, and it is not actionable.",
    "failure_scenario": "Clicking the client name jumps the page to the top and pushes '#' onto the history. Screen-reader users hear a link that does nothing."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The list rebuilds the whole innerHTML on every add, and there is no way to remove or edit a line.",
    "failure_scenario": "A mistyped line can't be corrected before sending, so the user must reload and lose all lines. The aria-live region re-announces the entire list on every add."
  },
  {
    "file": "guards.js",
    "line": 51,
    "summary": "validQuantity accepts numbers beyond safe-integer range, with no upper bound.",
    "failure_scenario": "The quantity '9007199254740993' passes the regex and Number() >= 1 but loses precision, so the stored qty differs from what the user typed."
  }
]
```