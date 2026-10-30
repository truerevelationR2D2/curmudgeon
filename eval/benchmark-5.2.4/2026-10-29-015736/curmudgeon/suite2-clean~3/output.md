**BLOCK** · Counts: 0 Critical, 1 High, 5 Medium, 3 Low

Nothing was run: the reviewers' shell was denied, so every scenario was traced from the code, not driven. No browser check ran either, because no page was given.

I changed no project files. The run wrote its own output under `.critic/`, and the full teardown is in `.critic/last-review.md`.

**Findings**
- **C1, High (`app.js:128`):** Every Refund click makes a new idempotency key and never stores it. After a timeout or a 502/504, a retry sends a different key, so the server cannot recognise it as the same refund and can pay it twice. All 3 reviewers raised it and the verifier confirmed it.
- **C2, Medium (`app.js:83`):** Orders that are already refunded, pending or of unknown status can be selected and sent for refund. The confirm dialog still says money will go back.
- **C3, Medium (`api.js:17`):** A successful refund with an empty or non-JSON body, such as a 204, is shown as "not confirmed". The caller never uses the body.
- **C4, Medium (`domain.js:11`):** A total of null, an empty string or an empty array becomes a $0.00 order. It is kept, not counted as skipped, and can be refunded.
- **C5, Medium (`domain.js:29`):** Revenue applies the gold discount and 8.25% tax again on top of the server's total. This is uncertain: the verifier could not settle whether the server's total already includes tax, and the repo doesn't say.
- **C6, Medium (`app.js:130`):** If the reload fails after a confirmed refund, the refunded orders stay ticked and the Refund button stays live. The verifier lowered it from High, because a double payout also needs a deliberate second confirm and a server that accepts it.
- **Low:**
  - After a failed search, the old rows and stats stay on screen under the new query.
  - Paging disables the button that has focus, and the page change isn't announced to screen readers.
  - The page title sits 24 px left of the content column on wide screens.

Three more single-vote findings were dropped, and the scripted scan had 0 FAIL. The only scan warning is the usual visually-hidden CSS pattern, which I treated as not a defect. The README makes test, axe and timing claims with nothing in the repo behind them, and its "Team plan" pricing line doesn't belong in this project; both are listed as Nits.

**Not checked:** the server's refund contract and what `total` means. These are not in the repo, and two findings (C3 and C5) depend on them.

**Fixes worth the most per hour**
1. Keep one idempotency key per attempt set (C1).
2. Block selecting orders that can't be refunded (C2).
3. Clear the selection right after a confirmed refund (C6).
4. Treat any 2xx on the refund POST as success (C3).
5. Reject null, empty and array totals (C4).

To fix them, run `/curmudgeon:review fix` for all, or `/curmudgeon:fix patch [id]` for one.