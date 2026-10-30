I read all four files and ran nothing. I found six bugs, listed by severity. Each is a failure of the code as written, and I haven't confirmed any of them in a browser.

1. **`app.js:24-29` and `guards.js:56-61` — the send guard is time-based and can let a duplicate invoice through.**
   - `tooSoon()` only blocks a second click within 1000 ms of the first. Nothing tracks whether a request is still in flight.
   - Sequence: add a line and click "Send invoice". If the server takes longer than 1 s to answer, click again at 1.5 s. The guard passes and `POST /api/invoices` runs twice with the same `lines`.
   - Even after a successful send, `lines` is never cleared (`app.js:28` only bumps `sentCount`). Clicking Send again 2 s later re-sends the whole invoice.

2. **`app.js:26` — a network failure is not handled.**
   - `fetch` rejects on a network error. There is no try/catch, so the `!res.ok` branch and its alert never run. The user sees no message and the console shows an unhandled rejection.
   - Sequence: go offline, add a line, click Send.
   - A smaller related effect: `tooSoon()` has already set `lastSend`, so a retry within 1 s after a failed send is silently ignored.

3. **`app.js:26` — the send can go out empty.**
   - Nothing checks `lines.length`. Loading the page and clicking Send immediately posts `[]`, which may create an empty invoice.

4. **`app.js:16-20` — a whitespace-only client name is accepted.**
   - The `required` attribute in `index.html:75` accepts `"   "` because the field is non-empty.
   - `trim()` then turns it into `""`, and nothing rechecks it. Enter client `"   "`, qty 1 and price 5, and the line is added. It renders as an empty, unclickable `<a>`.

5. **`app.js:18-19` and `app.js:10` — extreme prices and quantities are accepted.**
   - `Number("Infinity")` is `Infinity`, which passes `price > 0`. The total then shows "Infinity".
   - A huge quantity such as `99999999999999999999` passes `validQuantity` and loses precision as a float.
   - There is no upper bound on either field.

6. **`app.js:8` vs `app.js:10-11` — the displayed lines can disagree with the total.**
   - The total sums unrounded `qty * price`, while each line shows only the unit price to 2 decimals.
   - Sequence: add three lines of qty 1 at price 0.004. Each shows `0.00`, but the total shows `0.01`.
   - Float summing can also drift. For example, 0.1 × 3 gives 0.30000000000000004, which only the `toFixed` hides.

Two lower-confidence items:
- `app.js:26` sends a JSON string with no `Content-Type: application/json` header. It goes out as `text/plain`, and a JSON-parsing server may reject it or read an empty body.
- `canVoid` (`guards.js:45-47`) is a client-side check on a hard-coded `user`. If the server doesn't also enforce the role, anyone can call `/api/invoices/void` directly.
  - The void request also carries no invoice id, so the server can't tell which invoice to void.