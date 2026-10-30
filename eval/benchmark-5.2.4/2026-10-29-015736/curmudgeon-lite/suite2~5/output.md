**BLOCK** · Counts: 4 Critical, 12 High, 10 Medium, 2 Low (28 findings, plus 1 Nit that isn't counted)

This was a lite-tier review with one blind reviewer. Nothing in your project was changed. The scripted scan found 0 FAIL rows. The full teardown is saved at `.critic/last-review.md`.

The four Critical findings:
- **C1 `api.js:3`:** the API key is hard-coded in a script the browser downloads. Any visitor can copy it and POST refunds. The README says the opposite (D3).
- **C2 `app.js:32`:** customer names from the API go into `innerHTML` unescaped, so a malicious name runs script in every operator's session.
- **C3 `app.js:35`:** unticking a box never removes the order from the refund list. Tick 7, untick 7, tick 9, and a refund hits both orders.
- **U1 `index.html:19`:** the Refund control is a `span`, so keyboard and screen-reader users can't reach it.

The 12 High findings are in the teardown. The main themes:
- **Refund path:**
  - no confirmation;
  - no empty-selection or double-click guard;
  - success is reported before the request settles.
- **Errors:**
  - API errors are never checked;
  - an empty result shows `$NaN`;
  - pagination is off by one.
- **Accessibility:** focus outlines are removed, and order status is shown by colour alone.
- **README:**
  - the pricing is wrong: it says $1,440, but $15 × 12 seats × 12 months at 20% off is $1,728;
  - the accessibility claim is false;
  - the "key stays on the server" claim is false;
  - the "refunds are confirmed first" claim is false.

The five fixes worth the most per hour:
1. Move the key behind a backend and rotate it.
2. Escape or `textContent` every rendered field.
3. Rebuild the refund path: a real `button`, a Set for the selection, a confirmation, and an awaited, checked request.
4. Fix pagination and the empty and error states.
5. Correct the README.

**Not checked:** the app was never run in a browser, so every scenario is traced, not driven. No real API was contacted. Axe and keyboard page checks didn't run because no page was given.

**Verification:**
- All 16 Critical and High findings went to blind verifiers and all 16 were confirmed. None was lowered.
- The 10 Medium findings were not verified, because the lite tier checks only Critical and High. They stay at lower confidence.
- One verifier noted that orders 1–10 do appear, but only at "Page 0", so the pagination finding is slightly overstated.

**Next:**
- `/curmudgeon:review fix` fixes every finding.
- `/curmudgeon:fix patch [id]` fixes only that one.