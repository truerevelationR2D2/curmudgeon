I found 11 bugs after reading all four files and checking each against the rubric and sandbox scenarios. I only read the code and didn't run it, so every failing case below is traced from the source. Nothing was changed.

I'm assuming the server isn't in the repo. Findings 3 and 11 depend on how it behaves, and I've marked them.

**High**

1. **`app.js:26-29`: a double send is possible, so a duplicate invoice goes out.** `tooSoon()` only blocks a second click within 1000 ms. There is no in-flight flag, no idempotency key, and the button isn't disabled. If the POST takes more than 1 s, a second click goes through.
   - Failing sequence: click Send, wait 1.2 s on a slow network, click again. Two POSTs of the same lines are sent.
   - A successful send also doesn't clear `lines`, so a later click after success sends the same invoice again.

2. **`app.js:26`: an offline send fails silently.** `await fetch(...)` has no try/catch, and only a non-OK response triggers the `alert`. A rejected fetch throws an unhandled rejection, so the user sees nothing.
   - Failing sequence: go offline, click Send. No message appears and no console error is shown, even though the invoice was never sent.
   - `app.js:32` (void) has the same problem.

3. **`app.js:24-29`: a successful send shows nothing.** `sentCount` is incremented but never displayed or used, so the user can't tell whether the send worked. This is a failed or successful result the user can't distinguish, and it combines with finding 1 to make a resend likely.

4. **`app.js:8,11`: the total doesn't match the lines shown.** Each line's price is displayed rounded to 2 decimals, but the total sums the unrounded `qty*price`. Prices with more than 2 decimals are accepted at line 19.
   - Failing input: add two lines with qty 1 and price 0.004. Both display `0.00`, but Total shows `0.01` (0.008 rounds up).
   - The raw floats (0.004) are also what get POSTed, so the sent amount differs from what the user saw.
   - The money arithmetic is also computed inside `render()`, which is the "domain leak" row in the rubric.

5. **`app.js:19`: huge and infinite values are accepted.** `Number("Infinity") > 0` is true, and `validQuantity("99999999999999999999")` passes the digits-only regex.
   - Failing inputs: price `Infinity` gives Total `Infinity`. Qty `99999999999999999999` with price `1` gives `100000000000000000000.00`.
   - `JSON.stringify` turns `Infinity` into `null`, so the server receives `price: null` for that line.

**Medium**

6. **`app.js:16,20`: a whitespace-only client name is accepted.** The HTML `required` attribute passes `"   "`, but `.trim()` then gives `""`. The code never rechecks.
   - Failing input: client `"   "`, qty 1, price 5. A line with an empty client name is added, and the link text and title are blank.

7. **`app.js:19`: invalid input is rejected with no message.** `return` leaves no error state and no indication of which field is wrong.
   - Failing inputs: qty `1.5`, qty `0`, price `1,5` (a comma, which `inputmode="decimal"` keyboards can produce in some locales), and an empty price. Clicking "Add line" does nothing visible in each case.

8. **`app.js:32`, `guards.js:11`, `index.html:24`: the Void button does nothing for most users.** The signed-in user has roles `["viewer","billing"]`, so `canVoid` is false. The click is silently ignored: no message, and the button isn't disabled or hidden. That's a dead control.

9. **`app.js:31-35`: void gives no result and names no invoice.** The POST has no body or id, so it can't say which invoice to void. Success shows nothing, and `lines` stay in place, so the user can still send a voided invoice.

10. **`app.js:1`: refreshing the page loses all lines.** `lines` lives only in memory, with no persistence and no warning on close. Fill in 10 lines, press F5, and they're all gone.

11. **`app.js:2,32`: the admin check only runs in the browser.** `user` is a client-side object, and the console command `user.roles.push("admin")` bypasses it. The same applies to calling `fetch("/api/invoices/void",{method:"POST"})` directly. This is only a real hole if the server doesn't enforce the role, which this repo doesn't show.

**Lower severity, rubric Low or Nit**

- **`app.js:26`:** the body is a JSON string sent without `Content-Type: application/json`, so it goes out as `text/plain`. A server that requires JSON may return 415 on every send.
- **`app.js:25`:** `tooSoon()` sets `lastSend` before the request, so a retry within 1 s of a failed send is silently dropped. The alert says "Try again" but gives no feedback if the retry is ignored.
- **`app.js:26`:** Send with zero lines POSTs `[]`.
- **`app.js:8`:** `<a href="#">` is a focusable dead link that jumps the page to the top. The list also sits in an `aria-live` region that is rebuilt wholesale with `innerHTML`, so a screen reader may re-announce every line on each add.

I checked `escapeHtml` against hostile input (`<img src=x onerror=alert(1)>` and `"&q=1#`), and it holds in both the text and the attribute positions.