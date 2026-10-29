## Code review

I reviewed `git diff main...HEAD` (one commit, 4 new files). There is no CLAUDE.md in the repo, so I checked bugs only. I read the diff directly instead of launching subagents, because it is only 94 lines. I did not run it.

Four issues found:

1. **`canVoid` is inverted** (`guards.js:9-14`).
   - `user.roles.indexOf("admin")` returns `-1` when the role is absent, and `-1` is truthy.
   - It returns `0` when `"admin"` is the first role, and `0` is falsy.
   - So every non-admin, including the `["viewer", "billing"]` user in `app.js`, is allowed to void. An admin listed first is refused.
   - Fix: `return user.roles.indexOf("admin") !== -1;`, or `user.roles.includes("admin")`.

2. **`tooSoon` never rate-limits** (`guards.js:22-25`).
   - `lastSend` is initialised to `0` and never assigned.
   - `Date.now() - 0` is always far above 1000, so `tooSoon()` always returns `false`.
   - The "no second send within one second" guard in the send handler (`app.js:26`) does nothing, and double-clicks send duplicate invoices.
   - `app.js` also never records the send time.
   - Fix: set `lastSend = Date.now()` when a send starts.

3. **`escapeHtml` doesn't escape `"`, but its output goes inside `title="..."`** (`guards.js:4`, used at `app.js:8`).
   - A client name such as `" onmouseover="alert(1)` closes the attribute and injects an event handler.
   - The client name is free text from the form.
   - Fix: also replace `"` with `&quot;` (and `'` with `&#39;`).

4. **`validQuantity` accepts an empty quantity** (`guards.js:17-19`, called at `app.js:18`).
   - `isNaN("")` is `false`, because `Number("")` is `0`.
   - Leaving Quantity blank passes validation, so a line with qty `0` is added.
   - Negative and fractional values also pass, although the field is marked `inputmode="numeric"`.
   - Fix: parse the value first, for example `Number.isInteger(Number(qty)) && Number(qty) > 0` after rejecting an empty string.