## Code review

Four bugs found in `git diff main...HEAD`. I read the code directly, because this is a four-file, 94-line change with no CLAUDE.md files, and I haven't run it. Each bug follows from the code as written.

**1. `canVoid` is inverted, so non-admins can void invoices and admins can't** (`guards.js`, `canVoid`)
- `user.roles.indexOf("admin")` returns `-1` when the role is absent, and `-1` is truthy. It returns `0` when `"admin"` is the first role, and `0` is falsy.
- The signed-in user in `app.js` has roles `["viewer", "billing"]`. `indexOf` returns `-1`, so `canVoid` returns `true` and that user can void.
- An admin whose first role is `"admin"` gets `false`.
- The fix is `user.roles.indexOf("admin") !== -1`, or `includes("admin")`.
- This check is the only thing guarding the void button.

**2. `tooSoon()` never starts the throttle** (`guards.js`, `lastSend`/`tooSoon`; used in `app.js`)
- `lastSend` is initialised to `0` and nothing ever assigns to it. The send handler in `app.js` only does `sentCount += 1`.
- `Date.now() - 0` is always far above 1000, so `tooSoon()` always returns `false`.
- The "no second send within one second" guard never fires, and rapid clicks POST the same invoice repeatedly.
- The fix is to set `lastSend = Date.now()` when a send starts.

**3. `validQuantity` accepts empty and invalid quantities** (`guards.js`, `validQuantity`; used in `app.js`)
- `!isNaN(qty)` is `true` for `""`, `" "`, `"-5"` and `"1.5"`.
- An empty Quantity field (it has no `required` attribute) passes validation. `Number("")` is `0`, so a zero-quantity line is added.
- A negative quantity is accepted and reduces the total.
- The fix is to require a positive integer, for example `/^[1-9]\d*$/.test(qty.trim())`.

**4. Attribute injection (XSS) through the client name** (`guards.js` `escapeHtml`, used in `app.js` `render`)
- `escapeHtml` escapes only `&`, `<` and `>`. It leaves `"` alone.
- `render()` puts the result inside a double-quoted attribute: `title="${escapeHtml(l.client)}"`.
- A client name such as `x" onmouseover="alert(1)` closes the attribute and adds an event handler, which runs when the link is hovered.
- The fix is to also escape `"` as `&quot;` and `'` as `&#39;`.