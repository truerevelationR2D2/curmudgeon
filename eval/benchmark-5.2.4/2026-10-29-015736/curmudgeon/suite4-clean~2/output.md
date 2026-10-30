DEGRADED: axe-core could not run, so no automated WCAG result exists. No agent executed anything either, because every reviewer's shell was denied. Every case below is traced from the code, not run.

**BLOCK** · Counts: 0 Critical, 3 High, 7 Medium, 3 Low

I reviewed `app.js`, `guards.js`, `index.html` and `styles.css` with three blind reviewers. Each finding was then checked by a blind verifier. I changed no project files; the only writes are Curmudgeon's own `.critic/` outputs. The stated intent is the commit message "task", which says nothing checkable.

**High**
1. `F-992fdd63` `app.js:26` and `app.js:33`: Send and Void don't catch a rejected `fetch`, so a network failure shows nothing. The one-second throttle also swallows a quick retry. Votes 3/3, confirmed.
2. `F-8ecea8d5` `guards.js:23`: the double-send guard is a one-second timer, not a lock held while a request is pending. With a 3 s server, clicks at 0 s and 1.2 s send two invoices. Votes 3/3, confirmed. The verifier saw the quoted line at `guards.js:58` in its copy; the quote matches.
3. `F-93d0e835` `app.js:18`: price `1e999` becomes `Infinity` and is sent as `null`; hex input like `0x10` is also accepted. Votes 1/3, confirmed by the verifier.

**Medium**
- `F-b690c640` `app.js:10`: unrounded float sums. 100 × 1.005 shows a line of 1.00 beside a total of 100.50.
- `F-9dadc9fc` `app.js:16`: a whitespace-only client passes `required` and adds a blank line.
- `F-c845673a` `app.js:19`: Add line silently does nothing on invalid quantity or price.
- `F-0be95039` `app.js:28`: a successful send shows nothing, and `sentCount` is never read.
- `F-caf52c76` `app.js:33`: Void has no confirmation or target, and it is styled like Send.
- `F-5b4ad5a5` `app.js:2`: the Void role check exists only in the browser. This is **[UNCERTAIN RISK] - Requires verification**: the server isn't in the payload, so someone must read its void handler.
- `F-0ff7b3a5` `app.js:32`: Void does nothing and says nothing for the only defined user.

**Low**
- `F-46fb6206`: each line links to `#`, a dead tab stop.
- `F-bb8b3415`: Send accepts an empty invoice.
- `F-7a9add6f`: the live region is rebuilt wholesale, so screen readers may re-read the whole list.

Nit, not counted: the POST sets no `Content-Type` header.

**Fixes worth the most per hour**
1. One in-flight lock with an idempotency key, plus a visible send result.
2. `try/catch` on both requests.
3. Strict number parsing and money in cents.
4. Confirm Void, and enforce the role on the server.
5. Validate the whole form and say what's wrong.

**Panel:** 3 reviewers. 4 single-vote findings were dropped as not executed. 0 retracted, 0 refuted, 0 hidden by your rulings. The variant hunt found none.

**Not checked:** server-side role enforcement and `Content-Type` handling, and screen-reader output.

**Not reviewed:** nothing was skipped for budget. axe-core could not run. I skipped the spot-check; I didn't ask you to judge findings.

The full teardown is in `.critic/last-review.md`, the change map in `.critic/change-map.md`, and the ledger is stamped.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.