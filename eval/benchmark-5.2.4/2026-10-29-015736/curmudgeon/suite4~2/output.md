**BLOCK** · Counts: 1 Critical, 3 High, 4 Medium, 3 Low

I changed no project files. The review wrote only the `.critic/` folder. Three blind reviewers raised 34 raw findings, which the script counted down to 11, and blind verifiers checked the 8 that needed it. The scripted scan found 0 FAIL. No finding was executed: reviewers' Bash was denied, so all are traced from the code.

1. **Critical, `guards.js:10`:** `canVoid` tests `indexOf("admin")` as a boolean, so it is inverted. The signed-in user's roles are `["viewer","billing"]` (`app.js:2`), so `indexOf` returns -1 and `canVoid` returns true. The void request goes out for a non-admin. A user whose roles are `["admin"]` gets 0 and cannot void.
2. **High, `app.js:26`:** Send has no handling for a failed network request and shows nothing on success. A rejected `fetch` goes unhandled. An empty list posts `[]`.
3. **High, `guards.js:18`:** `validQuantity` accepts blank, negative and Infinity quantities. A quantity of -5 at price 10 posts a -50 line.
4. **High, `guards.js:22`:** `lastSend` is never assigned, so `tooSoon()` never blocks. A double-click sends the invoice twice.
5. **Medium:**
   - Bad input in Add line is dropped silently (`app.js:19`).
   - Money is summed as floats, so a unit price of 0.004 shows "0.00" but contributes to a total of "0.01" (`app.js:10`).
   - Void has no confirmation, no invoice id and no success state (`app.js:33`).
   - `escapeHtml` skips double quotes but its output goes inside `title="..."` (`guards.js:5`, `app.js:8`). The reviewers rated this Critical. The verifier lowered it to Medium: the client name comes only from the user's own input and nothing is stored or loaded, so there is no path to another user. That changes the moment lines come from a server.
6. **Low:**
   - Lines are lost on refresh.
   - Each client name is a dead `#` link.
   - The whole list is a live region rebuilt on every add.

**Verifier line numbers.** Verifiers 1 and 2 cited `app.js` line numbers up to 59 and 51, but `app.js` has 35 lines. For the float-sum and Void findings, that left the script unable to confirm their evidence, so those two rank as "likely" instead of "confirmed". I re-traced both by hand against the real lines, and the behaviour holds.

**Not checked:**
- **Browser:** nothing was driven in a browser.
- **Server:** the code behind `/api/invoices` and `/api/invoices/void` isn't in the payload, so server-side role checks and idempotency are unknown.
- **Variant hunt:** I skipped it.
- **Contrast and screen reader:** judged from the code, not measured.

**Not reviewed:** nothing; all 4 files were read.

The teardown is in `.critic/last-review.md`, and the change map is in `.critic/change-map.md`.

To fix the findings, type `/curmudgeon:review fix`, or `/curmudgeon:fix patch [id]` for one finding.