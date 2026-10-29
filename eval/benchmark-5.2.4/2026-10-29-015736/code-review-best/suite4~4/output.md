## Code review

I reviewed the local change (`git diff main...HEAD`, "Add the app"). Nothing was posted and no files were changed. Four files were added: `app.js`, `guards.js`, `index.html` and `styles.css`.

Three issues were found, and a separate Opus validator confirmed each one.

1. **Void permission check is inverted** (`guards.js:10`, used at `app.js:32`).
   - The check is `if (user.roles.indexOf("admin"))`, which treats `-1` (not found) as true and `0` (admin listed first) as false.
   - The user in `app.js:2` has roles `["viewer", "billing"]`, so they pass the check and can void invoices.
   - An admin whose first role is "admin" is refused.
   - Use `includes("admin")` or `indexOf("admin") !== -1`.
   - The check runs only in the browser. Any server-side check is not in this PR.

2. **Double-send guard never fires** (`guards.js:22-24`, called at `app.js:25`).
   - `lastSend` starts at `0` and nothing ever updates it.
   - `Date.now() - 0 < 1000` is always false, so `tooSoon()` always returns false.
   - Two clicks within a second both POST to `/api/invoices`.

3. **`escapeHtml` doesn't escape quotes, but its output goes inside `title="..."`** (`guards.js:5`, used at `app.js:8`, which assigns the result to `innerHTML`).
   - A client name like `x" onmouseover="alert(1)` breaks out of the attribute and adds an event handler.
   - In this PR the client name comes only from the user's own form field, so it is self-XSS today.
   - It becomes stored or cross-user XSS once `lines` is filled from shared data.
   - Escape `"` and `'` as well, or build the elements with DOM APIs.

**Not flagged:** `validQuantity` accepts an empty, negative or fractional quantity. Whether that is a bug depends on what input a user gives, so it did not meet the high-signal bar.

**CLAUDE.md compliance:** the repo has no CLAUDE.md files, so both compliance agents found nothing to check against.

**Process note:** the step 2 haiku agent couldn't run Bash, so I listed the changed files and searched for CLAUDE.md files myself. I also skipped the step 1 agent, as the instructions said to continue.