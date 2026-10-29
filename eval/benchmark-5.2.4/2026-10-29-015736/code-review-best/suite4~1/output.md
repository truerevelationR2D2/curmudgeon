## Code review: "Add the app"

I found three issues, and the validation agents confirmed all three. Nothing was posted and no files were changed. The CLAUDE.md compliance agents found nothing because the repo has no CLAUDE.md.

1. **`canVoid` gets the admin check backwards** (`guards.js:10`, bug and authorization).
   - `if (user.roles.indexOf("admin"))` tests the index number as true or false, not whether "admin" is present.
   - A user with no admin role gets `-1`, which counts as true, so they can void invoices. The hard-coded user in `app.js:2` has roles `["viewer", "billing"]`, so it passes.
   - A user whose first role is "admin" gets `0`, which counts as false, so they are refused.
   - This contradicts the comment "Only admins may void an invoice."
   - Fix: use `user.roles.includes("admin")` or `indexOf("admin") !== -1`.

2. **`tooSoon` never blocks a second send** (`guards.js:22-25`, used at `app.js:25`, bug).
   - `lastSend` starts at `0` and nothing ever updates it.
   - `Date.now() - lastSend` is therefore always far above 1000, and `tooSoon()` always returns false.
   - A quick double-click posts the invoice twice.
   - Fix: set `lastSend = Date.now()` when a send starts, not after the request returns.

3. **`escapeHtml` doesn't escape quotes** (`guards.js:4-5`, used in `app.js:8`, bug and security).
   - It escapes only `&`, `<` and `>`, but its output goes inside `title="..."` and is assigned through `innerHTML`.
   - Any `"` in the client name ends the attribute early. A name like `Acme "West" Ltd` breaks the markup, and `x" onmouseover="alert(1)` injects an event handler.
   - In this PR the name comes only from the user's own form, so today this is self-XSS. It becomes stored XSS if `lines` is ever filled from shared data.
   - Fix: also escape `"` as `&quot;` and `'` as `&#39;`.

The validator for issue 1 couldn't run `git diff` and read `guards.js` directly. It judged the bug introduced by this PR because the PR adds the file.

The agents saw other problems and left them out because they depend on input or on the server, which isn't in this PR:
- An empty or negative quantity passes `validQuantity`.
- The POST requests have no `Content-Type` header.
- The `fetch` calls have no error handling.
- `sentCount` is never read.