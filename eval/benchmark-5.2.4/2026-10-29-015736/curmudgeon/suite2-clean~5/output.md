**BLOCK** · Counts: 0 Critical, 1 High, 6 Medium, 1 Low

This is a review only. I changed no project files; the run state is in `.critic/`, and the full teardown is in `.critic/last-review.md`. Nothing was executed: Bash was denied to all three reviewers, so every finding is traced from the code, not run.

**High**
- **C1, `app.js:128` (`F-922ae62d`, 3 of 3 reviewers, confirmed).** Every Refund click creates a new `Idempotency-Key`. If a response is lost, the user retries with a different key, so the server can refund twice. This defeats the idempotency promise at `README.md:9`.

**Medium**
- **C2, `app.js:39` (`F-d4286f9f`, confirmed).** Refunded and pending orders can be selected and sent for refund. No client-side check stops it.
- **C3, `app.js:129` (`F-3a04c70f`, confirmed).** The refund response body is never read. A partial failure shows as full success, and an empty 204 shows as failure. The server's reply format isn't in the repo, so this stays Medium.
- **C4, `domain.js:11` (`F-46e3131a`, confirmed).** A null or empty total becomes a valid $0.00 order instead of being skipped. This contradicts the comment at `domain.js:7`.
- **C5, `domain.js:28` (`F-dc453406`, likely, verifier verdict "unclear").** Revenue re-applies a 10% gold discount and 8.25% tax to the order total, so it can differ from the Total column. Whether that's intended depends on whether the server's total is a subtotal. The repo doesn't say. That needs your answer.
- **C6, `app.js:145` (`F-9f099441`, confirmed).** The pager disables the button that has focus, which drops keyboard focus, and the page change isn't announced.
- **C7, `app.js:130` (`F-bd73c7fd`, possible, downgraded by the verifier from High).** If the reload after a successful refund fails, the refunded orders stay selected and can be refunded again.

**Low:** L1, `app.js:108` (`F-7a75b0a4`). A failed search leaves the old results on screen.

**Nits (not counted):** the pricing line at `README.md:12` describes a product this app doesn't have. The audit and performance claims at `README.md:5` can't be reproduced from the repo.

**Scan:** it reported 2 FAIL, 1 WARN and 2 NOTE. The two FAILs are 404s on the orders request because the page was served with no backend, so they aren't defects. I didn't turn the WARN or the NOTEs into findings.

**Dropped:** five findings raised by only one reviewer and not executed. Some are plausible: the missing request timeout, the refund total computed from raw floats, and the selection surviving paging.

**Fixes worth the most per hour:**
1. Hold one idempotency key per refund attempt (C1).
2. Read the refund result (C3).
3. Block refunds on non-refundable statuses (C2).
4. Reject null and empty totals (C4).
5. Stop disabling the focused pager button (C6).

**Not checked:**
- Browser behaviour, screen-reader output, 200% zoom and the real server's refund contract.
- The axe-core scan couldn't run (axe-core not found), so this review is degraded on that check.
- I skipped the variant hunt and the spot-check.

**Decisions for you:**
1. Is the server's `total` already net of discount and tax? My recommendation is to find out and then remove the duplicated rates from the client either way.
2. Which order statuses are refundable? My recommendation is paid only.

Next steps:
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.