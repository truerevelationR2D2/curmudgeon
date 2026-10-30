I read `rubrics.md` and `sandbox.md` first and used them as the checklist. Then I read all four files (`app.js`, `guards.js`, `index.html`, `styles.css`) and changed nothing. I traced the code and did not run it. Most findings need no browser. Where I'm relying on browser behavior I say so. Lines are per file.

## Critical / High

1. **`guards.js:45` – void permission check is inverted (broken access).**
   - **What's wrong:** `indexOf` returns `-1` when the role is absent, and `-1` is truthy. It returns `0` when `"admin"` is the first role, and `0` is falsy.
   - **Failing input:** the signed-in user in `app.js:2` is `roles: ["viewer","billing"]`, with no admin. `indexOf("admin")` is `-1`, so `canVoid` returns `true` and the Void click at `app.js:32` goes through.
   - **Reverse case:** a real admin with `roles: ["admin","viewer"]` gets `0`, so `canVoid` returns `false` and they are blocked.
   - **Also:** the check only runs in the browser, so the server must enforce it too.

2. **`app.js:16` and `app.js:8` with `guards.js:40` – `escapeHtml` leaves quotes alone, so the `title="…"` attribute can be broken out of (XSS).**
   - **Failing input:** a client name of `x" onmouseover="alert(1)` is stored as-is. `render()` emits `title="x" onmouseover="alert(1)"`. The handler fires when the link is hovered, which is the sandbox's hostile-input case (scenario 10).
   - **Fix direction:** escape `"` and `'` too.

3. **`guards.js:58-59` and `app.js:25-28` – the double-send guard never works.**
   - **What's wrong:** `lastSend` is initialised to `0` and never set. Nothing in `app.js` sets it, so `tooSoon()` is always `false`.
   - **Failing sequence:** double-click "Send invoice". Two POSTs go out with the same lines, which is a duplicate invoice.
   - **Related:** even without the throttle, `lines` is never cleared after a successful send. A second click later re-sends the same invoice.

4. **`guards.js:53` and `app.js:19` – `validQuantity` accepts values that aren't valid quantities.**
   - **What's wrong:** `isNaN("")` and `isNaN(" ")` are `false`, so an empty quantity passes and becomes `Number("") = 0`. `"-5"`, `"1.5"`, `"1e3"` and `"Infinity"` pass too.
   - **Failing input:** quantity `-5` with price `10` gives a line of −50.00 and lowers the total. Quantity `Infinity` makes the total `Infinity`, shown as "Infinity".
   - **Price:** `price > 0` at `app.js:19` also accepts `1e999`, which is `Infinity`.
   - **Impact:** wrong money on an invoice that is then sent.

5. **`app.js:26` and `app.js:33` – no `try/catch` around `fetch`, so a network failure is silent.**
   - **Failing sequence:** go offline and click Send. `fetch` rejects, nothing catches it, and the user sees nothing. They are never told the invoice wasn't sent, which is the "success or failure unreported" case. Void has the same problem.
   - **Success path:** a 200 response shows no feedback at all, only `sentCount += 1`, which is never displayed.

6. **`app.js:26` – empty or invalid invoices can be sent.**
   - **Failing sequence:** click Send with no lines. It POSTs `[]`.
   - **Also:** the request has no `Content-Type: application/json` header, so a server that reads JSON by content type may reject or mis-parse it.
   - **Void:** `app.js:33` POSTs void with no invoice id, so it can't say which invoice to void.

## Medium

7. **`app.js:16-20` – a whitespace-only client is accepted.** The `required` attribute accepts `"   "`. After `trim()` the client is `""`, there's no check on it, and the line is pushed with an empty name and an empty link.

8. **`app.js:10` – money maths in floats inside render code (domain leak).**
   - **What's wrong:** the maths is done in floats and sits in the view. Rounding is only done by `toFixed`.
   - **Failing input:** three lines of qty 1 at price `0.1` give `0.30000000000000004` before formatting. The shown total can differ by a cent from the sum of the displayed line amounts, for example 3 × 1.005. The rule belongs in one pure, tested function working in cents.

9. **`app.js:1` – state isn't persisted.** `lines` lives only in memory. A refresh or close mid-entry (scenario 6) loses every line. There is also no way to remove or edit a line, so one mistake means reloading and losing everything.

## Low

10. **`app.js:8` – `<a href="#">` is a dead control.** Clicking it jumps to the top of the page and does nothing else. It is a focusable control with no purpose.

I did not verify the CSS or contrast findings, since I found none.