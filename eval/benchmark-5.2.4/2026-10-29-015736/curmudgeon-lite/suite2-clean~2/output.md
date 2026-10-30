**BLOCK** · Counts: 0 Critical, 2 High, 3 Medium, 3 Low

This was a lite-tier review: one blind reviewer, six verifier verdicts, and a scripted scan with 0 failures. Nothing was executed, so every finding is traced from the code. I changed no project files. The review and its working files are under `.critic/`, and the full teardown is `.critic/last-review.md`.

**High**
- **F-6c61fee2, `app.js:128`:** a new idempotency key is made on every click, and the selection survives an unconfirmed refund. If a refund goes through but the response is lost, the user's retry can refund twice.
- **F-46e3131a, `domain.js:11`:** `normaliseOrder` turns a missing total into $0.00, although its own comment says such records are dropped. The order shows as $0.00, counts in the totals, and adds nothing to the refund amount.

**Medium**
- **F-9d3cdadc, `app.js:108`:** after a failed reload, the old orders stay selectable and refundable.
- **F-2e717129, `domain.js:28`:** revenue applies a gold discount and tax to `order.total`, but the table and the refund dialog use it raw, so the figures disagree.
- **F-aa8d392b, `app.js:76`:** any order can be selected for refund whatever its status. This one is "possible", not "likely", because the script marked the verifier's confirmation unclear (its evidence was too short).

**Low**
- **F-3022f88a, `app.js:83`:** disabling a focused button drops keyboard focus to the page start.
- **F-a65cc1ce, `domain.js:35`:** "Average per order" divides by every order, not just paid ones. The verifier lowered it from Medium to Low.
- **F-a14dc3c3, `styles.css:23`:** the heading sits 24 px left of the content at wide widths.

The two README items (an unsourced pricing line, and accessibility and performance claims with nothing that reproduces them) are listed as Nits and not counted.

**Not checked**
- Nothing was run and no page was rendered, so the focus loss and the layout finding are inferred from the code.
- The server is outside the payload, so I can't say whether it rejects duplicate or ineligible refunds.
- The README's 10,000-order timing and axe claims were not run.
- I couldn't search git history for the leaked key the README mentions, because there is one commit.

The scanner raised a clipped-text warning on `.sr-only` and a hover-without-focus note on the buttons. No reviewer examined either. The reviewer saw a focus-visible rule at `styles.css:38-43`.

The fix worth the most is the idempotency key in F-6c61fee2: reuse one key per refund attempt. To fix everything, type `/curmudgeon:review fix`. To fix one finding, type `/curmudgeon:fix patch [id]`.