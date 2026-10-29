**BLOCK** · Counts: 1 Critical, 2 High, 4 Medium, 2 Low

This was a lite-tier review: one blind reviewer, with Critical and High findings checked by a blind verifier. The scripted scan reported 0 FAIL. I changed no project files; everything I wrote is under `.critic/`. The full teardown is in `.critic/last-review.md`, and the change map is `.critic/change-map.md`.

**Critical and High**
- **C1, Critical — `guards.js:10` (`F-8cd9cc61`):** the `canVoid` check is inverted. `indexOf("admin")` returns -1 for a non-admin, which counts as true. It returns 0 for an admin listed first, which counts as false. A user with roles `[viewer, billing]` can send the void request, and an admin with `["admin"]` is refused. Fix it with `includes("admin")` and enforce the same rule on the server.
- **C2, High — `guards.js:18` (`F-d6e40c52`):** `validQuantity` returns `!isNaN(qty)`, so it accepts empty, blank, 0, negative, fractional and Infinity values. An empty quantity adds a `0 × price` line, and -3 at price 2 posts a total of -6.00.
- **C3, High — `guards.js:22` (`F-f1df78e4`):** `lastSend` is never assigned, so `tooSoon()` is always false. Two quick Send clicks make two invoice POSTs.

**Medium and Low**
- **C4, Medium — `guards.js:5` (`F-12358b37`):** `escapeHtml` does not escape quotes, and `app.js:8` puts its output inside `title="..."`. The verifier lowered this from Critical. The client name comes only from the user's own form field today, so it is self-XSS. It would become stored XSS if shared data is ever loaded.
- **C5, Medium — `app.js:26` (`F-992fdd63`):** Send has no catch for a failed fetch, no success message, and it POSTs an empty invoice when there are no lines.
- **C6, Medium — `app.js:33` (`F-cfaf04a4`):** Void asks for no confirmation, sends no invoice id and shows no result.
- **U1, Medium — `app.js:19` (`F-88720124`):** invalid line input is dropped with no message.
- **U2, Low — `app.js:8` (`F-595e1a80`):** each client name is a link to `#` that does nothing useful.
- **U3, Low — `index.html:21` (`F-7a9add6f`):** `aria-live` on a list rebuilt with `innerHTML` may re-announce every line on each add. I inferred this and did not test it with a screen reader.

C5, C6 and U1 have no verifier verdict, because the lite tier verifies Critical and High only; their confidence is lowered to "possible". The other findings were not re-run through the quote check; the script's own quote check passed on all 9.

**Not checked**
- No server-side code was in the payload, so I can't say whether the server enforces the void role or de-duplicates sends.
- Contrast, 390 px width and 200% zoom were traced from the CSS only.
- I did not run the spot-check or the variant hunt.

**Next steps**
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only one.