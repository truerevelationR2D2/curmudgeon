Review done and saved to `.critic/last-review.md`.

**BLOCK** · 1 Critical, 3 High, 4 Medium, 2 Low

I traced every finding by reading the code. Nothing was run, because the reviewer and verifier were denied Bash.

| # | Where | Impact | Defect |
|---|---|---|---|
| C1 | `guards.js:10` | Critical | `canVoid` uses `indexOf("admin")` as a boolean. Every non-admin may void, and an admin listed first is blocked. |
| C2 | `app.js:26` | High | Send has no network-failure handling and shows nothing on success. |
| C3 | `guards.js:18` | High | `validQuantity` accepts empty, zero, negative, fractional and Infinity quantities. |
| C4 | `guards.js:24` | High | `lastSend` is never assigned, so `tooSoon` never trips and a double click sends twice. |
| C5 | `app.js:8` | Medium (lowered from Critical) | `escapeHtml` leaves double quotes unescaped inside `title="..."`. The only input is the user's own, so the verifier called it self-XSS. |
| C6–C8 | `app.js:10`, `app.js:33`, `app.js:19` | Medium | Float total that doesn't match the rows shown; Void has no confirmation, invoice id or feedback; invalid input is dropped silently. |
| C9–C10 | `app.js:8`, `index.html:21` | Low | A client-name link that goes nowhere; the whole list is re-announced on every add. |

- **Medium findings not verified:** C6–C8 got no verifier verdict, so they stay at lower confidence.
- **Approximate figure:** one number in C6's failing case (the 0.005 rounding) is approximate. I couldn't run it.
- **Not checked:** the server routes `/api/invoices` and `/api/invoices/void`, including role enforcement, and live browser behaviour.
- **Files:** no project files were changed. The `.critic/` folder is Curmudgeon's own output.

To fix everything, run `/curmudgeon:review fix`. To fix one finding, run `/curmudgeon:fix patch [id]`.