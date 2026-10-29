**BLOCK** · Counts: 0 Critical, 5 High, 2 Medium, 4 Low

Three blind reviewers raised 35 findings. They were merged and verified, which left 11. No reviewer ran anything, so every finding is traced from the code, not executed. The only run result is the scripted scan: clicking "Void invoice" ended in "Failed to fetch". The page ran with no server behind it. The scan's axe check could not run, so there is no scripted accessibility result.

Files in the project folder are unchanged. The only new thing in git is `.critic/`.

**High**
1. **Send and Void failure handling** (`app.js:26`, also `app.js:33`): neither has a `try/catch`, and success changes nothing on screen. Offline gives a silent failure. A 200 leaves the lines in place, so a second click re-sends the same invoice.
2. **Quantity guard** (`guards.js:18`): `validQuantity` accepts empty, zero, negative and infinite values. A quantity of `-5` at price 100 gives a total of -500.00, and that negative line is sent to the server.
3. **Send throttle** (`guards.js:24`): `lastSend` is never assigned, so `tooSoon()` is always false. Two quick clicks send two invoices.
4. **Quote escaping** (`guards.js:5`, used at `app.js:8`): `escapeHtml` doesn't escape `"`, but its output goes inside `title="..."`. A client name like `x" onmouseover="alert(1)` runs script on hover. The verifier lowered it from Critical to High because the only source is the user's own typing.
5. **Inverted void permission** (`guards.js:10`): `canVoid` tests `indexOf("admin")` as true or false. A viewer can void and a lone admin can't. The verifier lowered it from Critical to High because this is only the client-side check. No server code is in the payload.

**Medium**
- **Silent rejection** (`app.js:19`): a bad quantity or price makes Add line do nothing and show no message.
- **Void without confirmation or id** (`app.js:31`): Void has no confirmation, and its request names no invoice.

**Low**
- **Lost draft:** invoice lines live only in memory and are lost on refresh.
- **Dead client link:** the client name is a link to `#` that does nothing.
- **Float totals:** money is summed as floats.
- **Live-region re-announcement:** the whole list is re-rendered inside a live region.

**Dropped:** four findings that only one reviewer raised and nobody executed. Two are worth a look when you fix the High items:
- an empty invoice can be sent;
- the form isn't cleared, so a second Enter adds a duplicate line.

**Not checked:**
- The server side (`/api/invoices` and the void endpoint) isn't in the payload, so server-side authorization, idempotency and validation are unverified.
- The float-rounding finding is inferred only.
- Screen-reader behaviour of the live region wasn't tested.

**Fixes worth the most per hour**
1. Fix the `canVoid` test, then enforce roles on the server.
2. Add one request helper with a pending state and visible success and failure. That also fixes the dead throttle.
3. Add a real quantity rule.
4. Escape quotes, or stop building HTML strings.
5. Confirm before void, and send an invoice id.

The full teardown is in `.critic/last-review.md`, and the change map is in `.critic/change-map.md`.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.