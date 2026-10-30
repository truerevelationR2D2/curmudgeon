**BLOCK** · Counts: 1 Critical, 3 High, 5 Medium, 2 Low

This was a deep, review-only run on `app.js`, `guards.js`, `index.html` and `styles.css`. It changed no source files, only the review's own `.critic/` output. The full teardown is saved in `.critic/last-review.md`.

Three blind reviewers raised 35 raw findings. After merging and verification, 11 remain: 8 confirmed outright, 1 lowered from Critical to Medium, and 2 Low untested. Three single-vote findings were dropped. The scripted scan had 0 FAIL, but no page was given, so every browser check is n/a. A variant hunt found none.

**What matters**
1. **Critical, `guards.js:10`:** `canVoid` uses `indexOf("admin")` as a yes/no test, so it is inverted. A viewer/billing user can void, and a lone admin is refused. One reviewer drove this in Chromium.
2. **High, `app.js:26`:** a failed network call on Send or Void produces no message to the user, only a console error.
3. **High, `guards.js:18`:** `validQuantity` accepts blank, zero, negative, fractional and `Infinity` quantities.
4. **High, `guards.js:24`:** `lastSend` is never assigned, so the double-send guard never fires. A double-click posted twice in Chromium.

**Medium**
- **`app.js:8`:** a client name containing a double quote injects an event handler into the `title` attribute. Reviewers rated this Critical. The verifier lowered it to Medium because the only source is the user's own input.
- **`app.js:10`:** the total sums unrounded floats and showed 3.31 for lines that display as 3.30.
- **`app.js:19`:** invalid quantity or price is rejected silently.
- **`app.js:24`:** Send posts `[]` when no line has been added.
- **`app.js:33`:** Void has no confirmation and sends no invoice id.

**Low**
- **`app.js:8`:** each client name is a dead `href="#"` link.
- **`index.html:21`:** the `aria-live` list re-announces every line on each add.

The server (`/api/invoices*`) isn't in the payload, so I couldn't check whether it enforces the admin role or rejects duplicate or empty sends. Only reviewer B ran anything in a browser, and nobody tested with a screen reader. Verifier 2 computed the C6 rounding by hand without running it.

I didn't run the optional spot-check on a few findings, since the run was unattended. I also didn't offer an outside reviewer.

Next steps:
- `/curmudgeon:review fix` fixes all findings.
- `/curmudgeon:fix patch [id]` fixes one.