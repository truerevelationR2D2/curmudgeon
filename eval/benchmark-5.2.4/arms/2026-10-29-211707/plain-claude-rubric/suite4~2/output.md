I read all four files, which are the whole repo (94 lines), against rubric 1 (code) and sandbox scenarios 1–7 and 10. I traced the code and ran nothing, and I changed no files.

**Critical**

1. **`guards.js:10` – `canVoid` lets everyone except a first-position admin void invoices.**
   - `indexOf` returns `-1` when the role is absent. `-1` is truthy, so the check passes.
   - `indexOf` returns `0` when `"admin"` is the first role. `0` is falsy, so that admin is refused.
   - Failing input: the file's own user, `roles: ["viewer","billing"]`, gets `true` and the Void click POSTs. A user with `roles: ["admin"]` gets `false` and can't void.
   - The check also runs only in the browser (`app.js:32`). The server must enforce it too, and nothing here shows that it does.
   - Fix: use `roles.includes("admin")`.

2. **`app.js:8` with `guards.js:5` – the attribute-injection XSS.**
   - `escapeHtml` doesn't escape `"` or `'`. `app.js:8` puts the result inside `title="..."`.
   - Failing input: enter the client `" onmouseover="alert(1)" x="`, then add a line. The output is `title="" onmouseover="alert(1)" x=""`, and hovering the link runs the script.
   - Use a client with `autofocus onfocus=...` for a no-interaction variant.

**High**

3. **`guards.js:22-24` with `app.js:25` – `tooSoon` never blocks anything.**
   - Nothing ever assigns `lastSend`, so it stays 0. `Date.now() - 0` is always at least 1000, so `tooSoon()` is always false.
   - Failing sequence: double-click "Send invoice". Two POSTs go out, so the invoice is created twice.
   - `app.js:28` also doesn't clear `lines`, so a later click resends the same lines.

4. **`guards.js:18` – `validQuantity` accepts values that aren't valid quantities.**
   - `isNaN("")` and `isNaN("  ")` are false, so a blank quantity passes and becomes qty 0.
   - `"-3"` passes, which lets one line cancel another. Add qty 10 at 5.00, then qty -10 at 5.00, and the total is 0.00.
   - `"Infinity"` and `"1e999"` pass, so the total becomes `Infinity`.
   - `"1.5"` and `"0x10"` pass, although the field is meant to be an integer.

5. **`app.js:26` and `app.js:31` – a rejected `fetch` has no handler.**
   - Failing sequence: go offline, then click Send. `fetch` rejects, the async handler throws and nothing is shown.
   - Nothing else is shown either way. A successful send or void gives no confirmation. Only `!res.ok` alerts.
   - Send with zero lines is allowed and POSTs `[]`.

**Medium**

6. **`app.js:19` – invalid input is dropped with no message.**
   - Failing input: type `abc` as the quantity and click "Add line". Nothing happens and nothing is announced.
   - A price of `1e999` passes `price > 0`, and a price with a comma such as `1,50` fails silently.

7. **`app.js:16` – a blank client can be added.**
   - The `required` attribute accepts `"   "`, then `.trim()` makes it `""`. A line with an empty client name is added.

8. **`app.js:10-11` and `app.js:8` – floating-point money and a total that can disagree with the lines.**
   - Failing input: three lines of qty 1 at price 1.005. Each line shows `1.00` (`1.005.toFixed(2)` is `"1.00"`), but the total is `3.015.toFixed(2)`, which also gives `"3.01"` or `"3.02"` depending on float error.
   - The total can therefore differ from the sum of the displayed lines. The fix is to use integer cents.

**Low**

9. **`app.js:8` – the `<a href="#">` is a dead control.**
   - It does nothing except jump the page to the top. It is also a tab stop with no purpose.
   - A client name is plain text, so use a `<span>`.

I found no way to remove or edit a line, and a bad entry stays until the page reloads. The void request in `app.js:33` carries no invoice id, so the server can't know which invoice it applies to. I counted both as design gaps, not failing cases.