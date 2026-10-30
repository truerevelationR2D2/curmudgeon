```json
[
  {
    "file": "guards.js",
    "line": 46,
    "summary": "canVoid only returns true for the 'admin' role, but the only user (app.js:2) has roles [viewer, billing], so the Void button can never do anything. The user object is hardcoded on the client.",
    "failure_scenario": "Sam clicks 'Void invoice'. canVoid returns false and the handler returns silently, with no request and no message. The feature is dead for every user the page can currently represent. If the user object is changed in devtools to include 'admin', the check passes, so the role check is only a UI gate. The server must enforce it, and nothing here shows that it does."
  },
  {
    "file": "app.js",
    "line": 31,
    "summary": "The void request sends no invoice id or body and has no confirmation step. The send request has no Content-Type header.",
    "failure_scenario": "POST /api/invoices/void carries nothing that says which invoice to void, so the server either voids 'the current invoice' by implicit state or rejects the call. An accidental click on an irreversible action goes straight through. The send call posts a JSON string without 'Content-Type: application/json', so many servers will not parse it."
  },
  {
    "file": "app.js",
    "line": 25,
    "summary": "The send guard is time-based, and lastSend is set before the request outcome is known. fetch rejections are not handled.",
    "failure_scenario": "(a) A send that fails with a 500 and is retried within 1 second is silently dropped by tooSoon, with no feedback. (b) A request that takes longer than 1 second can be sent again, so the same invoice is posted twice. (c) If the network is down, fetch rejects, which gives an unhandled promise rejection and no alert, because only !res.ok is handled. (d) sentCount is incremented but never read."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "Send does not check that any lines exist.",
    "failure_scenario": "Clicking 'Send invoice' on a fresh page posts '[]', which creates an empty invoice with a total of 0.00. It also counts as a successful send."
  },
  {
    "file": "app.js",
    "line": 16,
    "summary": "The client name is trimmed but never checked for emptiness. The 'required' attribute accepts whitespace-only input in the browser, and the handler pushes the line without checking.",
    "failure_scenario": "Typing '   ' in Client with qty 1 and price 5 passes `required` and validQuantity. A line with client '' is added and later sent, and it renders as an empty link."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "Price and quantity validation lets through non-finite and absurd values. A rejected form gives the user no message, and the form is not cleared after a successful add.",
    "failure_scenario": "Entering price '1e999' gives Number = Infinity, which passes `price > 0`, so the total shows 'Infinity'. A qty such as '99999999999999999999' loses precision. When validation fails, the submit just returns, so the user sees nothing change. After a successful add, the fields keep their old values, so a repeated Enter adds a duplicate line."
  },
  {
    "file": "app.js",
    "line": 10,
    "summary": "Money is summed as floating-point qty * price, and the total is rounded only at display.",
    "failure_scenario": "Three lines of 3 × 0.10 give a raw sum of 0.8999999999999999, while each line is shown separately rounded. Sums of rounded lines can differ from the displayed total by a cent, and the raw floats are what get posted. Use integer cents."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "Each rendered line is a link with href=\"#\" and a title that repeats the link text. The page offers no way to remove or edit a line.",
    "failure_scenario": "Activating the link jumps the page to the top and adds a '#' history entry. Screen readers announce a link that goes nowhere. A mistyped line cannot be removed, so the user has to reload and lose all lines."
  }
]
```