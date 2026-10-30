## Code review: `git diff main...HEAD` (commit 5f2ac3a)

I read the diff directly (4 new files, 94 lines) instead of launching agents. The change is small, and there is no CLAUDE.md or PR to check. I found four bugs, and each follows from the code as written.

**1. `canVoid` is inverted, so non-admins can void and admins can't** (`guards.js:9-14`)
- `user.roles.indexOf("admin")` returns `-1` when the role is missing, and `-1` is truthy.
- It returns `0` when `"admin"` is the first role, and `0` is falsy.
- The signed-in user in `app.js` has `["viewer", "billing"]`, so `canVoid` returns `true` for them, which defeats "Only admins may void an invoice."
- A user whose first role is `"admin"` is refused.
- Fix: `return user.roles.includes("admin");`

**2. `tooSoon` never records a send, so the one-second guard never fires** (`guards.js:22-25`, `app.js:24`)
- `lastSend` is initialised to `0` and never assigned. `Date.now() - 0` is always far above 1000, so `tooSoon()` always returns `false`.
- Double-clicking "Send invoice" posts the invoice twice.
- Fix: set `lastSend = Date.now()` when a send starts. `sentCount += 1` is the only state a send updates now.

**3. `escapeHtml` doesn't escape quotes, so a client name can inject attributes** (`guards.js:4-6`, used at `app.js:9`)
- The client name is placed inside `title="..."`.
- A name such as `x" onmouseover="alert(1)` closes the attribute and adds an event handler.
- Fix: also escape `"` as `&quot;` and `'` as `&#39;`.

**4. `validQuantity` accepts empty and non-integer values** (`guards.js:17-19`, `app.js:17`)
- `isNaN("")` is `false`, because `""` converts to `0`. Leaving Quantity blank therefore passes validation and adds a zero-quantity line. The `qty` input has no `required` attribute to catch it.
- Negative and fractional values such as `-3` or `1.5` also pass, though the input is meant to be numeric (`inputmode="numeric"`).
- Fix: `return /^[1-9]\d*$/.test(qty);`