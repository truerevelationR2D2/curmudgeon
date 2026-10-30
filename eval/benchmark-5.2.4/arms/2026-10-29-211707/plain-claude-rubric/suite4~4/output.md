I read all four files and traced the code by hand. I ran nothing and changed no files. I used the rubric 1 rows and sandbox scenarios 1–7 and 10 as the checklist.

Findings are ordered by impact.

1. **Critical: `guards.js:10`, the void permission check is inverted.**
   - `user.roles.indexOf("admin")` returns `-1` when the role is missing, and `-1` is truthy. It returns `0` when `"admin"` is the first role, and `0` is falsy.
   - For the signed-in user in `app.js:2` (`roles: ["viewer","billing"]`), `canVoid` returns `true`, so any non-admin can void an invoice.
   - A real admin with `roles: ["admin", ...]` gets `false` and can't void at all.
   - The check also runs only in the browser (`app.js:32`). Anyone can POST to `/api/invoices/void` directly, so the server has to enforce it too.

2. **Critical: `app.js:8`, XSS through the `title` attribute.**
   - `escapeHtml` (`guards.js:5`) escapes `&`, `<` and `>` but not `"` or `'`. The value is inserted into `title="..."`.
   - Entering the client `x" onmouseover="alert(1)` and adding the line renders `title="x" onmouseover="alert(1)"`. The script runs when the pointer moves over the link.
   - Entering `" autofocus onfocus="alert(1)` fails the same way.

3. **High: `guards.js:23-25` and `app.js:25-28`, the double-send guard never takes effect.**
   - `lastSend` is never set anywhere, so `Date.now() - 0 < 1000` is always false and `tooSoon()` never blocks.
   - Double-clicking "Send invoice" fires two POSTs with the same lines, which creates a duplicate invoice.
   - Nothing is cleared or disabled after a successful send, so a later click sends it again. `sentCount` is incremented but never read.

4. **High: `guards.js:18`, `validQuantity` accepts values that aren't a valid quantity.**
   - `isNaN("")` and `isNaN("  ")` are `false`, and `Number("")` is `0`. Leaving Quantity empty adds a line with qty 0.
   - `-5` is accepted, so a line with qty `-5` and price `10` makes the total `-50.00`.
   - `1.5`, `1e9` and `Infinity` are also accepted. A qty of `Infinity` makes the total `Infinity`.
   - `app.js:19` has a similar gap for price: `1e999` becomes `Infinity` and passes `price > 0`.

5. **High: `app.js:24-35`, failures and successes are not handled.**
   - `fetch` rejects on a network failure or offline. There's no `try/catch`, so the user gets an unhandled rejection and no message. Both the send and void handlers have this problem.
   - A successful send or void shows nothing, so the user can't tell it worked. This is why they re-click (see 3).
   - `app.js:26` sends `JSON.stringify(lines)` with no `Content-Type: application/json`. It goes out as `text/plain`, so a JSON-parsing server may reject it.
   - Send also works with `lines = []`, which posts an empty invoice.
   - Void POSTs with no body or invoice id, so the server can't know which invoice to void.

6. **Medium: `app.js:19`, invalid input is dropped silently.**
   - A bad quantity or price makes the handler `return` with no message and no field highlighted. The form isn't reset after a good add either.

7. **Medium: `app.js:16` with `index.html:14`, whitespace-only client names get through.**
   - The `required` attribute accepts `"   "`. Then `.trim()` gives `""`, and a line with a blank client is pushed and rendered as an empty link.

8. **Medium: `app.js:10-11`, money is calculated in floating point inside the render function.**
   - The rule lives in the view, which is a domain leak. `0.1 × 3` gives `0.30000000000000004`, and `toFixed` gives `1.005 → "1.00"`. Many lines can drift by a cent from what the server computes.

9. **Medium: `app.js:1`, `lines` lives only in memory.**
   - A refresh or closing the tab loses an unsent invoice. There's also no way to remove a mistaken line.

10. **Low: `app.js:8`, the client name is wrapped in `<a href="#">` that does nothing.**
    - It's a dead control that jumps to the top of the page and takes a tab stop. It should be plain text.

Nits, not counted:
- `app.js:27` and `app.js:34` use `alert`.
- `guards.js:2` calls the function a `canVoid` guard but returns a bare boolean.