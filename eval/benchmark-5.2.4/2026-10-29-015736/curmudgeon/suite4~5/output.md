**BLOCK** · Counts: 1 Critical, 3 High, 6 Medium, 2 Low

Review only: I changed no project files. The only new files are under `.critic/`. The full teardown is at `.critic/last-review.md`.

**Critical**
- `guards.js:10` — `canVoid` is inverted. Any non-admin can void, because `indexOf("admin")` returns -1, which is truthy. An admin listed first (index 0) is blocked. Confirmed 3/3.

**High**
- `app.js:26` — Send and Void have no `catch`, and Send gives no success feedback. An offline failure is silent.
- `guards.js:18` — `validQuantity` accepts empty, 0, -5, 1.5 and Infinity. A quantity of -5 at price 20 posts a -100.00 line.
- `guards.js:24` — `tooSoon` never blocks. `lastSend` is never assigned, so a double-click sends the invoice twice.

**Medium (6)**
- Draft lines live only in memory and can't be edited or removed.
- Each line's client name is a dead `href="#"` link.
- The total is a floating-point sum of unrounded prices.
- Invalid quantity or price is dropped with no message.
- Void is destructive, asks for no confirmation and names no invoice.
- `escapeHtml` doesn't escape `"`, but its output goes inside a double-quoted `title` attribute. The verifier lowered this from Critical: the only input is the user's own typing, so today it is self-XSS. It matters as soon as lines come from anywhere else.

**Low (2)**
- A whitespace-only client name passes `required` and is stored as an empty name.
- The live region is replaced wholesale on every add, so a screen reader re-reads the whole list.

**Process**
- Three blind reviewers raised 37 raw findings.
- 10 verification packets: 9 confirmed, 1 lowered, none raised.
- 3 single-vote findings were dropped. One of them was that the lines aren't cleared after a send.
- The variant hunt found nothing.

**Not checked**
- The server behind `/api/invoices` and `/api/invoices/void` isn't in the payload. Whether it re-checks roles, rejects negative quantities or de-duplicates sends is unknown.
- Every finding is traced by reading the code, not run. The reviewers' Bash calls were denied. The one scripted run, S001, clicked “Void invoice” and got “Failed to fetch”, which fits the Void finding but proves no defect.
- Axe couldn't run, so contrast and ARIA rules weren't machine-checked.

**Fixes worth the most per hour**
1. Invert `canVoid` and enforce the role on the server too.
2. Set `lastSend`, or an in-flight flag, and disable Send while it runs.
3. Validate quantity as a positive integer.
4. Catch and report failures on Send and Void, and confirm before Void.
5. Escape `"` in `escapeHtml`.

To fix everything, run `/curmudgeon:review fix`. To fix one finding, run `/curmudgeon:fix patch [id]`.