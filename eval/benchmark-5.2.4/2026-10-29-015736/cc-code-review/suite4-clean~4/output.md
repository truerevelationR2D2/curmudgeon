```json
[
  {
    "file": "guards.js",
    "line": 21,
    "summary": "tooSoon() records the send timestamp before the request runs, so it throttles attempts rather than sends. A failed send locks out the retry the alert asks for, and a slow request lets a duplicate through.",
    "failure_scenario": "The POST fails and the user sees 'Try again.' If they click again within 1s, tooSoon() returns true and the click is silently ignored. In the other direction, if the POST takes longer than 1s, a second click after that 1s goes through and sends the invoice twice, because nothing tracks the in-flight request. Use an in-flight flag that is reset in a finally block."
  },
  {
    "file": "app.js",
    "line": 24,
    "summary": "The send handler does not validate or reset state. It posts even when there are no lines, and it never clears `lines` after a successful send. sentCount is incremented but never read.",
    "failure_scenario": "The user clicks Send on an empty invoice and an empty invoice is POSTed. After a successful send the lines stay in the list, so a later click, or one after the 1s window, re-sends the same lines and creates a duplicate invoice. The only success feedback is the invisible sentCount counter."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "fetch is not wrapped in try/catch, so a network failure is an unhandled rejection with no user feedback. The JSON body is sent without a Content-Type header.",
    "failure_scenario": "The user is offline or the server is unreachable, so fetch rejects. The click handler throws an unhandled promise rejection and no alert is shown. A JSON.stringify body without 'Content-Type: application/json' goes out as text/plain, which servers that parse JSON by content type will reject or ignore."
  },
  {
    "file": "app.js",
    "line": 32,
    "summary": "The void button is shown to everyone, and canVoid() silently returns for non-admins. Authorization exists only on the client, and the void POST carries no invoice identifier.",
    "failure_scenario": "A viewer or billing user clicks Void and nothing happens, with no message. Anyone can call POST /api/invoices/void from the console, so unless the server checks the role independently, voiding is open to everyone. The request also names no invoice, so it is ambiguous which one is voided."
  },
  {
    "file": "app.js",
    "line": 16,
    "summary": "The client field is trimmed but never re-checked for emptiness. The HTML `required` attribute accepts whitespace-only input.",
    "failure_scenario": "The user enters '   ' as the client. `required` passes, trim() turns it into '', and a line with an empty client name is pushed and rendered as an empty link."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "Price validation `!(price > 0)` accepts Infinity and exponent forms. Invalid input is dropped with no feedback. Money is summed and displayed as floating point.",
    "failure_scenario": "The user types 'Infinity' or '1e999' as the price. Number() returns Infinity, the check passes, and the total shows 'Infinity'. A price such as '1,50' gives NaN and the submit does nothing, with no error message. Summing qty*price in floating point, for example 3 × 0.1, yields values that are not exact cents. Use integer cents and an upper bound."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "Each line renders as `<a href=\"#\">` with a redundant title, which is not a real link target.",
    "failure_scenario": "Keyboard and screen-reader users hear a link that goes nowhere. Activating it navigates to '#' and jumps the page to the top, and the line is announced as a link instead of text. It should be plain text."
  },
  {
    "file": "index.html",
    "line": 16,
    "summary": "The qty and price inputs have no `required` attribute, `pattern`, or visible error text. A rejected submit gives no feedback, and `lines` has no remove or edit control.",
    "failure_scenario": "The user submits a quantity of '0' or '1.5', or an empty price. The JS returns silently and the form appears broken. A wrong line that was added cannot be removed, so the user must reload and lose all lines."
  }
]
```