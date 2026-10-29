## Code review

I reviewed `git diff main...HEAD` ("Add the app": `app.js`, `guards.js`, `index.html`, `styles.css`). Three issues survived validation. Nothing was posted and no files were changed.

1. **`canVoid` tests the index instead of the presence of "admin"** (`guards.js:10`, used at `app.js:32`).
   - The code is `if (user.roles.indexOf("admin"))`. `indexOf` returns -1 when "admin" is missing, and -1 is truthy, so non-admins get `true`. An admin listed first gets index 0, which is falsy, so they are refused.
   - The hard-coded user in `app.js:2` has roles `["viewer", "billing"]`, so they pass the check and the void request goes out. This is the opposite of the "Only admins may void" comment.
   - The fix is `user.roles.includes("admin")`.
   - The diff has no server code, so I can't say whether the server also rejects a non-admin void.

2. **The double-send guard never fires** (`guards.js:22-24`, called from `app.js:50`).
   - `lastSend` is declared as `0` and never assigned anywhere. `Date.now() - lastSend < 1000` is therefore always false, and `tooSoon()` never blocks a send.
   - A fast double-click posts the invoice twice.
   - The send handler needs to set `lastSend = Date.now()`.

3. **`escapeHtml` doesn't escape quotes** (`guards.js:5`, used at `app.js:7-8`).
   - It replaces only `&`, `<` and `>`. Its output goes inside `title="..."` in markup assigned through `innerHTML`.
   - A client name like `x" onmouseover="alert(1)` closes the attribute and adds an event handler.
   - In this diff the client name comes only from the user's own form, so this is self-XSS. It becomes stored XSS only if server-provided client names are rendered through the same code later.
   - The fix is to also escape `"` and `'`.

There is no CLAUDE.md in the repo, so both compliance agents found nothing to check against.

I also noticed `validQuantity` accepts an empty string, but I dropped it because it depends on the input. Likewise for the missing `fetch` error handling and for lines not being cleared after a send.