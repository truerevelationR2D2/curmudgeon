I read all four files (`app.js`, `guards.js`, `index.html`, `styles.css`) and traced the code by hand. I did not run it in a browser, so every case below is "traced", not driven. I changed no files.

Impact scores follow `rubrics.md`: a failure shown as success, a wrong result or lost data is High or worse.

## High

**1. `app.js:26-29`: the send guard doesn't stop a duplicate invoice, and success is never shown.**
- `tooSoon()` (`guards.js:21-26`) only blocks a second click within 1 second of the first.
- Failing sequence: add one line, click **Send invoice**, and the server takes 3 seconds. Click again at 1.5 seconds and `tooSoon()` returns false, so a second POST goes out with the same lines.
- After a success only `sentCount` changes. `lines` is not cleared, nothing is shown, and the button stays enabled. A user who isn't sure it worked clicks again and sends a duplicate invoice.
- `sentCount` is never read anywhere.

**2. `app.js:26`: a network failure is reported as nothing at all.**
- `fetch` rejects on offline, DNS failure or abort. There is no `try/catch`, so only `!res.ok` is handled.
- Failing sequence: go offline and click **Send invoice**. The promise rejects unhandled, the user sees no message, and nothing was sent.
- `lastSend` was already set at `guards.js:24`, so a retry within 1 second is also silently dropped.
- The same applies to `app.js:32` (void).

**3. `app.js:10-11` against `app.js:8`: displayed lines don't add up to the displayed total.**
- Each line is shown rounded with `toFixed(2)`, but the total sums the raw `qty * price` and rounds once at the end. Prices of more than 2 decimals are accepted.
- Failing input: three lines with qty 1 and price `0.004`. Each shows `0.00`, but the total shows `0.01`.
- With price `0.1` and qty 3 the sum also carries float error (`0.30000000000000004`) before rounding. On an invoice, money must be computed in integer cents with one rounding rule.

**4. `app.js:19`: `Infinity` is accepted as a price.**
- `!(price > 0)` passes for `Number("Infinity")` and for `Number("1e999")`.
- Failing input: price `1e999`. The line shows `Infinity`, the total shows `Infinity`, and the POST body has `null` for the price, because `JSON.stringify(Infinity)` gives `null`. That sends a corrupt invoice.
- Qty of 22 or more digits gives about 1e21, and `toFixed` then returns exponent notation such as `1e+21`.

## Medium

**5. `app.js:16,19-20`: a whitespace-only client is accepted.**
- The HTML `required` attribute passes `"   "`, then `.trim()` produces `""` and no check follows.
- Failing input: client `"   "`, qty 1, price 5. A line with an empty client is added and shows as `: 1 × 5.00`, with an empty link.

**6. `app.js:19`: invalid input is dropped silently.**
- Failing input: qty `1.5`, `0` or `abc`, or price `-3`. The handler returns, and no message, focus change or `aria-invalid` appears.
- The user cannot tell why **Add line** did nothing.

**7. `app.js:26`: sending an empty invoice is allowed.**
- On first load, click **Send invoice**. This POSTs `[]`, and the server may create an empty invoice.

**8. `app.js:31-35` with `guards.js:10-12`: void is decided only in the browser, and it gives no feedback.**
- `user` is a hard-coded object in client code. Any visitor can run `user.roles.push("admin")` in the console, or POST to `/api/invoices/void` directly. The rubric's "client trusted to enforce limits" applies unless the server checks the role, which is not visible here.
- For `sam` (roles `viewer, billing`), clicking **Void invoice** does nothing and says nothing: a dead control.
- A successful void also shows nothing, and `lines` still holds the invoice.
- The request carries no invoice id (`app.js:32`), so the server cannot know which invoice to void.

**9. `index.html:21` with `app.js:7`: the whole list is re-announced on every add.**
- `aria-live="polite"` on a `ul` whose `innerHTML` is replaced each render makes a screen reader re-read every line each time.
- Failing sequence: with 50 lines, adding the 51st announces all 51.
- The work is also O(n) per add.

**10. `app.js:8`: a dead link on every row.**
- `<a href="#" title=…>` has no handler. It is keyboard-focusable and a Tab stop, and activating it jumps the page to the top and changes the URL to `#`.
- Failing sequence: Tab to a row's client link and press Enter.

## Low

**11. `app.js:14-22`: the form is not cleared after a successful add, and duplicates are easy.**
- A double-click on **Add line** with valid values pushes two identical lines (scenario 3, fast hands).
- Because the fields keep their values, the user can't tell that the add worked.

**12. `app.js:26`: no `Content-Type` header on the POST.**
- A string body defaults to `text/plain;charset=UTF-8`, so a JSON-parsing server may reject it or read it as empty.
- I can't see the server, so this is a likely failure rather than a proven one.

**13. `app.js:1`: all state is in memory only.**
- Failing sequence: enter lines and refresh, and every line is lost. There is no `pagehide` flush and no persistence (scenario 6).

## What holds
- `escapeHtml` (`guards.js:4-7`) covers `& < > " '` in both element and attribute context. Hostile input like `<img src=x onerror=alert(1)>` as a client name stays inert.
- `validQuantity` rejects `0`, `1.5`, `-1` and `abc`.
- `\d` in JavaScript is ASCII-only, so Unicode digits are rejected too.
- The load order of `guards.js` before `app.js` is correct.