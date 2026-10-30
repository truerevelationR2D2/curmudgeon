I found six bugs and changed no files. I read all four files but did not run the page. I checked the rounding example (item 6) in Node.

1. **`app.js:25-26` with `guards.js:56-61`: the double-send guard is a timer, not an in-flight check.**
   - `tooSoon()` only blocks clicks within 1 s of the previous one. The request has no in-flight lock.
   - Failing input: on a slow connection (more than 1 s), click "Send invoice", wait 1.1 s, click again. Both POSTs go out and the server gets a duplicate invoice.
   - The timestamp is also set before the request succeeds. If the first send fails (`!res.ok`, alert shown) and the user clicks Retry within 1 s, the retry is dropped silently with no message.

2. **`app.js:26-28`: a network failure is never handled.**
   - `fetch` rejects when the network is down, the request is aborted or the server is unreachable. The `await` has no try/catch.
   - Failing sequence: go offline and click Send. The handler throws an unhandled promise rejection, the user sees no alert and `sentCount` is not updated. The `!res.ok` branch only covers HTTP errors.
   - The same applies to the void handler at `app.js:33`.

3. **`app.js:16-20`: a whitespace-only client is accepted.**
   - `required` on `#client` (`index.html:75`) only checks that the field is non-empty. `"   "` passes it.
   - `.trim()` then makes the client `""`, and nothing checks it afterwards. Type `"   "`, qty `1`, price `5`, submit. A line with an empty client is pushed and rendered as `<a> </a>: 1 × 5.00`.

4. **`app.js:19`: `Infinity` passes the price check, and huge quantities pass the quantity check.**
   - `Number("Infinity") > 0` is true.
   - Price `Infinity`, qty `1` gives a line of `Infinity` and a total of `Infinity`.
   - Price `1e999` also becomes `Infinity`.
   - `validQuantity("99999999999999999999")` is true, so the quantity is stored as `1e20` and the line total loses precision. `Number.isFinite` and `Number.isSafeInteger` checks are missing.

5. **`app.js:26`: an empty invoice can be sent, and the body is sent as `text/plain`.**
   - With no lines added, clicking Send posts `[]` to `/api/invoices`.
   - `body` is a JSON string with no `Content-Type: application/json` header, so `fetch` labels it `text/plain;charset=UTF-8`. A server that parses JSON by content type will reject or ignore it.

6. **`app.js:8` and `app.js:10-11`: money is handled in floats, so line amounts and the total can disagree.**
   - Three lines of qty 1 at price 0.005 display as `0.01 × …`. The total is 0.015, shown as `0.01`, while the per-line values add up to 0.03.
   - Similarly, `1.005.toFixed(2)` gives `"1.00"`. The displayed amounts and the total round independently, so an invoice can show a total that doesn't match its lines. The unit price and each line's amount should be kept in integer cents.

One more concern, which I can't confirm from this folder:
- `app.js:32` with `guards.js:45-47`: only the browser checks that the user is an admin. `user` is a client-side constant, so anyone can edit it or POST to `/api/invoices/void` directly. This is only safe if the server enforces the role itself.
- The void request also names no invoice, so it is unclear what gets voided.