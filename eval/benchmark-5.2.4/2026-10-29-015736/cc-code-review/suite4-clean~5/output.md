```json
[
  {
    "file": "app.js",
    "line": 25,
    "summary": "The double-send guard stamps `lastSend` before the request and only blocks for 1 second. There is no in-flight guard.",
    "failure_scenario": "A slow POST takes more than 1s and the user clicks Send again. `tooSoon()` returns false and a duplicate invoice is created. In the opposite case the first POST fails with a 500 and the alert says 'Try again'. A retry within 1s is silently swallowed, because `lastSend` was already set and is never reset on failure."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "`fetch` is not wrapped in try/catch, so a network error produces an unhandled rejection with no user feedback. There is also no Content-Type header, and nothing stops an empty invoice from being sent.",
    "failure_scenario": "The user is offline. `fetch` rejects and nothing is shown, so the user can't tell the send failed. Separately, with `lines` empty, clicking Send posts `[]` and creates an empty invoice. The body is a JSON string sent as text/plain, so a server that parses JSON by Content-Type will reject it."
  },
  {
    "file": "app.js",
    "line": 28,
    "summary": "After a successful send, `lines` is not cleared or re-rendered and there is no confirmation. `sentCount` is write-only.",
    "failure_scenario": "The invoice is sent and the UI looks unchanged. The user clicks Send again, 1 second later, and the same lines are posted as a second invoice."
  },
  {
    "file": "guards.js",
    "line": 46,
    "summary": "Void authorization is enforced only in the client, against a hardcoded `user` object. The void request carries no invoice id.",
    "failure_scenario": "Anyone can edit `user.roles` in the console, or call `POST /api/invoices/void` directly, and bypass the admin check. The 'viewer, billing' user also sees an active Void button that does nothing. If the server does not check roles, this is a privilege bypass. The POST body is empty, so the server cannot tell which invoice to void."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "Price validation accepts `Infinity` (for example '1e999' or 'Infinity'). A whitespace-only client name is accepted after `trim()`.",
    "failure_scenario": "The user enters price '1e999'. `Number` returns Infinity, which passes `price > 0`, so the total shows 'Infinity' and the invoice is sent with an invalid value. Entering '   ' as the client passes the `required` attribute but becomes an empty string after `trim()`, so a line with a blank client is added."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "Money is summed as floating-point numbers, so the displayed total can be off by a cent.",
    "failure_scenario": "For example, 3 × 0.1 + 0.2 sums with rounding error. The per-line `toFixed(2)` values and the total's `toFixed(2)` can then disagree by a cent, and the same floats are posted to the server."
  },
  {
    "file": "guards.js",
    "line": 51,
    "summary": "`validQuantity` has no upper bound. Very long digit strings pass and convert to imprecise or Infinity numbers.",
    "failure_scenario": "A quantity of '9'×400 becomes Infinity. Then `qty * price` is Infinity, and the total and invoice are corrupted. A quantity above 2^53 silently loses precision."
  },
  {
    "file": "app.js",
    "line": 21,
    "summary": "The form is not reset after a line is added, and there is no way to remove a line.",
    "failure_scenario": "The user adds a line, and the fields keep their old values. A second click on Add line adds an exact duplicate. A mistaken line cannot be removed, so the only fix is to reload the page and lose everything."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "Each line renders a `<a href=\"#\">` with no handler. The anchor is a non-functional link that is also a tab stop.",
    "failure_scenario": "A keyboard or screen-reader user tabs to a link that does nothing except jump the page to the top. This is an accessibility defect. The title attribute duplicates the link text."
  }
]
```