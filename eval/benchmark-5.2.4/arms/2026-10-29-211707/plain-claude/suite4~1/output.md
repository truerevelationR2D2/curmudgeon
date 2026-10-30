Bugs found (nothing changed). Line numbers are per file.

1. **guards.js:45 – `canVoid` is inverted.** `indexOf("admin")` returns -1 when the role is absent, and -1 is truthy. It returns 0 when "admin" is the first role, and 0 is falsy.
   - Failing input: sam has roles `["viewer","billing"]`. `indexOf` gives -1, so `canVoid` returns true and the non-admin can void.
   - Reverse case: a user with `roles: ["admin"]` gets 0, so `canVoid` returns false and the admin is blocked.
   - Fix: `includes("admin")`.

2. **guards.js:53 – `validQuantity` accepts empty and blank input.** `isNaN("")` and `isNaN("  ")` are false, because both convert to 0.
   - Failing input: leave Quantity empty, enter price 5, and submit. `validQuantity("")` is true, so a line with qty 0 is pushed.
   - Related cases: `"1e3"` and `"0x10"` pass and become 1000 and 16. `"-3"` and `"1.5"` also pass, which gives a negative or fractional quantity and a negative total. The field has `inputmode="numeric"`, so integers were presumably intended.

3. **guards.js:57–59 and app.js:24–29 – the double-send guard never works.** `lastSend` is never assigned (the file has no `lastSend = Date.now()`). `Date.now() - 0` is far greater than 1000, so `tooSoon()` is always false.
   - Failing sequence: double-click "Send invoice". Two POSTs go out, and the invoice is duplicated.
   - Related: even with `lastSend` set, the check runs before the `await`. A failed send would still block the retry for 1 second.

4. **app.js:20 – a client name is never required, and empty `lines` can be sent.** `required` on the client input only applies on native submit, and this handler does its own validation.
   - Failing input: whitespace-only client `"   "` passes the browser's `required` check. After `trim()` it becomes `""`, and a line with an empty client is pushed.
   - Also, "Send invoice" with zero lines (app.js:26) POSTs `[]`, and the server may create an empty invoice.

5. **app.js:26 – the send request has no `Content-Type` header.** `fetch` with a string body defaults to `text/plain;charset=UTF-8`. A JSON API that expects `application/json` will reject it or not parse it. A network failure also throws an unhandled rejection with no user message, because `fetch` isn't in a try/catch. The same applies to the void call at app.js:33.

6. **app.js:8 – `escapeHtml` doesn't escape double quotes (guards.js:40), and its output is used inside the `title="..."` attribute.**
   - Failing input: client `x" onmouseover="alert(1)`. It becomes `title="x" onmouseover="alert(1)"`, which gives attribute injection and script execution on hover (XSS).
   - Fix: also escape `"` and `'`.

7. **app.js:10–11 and app.js:8 – floating-point money sums.** Totals are accumulated as floats of `qty*price`.
   - Failing input: 3 lines of qty 1 at price 0.1 give 0.30000000000000004. `toFixed(2)` hides this in that case, but sums of values such as 1.005 round incorrectly (`(1.005).toFixed(2)` gives "1.00"). Use integer cents.

8. **app.js:19 – a price of `Infinity` or `1e999` is accepted.** `Number("1e999")` is `Infinity`, and `Infinity > 0` is true. `toFixed` then shows "Infinity", and the total becomes Infinity.

9. **app.js:28 – `sentCount` is never read or shown, and there is no feedback or clearing after a successful send.** The user can resend the same lines, which is the same duplicate-invoice risk as bug 3. This one is minor.

I haven't run any of this, so each failing case comes from reading the code.