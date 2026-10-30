I read all four files (95 lines) and ran nothing. Here are the bugs, most serious first.

1. **`app.js:24-29` with `guards.js:56-61`: the duplicate-send guard is a timer, not an in-flight check.**
   - `tooSoon()` only blocks a second click within 1 second.
   - To fail: click "Send invoice" while the server takes more than 1 second (slow network). Click again at about 1.5 seconds. Both POSTs go out, so the invoice is created twice. Nothing disables the button or records that a request is pending.
   - `sentCount` and `lines` are never reset or checked after a successful send. Clicking "Send invoice" again at any later time re-posts the same lines as a new invoice.

2. **`app.js:25-27` with `guards.js:58-59`: a failed send locks the retry for 1 second.**
   - `tooSoon()` writes `lastSend` before the request runs.
   - To fail: the server returns 500, the alert shows, and the user clicks again within 1 second. The click is silently ignored with no message.
   - `fetch` itself can reject (offline, DNS failure). Line 26 has no try/catch, so there is no alert and an unhandled rejection. The user gets no feedback at all.

3. **`app.js:26`: the POST sends JSON with no `Content-Type` header.**
   - The body is a string, so the browser sends `text/plain;charset=UTF-8`.
   - To fail: any server that only parses `application/json` bodies (Express `express.json()`, for example) gets an empty or unparsed body and rejects or misreads it. I didn't see the server, so this one depends on it.

4. **`app.js:16-20`: whitespace-only client names are accepted.**
   - The `required` attribute in `index.html:75` passes a value like `"   "`.
   - To fail: type three spaces as the client, set quantity 1 and price 5, and submit. `trim()` makes the client `""`, and line 19 never checks it. A line with a blank client is added, rendering as `: 1 × 5.00`.

5. **`app.js:18-19`: `Infinity` and extreme values pass the price check.**
   - `Number("Infinity") > 0` is true, and so is `Number("1e999")`, which is `Infinity`.
   - To fail: enter price `Infinity` or `1e999`. The line is added, the total becomes `Infinity`, and an invoice with that amount can be sent. The check should use `Number.isFinite`.

6. **`app.js:8` and `app.js:10-11`: money is handled as floats with no rounding rule.**
   - Prices are not limited to 2 decimals, so the displayed values can disagree with the stored ones.
   - To fail: add price `0.004` with quantity 1. The line shows `0.00` while the data holds `0.004`. Add `1.005`, which displays `1.00` because `toFixed` follows the float value.
   - With many lines, the total is a float sum that doesn't match the sum of the rounded lines.

7. **`app.js:31-35` with `guards.js:45-47`: a denied void gives no feedback.**
   - `canVoid` only checks a client-side role list. Server authorization isn't visible here, and the client check is not a security control.
   - For the hard-coded user `sam` (roles `viewer` and `billing`), the "Void invoice" button always returns silently at line 32. The user gets no message and no disabled state.
   - The request at line 33 also carries no invoice identifier, so an admin's click cannot say which invoice to void.