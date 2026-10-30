The repo has one commit and no diff, so I reviewed the whole tree as the target. Nothing was run or tested; every finding comes from reading the code. The findings are ranked most severe first.

```json
[
  {
    "file": "guards.js",
    "line": 8,
    "summary": "canVoid uses indexOf's return value as a boolean, so the admin check is inverted.",
    "failure_scenario": "A user with roles [\"viewer\",\"billing\"] gets indexOf(\"admin\") = -1, which is truthy, so canVoid returns true and any non-admin can void. A user with roles [\"admin\",...] gets index 0, which is falsy, so a real admin is refused. The check should be `indexOf(\"admin\") !== -1` or `includes`."
  },
  {
    "file": "guards.js",
    "line": 16,
    "summary": "validQuantity accepts empty, whitespace, negative, zero and fractional quantities.",
    "failure_scenario": "The caller passes a string. An empty qty gives isNaN(\"\") = false, so it is accepted and Number(\"\") = 0. \"-5\" and \"0\" are accepted, and the total goes negative or zero. \"2.5\" is accepted although the field is numeric/integer. \"  \" also passes. The check needs to be like `Number.isInteger(Number(q)) && Number(q) > 0` with a non-empty string."
  },
  {
    "file": "guards.js",
    "line": 22,
    "summary": "tooSoon never updates lastSend, so the debounce never triggers.",
    "failure_scenario": "lastSend stays 0, so Date.now() - 0 is always far above 1000 and tooSoon() is always false. Double-clicking Send posts the invoice twice. app.js also never sets lastSend after sending."
  },
  {
    "file": "app.js",
    "line": 33,
    "summary": "The void action is gated only by the client-side canVoid and sends no invoice id or auth.",
    "failure_scenario": "The `user` object is a hard-coded client-side constant, and the POST to /api/invoices/void carries no body or identifier. Anyone can edit `user` in the console or call the endpoint directly. The server must enforce the role, and the void request does not say which invoice to void."
  },
  {
    "file": "app.js",
    "line": 28,
    "summary": "The send handler has no in-flight guard or error handling, and sentCount is only incremented.",
    "failure_scenario": "A fetch that rejects (network error) throws an unhandled rejection with no alert, because only !res.ok is handled. With tooSoon broken, two rapid clicks send twice. An empty `lines` array is sent without a check. The request has no Content-Type header, so the JSON body goes out as text/plain. sentCount is never read or displayed, and `lines` is not cleared after a successful send, so the user can resend the same invoice."
  },
  {
    "file": "app.js",
    "line": 18,
    "summary": "The price check allows blank or non-finite values, and the client name is not re-checked after trim.",
    "failure_scenario": "Number(\"\") is 0, which `price > 0` rejects, so that case is silent. `Infinity`, or \"1e999\", passes `price > 0` and makes the total Infinity, shown as \"Infinity\". The user gets no feedback on any rejected input, because the handler just returns. A client of only whitespace passes the HTML `required` attribute but trims to \"\", and a line with an empty client is pushed."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "render builds HTML by string interpolation, and escapeHtml does not escape double quotes.",
    "failure_scenario": "l.client is inserted into the title=\"...\" attribute. A client name like `x\" onmouseover=\"alert(1)` is not escaped, because escapeHtml handles only & < >, so it breaks out of the attribute and injects an event handler (XSS). The fix is to also escape `\"` and `'`, or to use textContent/setAttribute."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "render uses float arithmetic for money and shows the line total in an unlabeled form; the href=\"#\" link is also pointless.",
    "failure_scenario": "Totals are summed as floating-point qty*price, so 3 × 0.10 comes out as 0.30000000000000004, and toFixed hides this only at display time. Rounding on many lines can disagree with the server's total. The `<a href=\"#\">` client link jumps the page to the top on click and does nothing else. Using integer cents and a plain span would be better."
  },
  {
    "file": "index.html",
    "line": 16,
    "summary": "The qty and price inputs use inputmode only, with no type or constraints, and the Send and Void buttons are always enabled.",
    "failure_scenario": "Nothing in the markup restricts the qty or price values, so all validation rests on the broken JS guard. The Void button is shown to every user and Send is clickable with zero lines. Invalid input is rejected silently, with no error message or aria-live feedback."
  }
]
```