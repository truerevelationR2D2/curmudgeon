**BLOCK** · Counts: 5 Critical, 14 High, 8 Medium, 1 Low

The full review is saved at `/tmp/dm-8dgzqxqp/work/.critic/last-review.md`. I changed no project files. The only new thing in the repo is the untracked `.critic/` folder.

**Process**
- Three blind reviewers raised 79 raw findings.
- After dedup and a script-counted vote, 28 findings stand; 3 were dropped as single votes that no reviewer executed.
- Blind verifiers checked 27 of them. 26 were confirmed and 1 was downgraded to Medium.
- The scripted scan reported 0 FAIL.

**The five fixes worth the most per hour**
1. **C1 (`app.js:35`, Critical):** the refund selection never loses an id when a box is unticked, and it is never cleared. Tick 11, untick 11, tick 12, and Refund refunds both.
2. **C2 and C3 (Critical):** `api.js:3` hard-codes the API key in client code, and `app.js:32` writes customer names into `innerHTML` unescaped. One reviewer ran a hostile name and the script executed.
3. **C5 and C4 (High):** `refund()` never awaits and always returns `ok:true`, so a failed refund shows a success toast. `getOrders` never checks `res.ok`, so an error body crashes the render.
4. **U1 (`index.html:19`, Critical):** Refund is a `<span>`, so the keyboard can't reach it. The same handler also has no confirmation (C10) and no double-click guard (C9).
5. **C6 and C7 (High):** page 1 starts at offset 10, so the first ten orders never show. The page count rounds down and Prev/Next are unbounded.

The README makes four claims that are false: the key never leaves the server, WCAG AA, refunds are confirmed, and the pricing. The pricing line should read $1,728 a year, not $1,440 (12 × $15 × 12 × 0.8).

**Not checked**
- Server-side refund behaviour (idempotency, auth) was not checked.
- Contrast ratios are hand-computed, not measured on screen.
- Screen-reader output and 200% zoom were not run.
- The "10,000 orders instantly" claim was not timed.
- Several scenarios were traced rather than driven.
- No `--page` was given, so the scan's own browser checks did not run. The browser evidence comes from reviewers A and B.

**Not reviewed:** nothing in the payload was skipped. The variant hunt found 0 variants, and there was no outside reviewer.

Four verifier confirmations (C7, C13, C14, C15) were counted "unclear" because they cited no failing file:line that exists. Those findings stand on their reviewer votes.

To act on this:
- `/curmudgeon:review fix` fixes every finding.
- `/curmudgeon:fix patch [id]` fixes one.