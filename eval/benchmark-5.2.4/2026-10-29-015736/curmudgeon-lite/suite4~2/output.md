**BLOCK** · Counts: 1 Critical, 2 High, 7 Medium, 3 Low

I changed no project files; only `.critic/` was written. The lite tier ran one blind reviewer. Everything was traced from the code, and nothing was executed because the reviewer's sandbox refused Bash. The server side of `/api/invoices` and `/api/invoices/void` is not in the payload, so I couldn't check what it enforces.

**Critical and High (verifier confirmed all three):**
- **C1 `guards.js:10` (Critical):** `canVoid` is inverted. `indexOf("admin")` returns -1, which is truthy, so a viewer or billing user can void. An actual admin at index 0 is refused.
- **C2 `guards.js:18` (High):** `validQuantity` is just `!isNaN`. Empty, `-5`, `1.5` and `1e9` all pass, so a quantity of -5 at price 20 takes 100 off the total.
- **C3 `guards.js:24` (High):** `lastSend` is never updated, so the double-send guard never fires. A double-click posts the invoice twice.

**Medium:**
- **Verified, then lowered:** the `escapeHtml` quote-escaping gap (`guards.js:5`, used inside a `title="..."` attribute at `app.js:8`) was rated High and the verifier lowered it to Medium. The only source of client names is the user's own input today, so it is self-XSS. I haven't offered a fix for it, as the review rules require.
- **Not verified:** the other six Mediums got no verifier verdict and are kept at lower confidence. They are the client-side role literal, the `Infinity` price, the silent input rejection, the uncaught fetch rejection, no feedback after a send, and Void with no confirmation or invoice id.

**Low:** a dead `#` link on each client name, a whitespace-only client name, and the `innerHTML` rebuild on every add.

The scripted scan found 0 FAIL, and no browser page checks ran because no `--page` was given. The full teardown, with evidence and failing cases per finding, is in `.critic/last-review.md`. The change map is at `.critic/change-map.md`.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.