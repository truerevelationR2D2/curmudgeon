## Code review: "Add the app"

I reviewed `git diff main...HEAD` and found four issues. Each was independently validated. Nothing was posted and no files were changed.

The repo has no CLAUDE.md files, so both compliance agents found nothing.

1. **`canVoid` is inverted** (`guards.js:10`, used at `app.js:32`).
   - `if (user.roles.indexOf("admin"))` treats the index as a boolean.
   - A user without the admin role gets -1, which is truthy, so they can void. The signed-in user, `sam`, has roles `["viewer","billing"]` and can void.
   - A user whose first role is `"admin"` gets 0, which is falsy, so they are refused.
   - Fix: `user.roles.includes("admin")`.
   - The check runs in the browser only. There is no server code in this diff, so I can't tell whether `/api/invoices/void` checks the role again.

2. **The double-send guard never blocks** (`guards.js:22-25`, used at `app.js:25`).
   - `lastSend` stays 0 and nothing ever updates it, so `tooSoon()` always returns false.
   - Two quick clicks on "Send invoice" post the invoice twice.
   - Fix: set `lastSend = Date.now()` right after the `tooSoon()` check, before the `await`.

3. **`escapeHtml` doesn't escape quotes** (`guards.js:5`, used at `app.js:8`).
   - Its output goes inside `title="..."` via `innerHTML`.
   - A client name like `x" onmouseover="alert(1)` adds an event handler.
   - In this diff the client name only comes from the user's own form field, so this is self-XSS with low impact for now. It becomes stored or cross-user XSS once client names load from anywhere else.
   - Fix: also escape `"` and `'`.

4. **`validQuantity` accepts bad quantities** (`guards.js:18`, used at `app.js:19-20`).
   - `!isNaN("")` is true, and the quantity input has no `required`, `min` or `type="number"` (`index.html:16`).
   - An empty quantity adds a line with quantity 0. A quantity of `-3` lowers the total. Both are sent to `/api/invoices`.
   - Fix: require a positive integer.