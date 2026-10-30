Bugs found (no files changed). Line numbers: `app.js` is lines 1–35 of the listing above; `guards.js` is listed as 36–60, so I give its in-file line numbers.

1. **`guards.js:45` – `canVoid` has its logic inverted.**
   - `indexOf("admin")` returns `-1` when the role is absent, and `-1` is truthy. It returns `0` when "admin" is the first role, and `0` is falsy.
   - Input: the default user `{roles:["viewer","billing"]}` gives `-1`, so `canVoid` is true and a non-admin can void. A real admin with `roles:["admin"]` gives `0`, so `canVoid` is false and the admin is blocked.
   - This is an authorization bypass. The server must enforce the role too, because the client check is only advisory. Fix: use `includes("admin")`.

2. **`guards.js:53` – `validQuantity` accepts bad quantities.** `isNaN` coerces its argument.
   - `""` and `"   "` coerce to 0, so they pass. The quantity field is not `required`, so submitting with it empty adds a line with qty 0.
   - `"-3"`, `"1.5"` and `"1e3"` pass. A negative quantity produces a negative total.
   - `"Infinity"` passes, and the total becomes `Infinity`. `Number("0x10")` is 16.
   - The input is meant to be numeric, so it should require a positive integer, for example `/^\d+$/` and `> 0`.

3. **`guards.js:57-59` and `app.js:25-29` – `tooSoon` never fires.**
   - `lastSend` is only ever `0` and is never updated, so `Date.now() - 0` is always far above 1000.
   - Double-click "Send invoice" and two POSTs go out, which sends the invoice twice.
   - `lastSend = Date.now()` should be set before the `await`. If it is set only after the response, two clicks made while the request is in flight still both pass. Setting it on failure is also needed so a retry is not blocked.

4. **`app.js:19-20` – an empty client is not rejected.**
   - The `required` attribute on `index.html:74` is not checked for whitespace. Enter `"   "` as the client: it passes `required` but `trim()` makes it `""`, and the line is pushed with an empty client.
   - Fix: check `client` is non-empty in JS.

5. **`app.js:18-19` – an empty price field is mishandled.** `Number("")` is 0, which the `price > 0` check rejects, so the failure is silent. `Number("1,5")` is NaN, also silently rejected. Neither gives the user any feedback, and invalid input just does nothing.

6. **`app.js:26-28` – the send path has no error handling and sends the wrong data.**
   - `fetch` rejects on a network failure, so there is no `try/catch`. The error is an unhandled rejection, and the `alert` on line 27 never runs.
   - There is no `Content-Type: application/json` header, so the body goes out as `text/plain`. A server that parses JSON by content type will reject or ignore it.
   - Sending with zero lines posts `[]`.
   - `sentCount` is incremented but never read, and `lines` is not cleared after a successful send. Pressing Send again resends the same invoice, with only the broken `tooSoon` guard in the way.

7. **`app.js:31-34` – the void request has no payload and no error handling.**
   - It POSTs to `/api/invoices/void` with no invoice id. The server cannot tell which invoice to void, and nothing is voided locally.
   - A network failure is unhandled, as in bug 6.

8. **`app.js:8` – the HTML escaping is incomplete.** The `escapeHtml` in `guards.js:40` does not escape `"`, and `l.client` is placed inside `title="…"`. A client of `x" onmouseover="alert(1)` closes the attribute and injects a handler (XSS). Add `.replace(/"/g, "&quot;")` and escape `'` too.

9. **`app.js:10-11` – floating-point money.** Totals are summed as floats and shown with `toFixed(2)`. For example, 3 × 0.1 gives 0.30000000000000004. Line prices are shown with `toFixed`, but the per-line `qty * price` is never rounded. Totals can drift by a cent when many lines are summed. Use integer cents.

10. **`app.js:1-3` – `render` never runs on load, and there is no way to remove a line.** The list stays blank until the first add, which is minor. The `<a href="#">` at line 8 is a link with no handler. Clicking it scrolls to the top and changes the URL hash.