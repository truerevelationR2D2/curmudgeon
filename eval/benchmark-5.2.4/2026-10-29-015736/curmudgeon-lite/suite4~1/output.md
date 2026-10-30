**BLOCK** · Counts: 1 Critical, 3 High, 3 Medium, 2 Low

I ran the lite tier on the four files (`app.js`, `guards.js`, `index.html`, `styles.css`) with one blind reviewer. I changed no project files. The only files written are Curmudgeon's own records under `.critic/`. The full teardown is saved at `.critic/last-review.md`.

Nothing was run in a browser and Node was blocked, so every finding is traced from the code, not executed. The server routes `/api/invoices` and `/api/invoices/void` aren't in the payload.

**Critical**
- **C1 `guards.js:10`:** `canVoid` tests `indexOf("admin")` as a boolean, so the admin rule is inverted. A `['viewer','billing']` user can void (`indexOf` returns -1, which is truthy). A real `['admin']` user can't (`indexOf` returns 0, which is falsy).

**High**
- **C2 `app.js:26`:** Send has no error handling for a network failure, shows nothing on success, and posts `[]` when there are no lines.
- **C3 `guards.js:18`:** `validQuantity` is `!isNaN(string)`. It accepts empty, negative, fractional and `Infinity` quantities. A quantity of -3 subtracts from the total.
- **C4 `guards.js:24`:** `lastSend` is declared but never assigned, so `tooSoon()` is always false. A double-click sends two POSTs.

**Medium**
- **C5 `app.js:10`:** the total is summed in floats from unrounded prices. Price 1.004 × 3 shows line "1.00" but total "3.01".
- **C6 `app.js:33`:** Void is irreversible, with no confirmation, no invoice id in the request, no feedback and no error handling.
- **U1 `app.js:19`:** an invalid line is dropped silently, with no message and no focus move.

**Low**
- **C7 `app.js:8`:** `escapeHtml` skips `"` but is used inside `title="..."`. The reviewer raised it as Critical. The verifier downgraded it to Low because it's self-XSS: the text only comes from the user's own form field and is never stored.
- **C8 `app.js:8`:** each client name is a dead `href="#"` link, and the whole live list is re-announced on every add.

Of the nine findings, the verifier confirmed four by trace (C1–C4) and downgraded one (C7). The other four (C5, C6, U1, C8) went unverified. The lite tier only verifies Critical and High, so they stay at "possible" confidence.

The scripted scan reported 0 FAIL. The page checks (axe, keyboard, layout, speed) were not run, because I passed no `--page`. Variant hunting is full-tier only and was not run either.

**Decision for you:** to fix these, `/curmudgeon:review fix` fixes all nine, or `/curmudgeon:fix patch [id]` fixes one. I'd start with C1, C3 and C4, since each is a one-line cause with a clear test.