I found six bugs and a few smaller ones. I only read the code and ran nothing. The repo has four files (`app.js`, `guards.js`, `index.html`, `styles.css`), and `styles.css` is 5 lines.

## Bugs

1. **`guards.js:45` – the void check is inverted, so non-admins can void and admins can't.**
   - `indexOf("admin")` returns `-1` when the role is absent. `-1` is truthy, so the function returns `true`. When `"admin"` is the first role, `indexOf` returns `0`, which is falsy, so the function returns `false`.
   - Failing input: with the default `user = { roles: ["viewer","billing"] }` in `app.js:2`, `canVoid(user)` returns `true`. Clicking "Void invoice" (`app.js:32`) then POSTs the void.
   - Counter-case: `roles: ["admin"]` returns `false`, so a real admin is blocked. An admin who isn't first in the list (for example `["viewer","admin"]`) is allowed.
   - Fix: use `includes("admin")`, or compare `indexOf(...) !== -1`.
   - This is an authorization bypass. The check also runs only in the browser, so the server has to enforce it too.

2. **`guards.js:59` and `app.js:25` – the double-send guard never fires.**
   - `lastSend` is initialized to `0` and nothing ever assigns it. `Date.now() - 0` is always far above 1000, so `tooSoon()` always returns `false`.
   - Failing sequence: double-click "Send invoice". Two POSTs go out, and `sentCount` becomes 2.
   - There is also no in-flight lock. A second click while the first `fetch` is pending sends again even if the timestamp were set.

3. **`guards.js:53` – quantity validation accepts invalid values.** `!isNaN(qty)` coerces its argument to a number, so these all pass:
   - An empty or whitespace quantity: `""` or `"  "` becomes `Number("")`, which is `0`, and `app.js:20` pushes a line with qty 0.
   - Negative values: `"-5"` gives a line that reduces the total.
   - Fractions: `"2.5"`, even though the input has `inputmode="numeric"`.
   - Non-finite or odd values: `"Infinity"` and `"1e999"` make the total `Infinity`. `"0x10"` passes as 16.

4. **`guards.js:40` and `app.js:8` – attribute injection (XSS).**
   - `escapeHtml` doesn't escape `"` or `'`, but `app.js:8` puts its output inside `title="..."`.
   - Failing input: client name `x" onmouseover="alert(document.cookie)`. The rendered `<a title="x" onmouseover="...">` runs the script on hover.

5. **`app.js:16` and `app.js:19` – blank client name and infinite price get through.**
   - The HTML `required` attribute accepts `"   "`, and `.trim()` then makes it `""`. Nothing checks it, so a line is pushed with an empty client.
   - `price > 0` is true for `Infinity` (`"1e999"`), and `toFixed` then prints `"Infinity"`.

6. **`app.js:24-29` and `app.js:31-35` – the send and void handlers have gaps.**
   - There is no `Content-Type` header on either request. The send body is a JSON string with no `application/json` header, so a server that parses by content type will not read it.
   - Send posts even when `lines` is empty.
   - `lines` is never cleared after a successful send. A second click, or a later "Add line", resends the old lines as a duplicate invoice.
   - If the network fails, `fetch` rejects and the exception is unhandled. The user gets no alert, which is different from the `!res.ok` path.
   - Void shows no success feedback, and it posts no invoice id, so the server can't tell which invoice to void.

## Minor
- `app.js:10` sums floating-point values and only rounds at display (`toFixed`). Totals can drift, for example 3 × 0.1. Cents or a rounding step would avoid that.