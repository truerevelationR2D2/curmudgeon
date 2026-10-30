I found six bugs by reading the code. I didn't run any of it, and I changed no files.

1. **`app.js:24-29` (with `guards.js:56-61`): the double-send guard fails on slow requests, and a failed send blocks the retry.**
   - `tooSoon()` only blocks clicks within 1 second of the last click. It doesn't track whether a request is still running.
   - **Duplicate send:** if `/api/invoices` takes more than 1 second, a second click at about 1.5s passes the guard and sends the invoice again. Both responses then bump `sentCount`.
   - **Blocked retry:** `lastSend` is set before the request. If the first send fails and the user clicks Send again within 1 second, the click is silently ignored.
   - **Network errors:** `fetch` can reject, for example when offline. Nothing catches that, so the rejection goes unhandled and the user sees no message, because the `alert` only covers `!res.ok`.

2. **`app.js:19`: the price check accepts `Infinity` and other odd number formats.**
   - `Number("Infinity") > 0` is true, so typing `Infinity` as the price adds a line. The line shows `Infinity` and the total becomes `Infinity`.
   - `Number()` also accepts `1e3` (1000) and `0x10` (16), which the user probably didn't mean.
   - Check with `Number.isFinite(price)`, or validate the text with a regex as `validQuantity` does.

3. **`app.js:16, 19-20`: a whitespace-only client name is accepted.**
   - The `required` attribute on `index.html:75` passes `"   "`. The code then trims it to `""` and never re-checks.
   - Entering client `"   "`, quantity `1` and price `5` adds a line with an empty client name.

4. **`guards.js:50-52`: there is no upper bound on quantity.**
   - `"99999999999999999999"` passes the regex, and `Number()` turns it into 1e20, which is past the safe-integer range.
   - The total (`qty * price`) then loses precision, and the line shows `100000000000000000000`.

5. **`app.js:26`: the send handler allows an empty invoice and never clears `lines`.**
   - With no lines added, clicking Send posts `[]`.
   - After a successful send, `lines` is not cleared. Clicking Send again more than 1 second later re-posts the same invoice, which the server may record as a duplicate.
   - The request also has no `Content-Type` header, so the JSON body goes out as `text/plain`. A server that expects `application/json` may not parse it.

6. **`app.js:31-35`: the void request doesn't say which invoice to void.**
   - It posts to `/api/invoices/void` with no body, so the server can't tell which invoice is meant. It may void the wrong one, or reject the request.
   - Separately, `canVoid` only decides whether the click does anything on the client. The `user` object is hardcoded in the page and editable in dev tools, so the server must enforce the admin check itself.
   - I can't see the server from here, so I can't confirm either problem.

`escapeHtml` and the `render` output look correct: qty and price are numbers, and the client name is escaped for both text and attributes. `render()` also builds each link with `href="#"`, which jumps the page to the top on click. That's minor.