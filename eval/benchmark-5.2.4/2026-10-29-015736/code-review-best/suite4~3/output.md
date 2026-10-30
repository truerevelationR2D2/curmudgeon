## Code review

Local PR "Add the app" (`git diff main...HEAD`): 4 new files, 94 lines. Nothing was posted and no files were changed.

**Issues found: 4.** All four were found by the bug agents and then confirmed by a separate validator. The two CLAUDE.md agents reported no issues, because the working tree has no CLAUDE.md.

1. **`canVoid` is inverted** (`guards.js:10-13`). `if (user.roles.indexOf("admin"))` treats `-1` (no admin role) as true and `0` (admin listed first) as false. The signed-in user in `app.js:2` has roles `["viewer", "billing"]`, so `canVoid` returns true and the guard at `app.js:32` lets the void request through. An admin listed first is refused. The fix is `user.roles.includes("admin")`. This is a browser-side check, and the diff doesn't show whether the server also enforces it.

2. **The double-send guard never blocks** (`guards.js:22-25`, used at `app.js:25`). `lastSend` is initialised to 0 and never assigned anywhere, so `tooSoon()` always returns false. A double click posts the invoice twice. The fix is to set `lastSend = Date.now()` when a send goes ahead.

3. **Zero, negative and blank quantities pass validation** (`guards.js:17-19`, used at `app.js:19`). `validQuantity` is `!isNaN(qty)`, so `""`, `"   "`, `"0"`, `"-5"`, `"1.5"`, `"1e3"` and `"Infinity"` all pass. The qty input at `index.html:16` has no `type=number`, `required` or `min`, so the browser doesn't block them either. A negative line lowers the invoice total (`app.js:10`) and `Infinity` makes it `Infinity`. That list is then POSTed.

4. **`escapeHtml` doesn't escape quotes, but its output goes inside `title="..."`** (`guards.js:5`, used at `app.js:8`). A client name like `x" onmouseover="alert(1)` breaks out of the attribute and runs script on hover. The validator found that only the person typing the name can trigger it, because `lines` is filled only from the form. So today this is self-XSS. It becomes stored XSS if lines are ever loaded from the server. The fix is to also escape `"` and `'`.

**Not flagged:**
- The unhandled `fetch` errors and the missing `Content-Type` header.
- The unused `sentCount`.
- The whitespace-only client name.
- The empty-lines send. These depend on input or state, or are quality concerns.

**Caveat:** three of the validators couldn't run `git diff` (Bash was denied) and read the files directly. One of them confirmed from the git log that all four files are new in this PR.