**BLOCK** · Counts: 0 Critical, 4 High, 5 Medium, 1 Low. I changed no source files. The full teardown is in `.critic/last-review.md`.

Three blind reviewers raised 38 findings; 10 survived the vote count and blind verification. The scripted scan had 0 FAIL rows. Nothing was executed by any agent, so every finding is traced by reading the code, not run.

**High**
- **Inverted void check:** `canVoid` in `guards.js:10` is inverted. Every non-admin can void, and an admin listed first can't. The reviewers rated it Critical; the verifier lowered it to High because the check runs only in the browser and no server code is in the repo.
- **Fetch failures and silent success:** send and void in `app.js:26` have no handling for a failed request, and success shows nothing.
- **Quantity check:** `validQuantity` in `guards.js:18` accepts empty, zero, negative, fractional and `Infinity` values.
- **Dead double-send guard:** `tooSoon` in `guards.js:24` never trips because `lastSend` is never assigned, so a double click sends two requests.

**Medium**
- **Lost lines:** invoice lines live only in memory and can't be edited or removed (`app.js:1`).
- **Float money:** the total is summed as floating point in the render function (`app.js:10`).
- **Silent validation:** invalid add-line input is dropped with no message (`app.js:19`).
- **Void has no confirmation:** it sits beside Send with the same styling (`app.js:31`).
- **Quote-breakout in the client name:** `escapeHtml` leaves quotes alone but its output goes inside `title="..."` (`app.js:8`). The reviewers rated it Critical; the verifier lowered it to Medium because the client name comes only from the user's own form field, so today it's self-XSS on hover.

**Low:** each line renders a dead `href="#"` link (`app.js:8`).

The five fixes worth the most per hour:
1. Use `includes("admin")` in `canVoid`, and enforce the rule on the server too.
2. Add an in-flight flag, a disabled button, a try/catch and a visible status to send and void.
3. Make `validQuantity` accept only a positive whole number.
4. Build the list with `textContent` instead of HTML strings.
5. Compute money in integer cents in one tested function.

**Not checked:**
- **Server side:** `/api/invoices` and `/api/invoices/void` aren't in the payload. Whether the server de-duplicates sends or enforces roles is unknown.
- **Browser behaviour:** nothing was driven in a real browser or screen reader.
- **Page checks:** the scan ran without `--page`, so none were run.
- **Outside reviewer:** none was used.
- **Variant hunt:** not run.

To fix every finding, run `/curmudgeon:review fix`. To fix one, run `/curmudgeon:fix patch [id]`.