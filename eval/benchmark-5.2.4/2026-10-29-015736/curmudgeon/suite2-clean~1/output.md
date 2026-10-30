DEGRADED: axe-core wasn't installed, so the scripted accessibility check didn't run and anything it covers is unverified.

**BLOCK** · Counts: 0 Critical, 1 High, 5 Medium, 0 Low

Three blind reviewers raised 20 findings and 6 survived the vote count. Blind verifiers confirmed 5 and lowered 1 from High to Medium. Nothing was executed; every finding is traced from the code. No source file changed, only the `.critic/` review folder was added.

| # | Where | Impact | Defect |
| --- | --- | --- | --- |
| C1 | `app.js:128` | **High** | A new idempotency key is made on every click. If a refund goes through but the response is lost, retrying refunds again. |
| C2 | `app.js:130` | Medium (High before verification) | If the reload after a refund fails, the refunded orders stay ticked and refundable under a new key. |
| C3 | `app.js:38` | Medium | Any order can be refunded whatever its status, including already-refunded and pending ones. |
| C4 | `domain.js:11` | Medium | A `null`, `''`, `[]` or `true` total becomes a valid $0.00 or $1 order instead of being dropped. |
| C5 | `domain.js:29` | Medium | Revenue adds 8.25% tax and a gold discount on top of the table's totals. $100.00 shows as $108.25 or $97.43. |
| U1 | `app.js:70` | Medium | Paging isn't announced to screen readers, and the focused Next or Previous button disables itself, dropping keyboard focus. |

Two README claims (axe-core clean, under 100 ms with 10,000 orders) and the plan pricing line aren't backed by anything in the repo. I listed them as nits and they don't count toward the verdict.

C3 and C5 rest on inferred requirements, since nothing in the repo says whether a total is net or gross, or which orders may be refunded. C2's duplicate payout also needs a server that doesn't check order status, which the README doesn't say.

The scan's two console failures are 404s on `/api` from a static server with no backend, so I didn't count them. The project's own tests weren't run, and the payload contains none.

The five fixes worth the most per hour:
1. Keep one idempotency key per refund attempt (C1).
2. Clear the selection as soon as the refund resolves, before the reload (C2).
3. Add an `isRefundable` check and use it for the checkboxes and the confirmation total (C3).
4. Tighten the total check in `normaliseOrder` and add the missing tests (C4).
5. Pick net or gross for `order.total` in one place and use it for Revenue and the refund amount (C5).

The full teardown, with the sandbox ledger and the evidence for each finding, is in `.critic/last-review.md`.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.