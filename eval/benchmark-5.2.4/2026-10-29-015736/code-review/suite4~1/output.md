## Code review

Four bugs in `git diff main...HEAD`, all in new files. I read the diff directly and checked each one against the code. There are no CLAUDE.md files in the repo, so there was nothing to check for compliance. I did not launch the subagents the command describes, because the diff is 94 added lines across four files.

**1. `canVoid` lets non-admins void invoices and blocks some admins** (`guards.js:9-14`)
- `Array.prototype.indexOf` returns `-1` when the role is missing, and `-1` is truthy. It returns `0` when the role is first in the array, and `0` is falsy.
- The signed-in user in `app.js` is `sam`, with roles `["viewer", "billing"]`. `indexOf("admin")` is `-1`, so `canVoid` returns `true` and `sam` can void invoices.
- A user whose roles are `["admin", ...]` gets `0`, so `canVoid` returns `false` and they are blocked.
- The check is inverted for the "only admins" rule. It needs `user.roles.indexOf("admin") !== -1`, or `includes`.

**2. The double-send guard never fires** (`guards.js:22-25`, `app.js:24-29`)
- `lastSend` starts at `0` and nothing ever assigns it. `app.js` doesn't touch it, and the success path only does `sentCount += 1`.
- `Date.now() - 0` is always over 1000, so `tooSoon()` always returns `false`. Rapid clicks on "Send invoice" send duplicate invoices.
- `lastSend = Date.now()` needs to be set when a send starts.

**3. `validQuantity` accepts an empty quantity** (`guards.js:17-20`)
- `isNaN("")` is `false`, so an empty or whitespace-only quantity passes validation.
- The `qty` input has no `required` attribute. The submit handler then pushes a line with `qty: Number("") === 0`.
- The comment says "must be a number", but the line is silently added with quantity 0.

**4. `escapeHtml` doesn't escape quotes, which allows attribute injection** (`guards.js:4-6`, `app.js:8`)
- `escapeHtml` handles only `&`, `<` and `>`. `render()` also uses it inside a double-quoted attribute: `title="${escapeHtml(l.client)}"`.
- A client name such as `x" onmouseover="alert(1)` is not escaped, so it breaks out of the attribute and adds an event handler. This is script injection through the `client` field.
- Escaping `"` (and `'`) as `&quot;` and `&#39;` closes it.