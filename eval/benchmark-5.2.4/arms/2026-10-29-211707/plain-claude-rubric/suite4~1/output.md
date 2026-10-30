I found 8 bugs, all by reading the code. I ran nothing, and I changed no files.

I used `rubrics.md` and `sandbox.md` as the checklist. The payload is a UI, so I traced scenarios 0–10, and none of them was driven.

**High or worse**

1. **`app.js:8` (with `guards.js:5`) – XSS through an unescaped quote.**
   - `escapeHtml` escapes `&`, `<` and `>` but not `"`.
   - The client value is put inside `title="..."`, so a quote breaks out of the attribute.
   - Failing input: Client = `" onmouseover="alert(1)` and a valid qty and price. The rendered `<a title="" onmouseover="alert(1)">` runs the script when the user hovers over the link.
   - **Critical** (security).

2. **`guards.js:10` – `canVoid` is inverted.**
   - `indexOf` returns `-1` when the role is missing, and `-1` is truthy. It returns `0` when `"admin"` is first in the list, and `0` is falsy.
   - The app's own user `{roles:["viewer","billing"]}` gets `-1`, so `canVoid` returns true and a non-admin can void.
   - A user with `roles:["admin"]` gets `0`, so `canVoid` returns false and the admin is blocked.
   - The check also runs only in the browser (`app.js:32`), so anyone can skip it by posting to `/api/invoices/void` directly. The server has to enforce it.
   - **Critical** (broken access).

3. **`guards.js:22-25` and `app.js:25-28` – `tooSoon` never fires.**
   - `lastSend` is never assigned, so `Date.now() - 0` is always greater than 1000 and `tooSoon()` is always false.
   - There is also no in-flight lock.
   - Failing sequence: double-click "Send invoice". Two POSTs go out, and the invoice is sent twice.
   - **High** (double submit).

4. **`guards.js:17-19` (used at `app.js:19`) – `validQuantity` accepts bad quantities.**
   - `isNaN("")`, `isNaN(" ")`, `isNaN("-5")`, `isNaN("1.5")`, `isNaN("1e3")` and `isNaN("0x10")` are all false, so all of them pass.
   - Failing input: qty empty, or `" "`, gives `Number("")` = 0, so a zero-quantity line is added.
   - Failing input: qty `-5` with price 10 adds a line of −50 and lowers the total.
   - Failing input: qty `1.5` is accepted even though the field says `inputmode="numeric"`.
   - **High** (wrong money result).

5. **`app.js:26-27` and `app.js:33-34` – `fetch` failures are not caught, and successes are silent.**
   - If the network is offline, `fetch` rejects and the click handler throws an unhandled rejection. The user sees nothing, which is a failure that looks like nothing happened.
   - The success path never tells the user either, and it never clears `lines`. Clicking Send again after a success re-sends the same lines.
   - Send is also allowed with zero lines.
   - Void shows no confirmation on success, and the user can't tell a void happened.
   - Failing sequence: go offline and click Send. No message appears.
   - **High**.

6. **`app.js:19` and `app.js:11` – no upper limit on price, and it breaks the total.**
   - Failing input: price `1e400` gives `Infinity`, which passes `price > 0`.
   - The line then shows "Infinity" and the total becomes "Infinity". Any later line keeps it at Infinity.
   - **Medium**.

**Medium or lower**

7. **`app.js:19-20` and `app.js:16` – rejected input gets no message, and whitespace-only clients are accepted.**
   - A rejected line just returns, with no message, so the user doesn't know why "Add line" did nothing.
   - The native `required` check passes `"   "`, but `trim()` then makes it `""`. A line is pushed with an empty client.
   - Failing input: Client = three spaces, qty 1, price 5. The result is an unnamed line.
   - The form also isn't reset after a successful add.
   - **Medium**.

8. **`app.js:10` – money is summed as floats, and the line text and total can disagree.**
   - Each line shows `price.toFixed(2)`, but the total is computed from the unrounded price.
   - Failing input: price `1.005`, qty 3 shows "1.00" per unit, the line total is 3.015, and the total displays "3.01" (or "3.02"). A client checking 3 × 1.00 gets a total that doesn't match.
   - A fix is to use integer cents.
   - **Medium**.

Also, in `app.js:8` the `<a href="#">` is a dead link. Clicking it jumps the page to the top and does nothing else. This is a Nit.