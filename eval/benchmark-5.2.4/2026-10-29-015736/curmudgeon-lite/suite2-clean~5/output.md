**BLOCK** · Counts: 0 Critical, 1 High, 1 Medium, 3 Low

Lite tier, one blind reviewer. The scripted scan had 0 FAIL rows. No source files were changed; the run only wrote its own records under `.critic/`. The full teardown is in `.critic/last-review.md`.

1. **High, `app.js:128`, `F-f5d7550d`:** `refundSelected` makes a new idempotency key on every click.
   - **Failing case:** if a refund succeeds but the reload fails, the selection stays checked and Refund stays enabled. A second click sends a different key, so the server can't recognise it as a repeat and the customer is refunded twice.
   - **Evidence:** the reviewer drove this in Chromium and saw three clicks send three different keys. The verifier traced it and confirmed it.
2. **Medium, `app.js:38`, `F-47fedea7`:** refunded and pending orders can be ticked and sent to Refund. `domain.js` has no eligibility rule. I don't know whether the server rejects them.
3. **Low, `api.js:17`, `F-71f0b31a`:** a 204 or empty-body success on the refund call is reported as "not confirmed". The verifier lowered it from Medium because the server contract isn't in the repo.
4. **Low, `app.js:72`, `F-5f340f06`:** paging to the last or first page disables the focused button, so keyboard focus drops to the body. The verifier lowered it from Medium because it couldn't trace the claim that Tab then restarts from the top.
5. **Low, `styles.css:23`, `F-2c3ff8c3`:** the page title sits 24 px left of the content on screens wider than 1148 px.

There is also one Nit, not counted: `README.md:12` states a subscription price that nothing in the dashboard uses.

**Not checked:** screen-reader behaviour, real server behaviour for refunds and idempotency, the README's axe-core and 10,000-order timing claims, and Safari and Firefox focus behaviour. No page-level browser checks ran, because I didn't pass `--page`.

**Verification:** the verifier ran no browser, so it traced all four packets and reproduced none. It had no write access, so I saved its verdicts to `.critic/verdicts/1.json` myself.

The five fixes worth the most per hour, in order, are the five findings above.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.