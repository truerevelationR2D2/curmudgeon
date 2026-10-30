I found six bugs, all by reading the code; I didn't run anything or change any files. The files are `app.js`, `guards.js`, `index.html` and `styles.css`. I didn't read `styles.css`.

**1. `guards.js:10`: the admin check is inverted.**
- `user.roles.indexOf("admin")` returns `-1` when the role is missing, and `-1` is truthy. It returns `0` when "admin" is first in the list, and `0` is falsy.
- Failing input: the signed-in user in `app.js:2` is `roles: ["viewer","billing"]`. `canVoid` returns `true` for them, so they can void an invoice. A user with `roles: ["admin"]` gets `false` and cannot.
- The check should be `indexOf("admin") !== -1` or `includes("admin")`. The check also exists only in the browser, so the `/api/invoices/void` endpoint has to enforce it as well.

**2. `guards.js:17`: `validQuantity` accepts values that aren't valid quantities.**
- `!isNaN(qty)` is true for `""`, `" "`, `"-3"`, `"1.5"`, `"0"` and `"Infinity"`.
- Failing sequence: leave Quantity blank, enter price 5 and click "Add line". `Number("")` is `0`, so a line with qty 0 is added. Entering `-3` makes the total negative, and `Infinity` makes it `Infinity`.
- It should require a positive integer, for example `/^[1-9]\d*$/.test(qty)`.

**3. `guards.js:22-23` and `app.js:25-29`: the one-second send guard never works.**
- `lastSend` is initialised to 0 and never updated, so `tooSoon()` is always false. `app.js` also has no in-flight lock.
- Failing sequence: double-click "Send invoice". Two `POST /api/invoices` requests go out and the invoice is sent twice.
- `sentCount` is incremented but never read.

**4. `guards.js:5` (used at `app.js:8`): `escapeHtml` doesn't escape quotes, so there is an XSS hole.**
- The function escapes `&`, `<` and `>` but not `"` or `'`. The result goes into a `title="..."` attribute.
- Failing input: client name `x" onmouseover="alert(document.cookie)`. It breaks out of the attribute, and the handler runs when the mouse hovers over the link.
- It should also escape `"` as `&quot;` and `'` as `&#39;`.

**5. `app.js:16-20`: a whitespace-only client name is accepted.**
- The `required` attribute on the input passes for `"   "` because the value is non-empty. `.trim()` then turns it into `""`, and there is no check afterwards.
- Failing input: client `"   "`, qty 2, price 3. A line with a blank client is pushed, and the rendered list item shows nothing before the colon.

**6. `app.js:26-28`: the send handler has no network-error handling, and sends empty or unlabelled data.**
- `fetch` throws when the network fails or the server is unreachable. The `await` is outside any `try/catch`, so the rejection is unhandled and the user gets no "not sent" message. The same applies to the void handler at `app.js:33`.
- The body is a JSON string sent without `Content-Type: application/json`, so the browser labels it `text/plain`. A server that parses JSON by content type may reject or ignore it.
- Clicking "Send invoice" with no lines posts `[]`. `lines` is not cleared after a successful send, so the same lines can be sent again.

Lower-confidence note: `app.js:10` sums `qty * price` as floats, so the unrounded total can drift. For example, `0.1 * 3` is `0.30000000000000004`. `toFixed(2)` hides this in the display, but the posted line values are unaffected.