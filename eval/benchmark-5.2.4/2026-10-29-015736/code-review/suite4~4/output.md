## Code review: `git diff main...HEAD` (1 commit, 4 new files)

I found 4 bugs. There were no CLAUDE.md files in the repo, so I checked bugs only. The diff is small, so I read it myself and didn't launch review subagents. Each finding below can be confirmed from the code shown.

**1. The void permission check is inverted (`guards.js:9-14`).**
- `canVoid` tests `user.roles.indexOf("admin")` as if it were a boolean.
- `indexOf` returns `-1` when "admin" is absent, and `-1` is truthy.
- So `canVoid` returns `true` for every user without the admin role. The signed-in user in `app.js` has roles `["viewer","billing"]`, so they can void.
- If "admin" is the first role, `indexOf` returns `0`, which is falsy, so that user is refused.
- The check needs `user.roles.indexOf("admin") !== -1` or `user.roles.includes("admin")`.

**2. The double-send guard never engages (`guards.js:23-25`, used at `app.js:24`).**
- `tooSoon()` compares against `lastSend`, but nothing ever assigns `lastSend`.
- It stays `0`, so `Date.now() - 0` is never below 1000 and `tooSoon()` always returns `false`.
- Double clicks on "Send invoice" therefore post the invoice twice.
- `lastSend = Date.now()` needs to be set when a send starts, or after it succeeds.

**3. `validQuantity` accepts values that aren't valid quantities (`guards.js:17-19`, used at `app.js:17-18`).**
- `isNaN("")` and `isNaN(" ")` are `false`, so an empty or blank Quantity field passes. `Number("")` is `0`, so a line with quantity 0 is added.
- Negative and fractional values like `"-3"` or `"1.5"` also pass. The input is meant to be numeric (`inputmode="numeric"`).
- The check should require a positive integer, for example `/^[1-9]\d*$/.test(qty)`.

**4. `escapeHtml` doesn't escape quotes, but it is used inside an HTML attribute (`guards.js:4-6`, used at `app.js:8`).**
- The client name goes through `escapeHtml` into `title="${escapeHtml(l.client)}"`.
- The function only escapes `&`, `<` and `>`. A client name such as `x" onmouseover="alert(1)` closes the attribute and injects an event handler, so this is XSS through the client field.
- `"` needs to become `&quot;`, and `'` should be escaped too.

I didn't flag the unused `sentCount` or the `alert()` calls. They're style issues, not correctness bugs.