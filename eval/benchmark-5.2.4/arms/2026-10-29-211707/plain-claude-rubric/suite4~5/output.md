I read `rubrics.md` and `sandbox.md` first. I used the code rubric and sandbox scenarios 1–7 and 10, plus bad arguments, since this is an interface payload. I traced the code by reading it and did not run it in a browser. Nothing was changed.

## Critical

**1. `guards.js:45` — `canVoid` lets everyone void except an admin at index 0.**
- **What is wrong:** `indexOf("admin")` returns `-1` when the role is absent, and `-1` is truthy. It returns `0` when `admin` is the first role, and `0` is falsy.
- **Failing input:** the signed-in user at `app.js:2` is `roles: ["viewer","billing"]`. `indexOf` gives `-1`, `canVoid` returns `true`, and the user clicks "Void invoice" and `app.js:33` POSTs the void. The reverse also fails: `roles: ["admin","viewer"]` gives `0`, so a real admin is refused.
- **Also:** the check runs only in the browser. Anyone can call `canVoid`, or POST to `/api/invoices/void`, from the console. The server has to enforce it (the "trust boundary" row).

**2. `guards.js:40` — `escapeHtml` does not escape quotes, so `app.js:8` is open to attribute injection.**
- **What is wrong:** the escaped client name goes into `title="…"`, but `"` is not escaped.
- **Failing input:** a client of `" onmouseover="alert(1)` or `" autofocus onfocus="…` produces `title="" onmouseover="alert(1)"`. The script runs when the user hovers or focuses the link, which is XSS.

## High

**3. `guards.js:58-60` — `tooSoon()` never throttles.**
- **What is wrong:** `lastSend` stays `0` forever because nothing assigns it, so `Date.now() - 0 < 1000` is always false. `app.js:25` therefore never blocks a send.
- **Failing input:** double-click "Send invoice". Two POSTs go out, which creates a duplicate invoice. The button is also never disabled while the request is pending.

**4. `guards.js:53` — `validQuantity` accepts values that are not valid quantities.**
- **What is wrong:** `isNaN` coerces its argument, so these all pass:
  - `""` or `"  "` become qty `0`.
  - `"-5"` becomes a negative quantity.
  - `"Infinity"` and `"1e999"` become `Infinity`.
  - `"0x10"` becomes 16.
  - `"1.5"` becomes a fractional quantity.
- **Failing input:** qty `-5` with price `10` adds a line and the total shows `-50.00`. Qty `Infinity` makes the total `Infinity` and `NaN` can follow, and that bad data is sent to `/api/invoices` at `app.js:26`. The price check at `app.js:19` has the same hole, since `Number("1e999")` is `Infinity` and passes `> 0`.

**5. `app.js:26-28` — a failed send is not reported.**
- **What is wrong:** `fetch` rejects on a network error or when offline, and there is no `try/catch`. The `await` throws, and the click handler's promise rejects unhandled. The user sees no message, so the failure is silent.
- **Failing input:** go offline and click "Send invoice". Nothing happens on screen.
- **Related:** a successful send shows no confirmation. `sentCount` is incremented but never displayed or used.
- **Related:** `lines` is not cleared after a send, so the user can send the same invoice again.
- **Related:** an empty `lines` array can be sent (clicking Send with no lines), which creates an empty invoice.

**6. `app.js:33-34` — the void request has no target and no catch.**
- **What is wrong:** the POST sends no invoice id and no body, so the server cannot know which invoice to void. There is no confirmation step on a destructive action. A `fetch` rejection is unhandled, as in finding 5.
- **Failing input:** click "Void invoice" while offline. Nothing is shown.

**7. `app.js:19` — invalid input is rejected silently.**
- **What is wrong:** `return` with no message.
- **Failing input:** type qty `abc` (or a price of `0`) and press Add line. Nothing happens, with no error and no focus change. The form's `required` only covers the client field.
- **Failing input:** a client of `"   "` passes `required` (it is not empty) but is trimmed to `""` at `app.js:16`, so a line with a blank client is pushed.

## Medium

**8. `app.js:8` — `<a href="#">` is a dead link.**
- **What is wrong:** it does nothing useful, but it jumps the page to the top and appends `#` to the URL. It is a tab stop that does nothing.
- **Failing input:** tab to a line and press Enter, and the page scrolls to the top.

**9. `app.js:1,20` — there is no persistence.**
- **What is wrong:** `lines` lives only in memory.
- **Failing input:** add five lines and refresh the page, and all five are lost (sandbox scenario 6).

**10. `app.js:10-11,8` — money is handled as floats.**
- **What is wrong:** `toFixed(2)` rounds binary floats, and the raw float price is sent to the server.
- **Failing input:** price `1.005` shows as `1.00`. The server receives `1.005`, which may not match what the user saw.
- **Also:** the sum is not rounded per line, so the displayed lines may not add up to the displayed total.

**11. `app.js:26` — the send has no `Content-Type` header.**
- **What is wrong:** the body is a JSON string with no header, so `fetch` sends it as `text/plain`. A server that parses JSON by content type will reject it.
- **Failing input:** with such a server, every send returns a 4xx.

## Low

**12. `index.html:81` — `aria-live` on the whole `<ul>`.** `render()` rewrites the list each time, so the screen reader may re-read every line on each add.

**13. `app.js:20` — the form is never reset after adding a line.** The user has to clear the fields by hand to add the next line.