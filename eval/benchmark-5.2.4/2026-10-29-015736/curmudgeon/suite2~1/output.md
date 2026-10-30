**BLOCK** · Counts: 4 Critical, 16 High, 8 Medium, 1 Low

I changed no project file. The only new thing is the `.critic/` working folder. The full teardown, with evidence and failing cases for every finding, is in `.critic/last-review.md`.

Three blind reviewers raised 77 findings. The script merged them into 29 and 28 went to blind verification. The verifiers confirmed 27 and lowered 2 (U1 Critical to High, C15 High to Medium). The scripted scan had 0 FAIL, and the variant hunt found nothing. One finding, F-2dc54db1, was dropped: one reviewer raised it and it wasn't executed.

**Critical**
- **C1** `api.js:3`: the API key is hard-coded in a script the browser downloads. It is sent on every call, refunds included.
- **C2** `api.js:12`: `refund()` doesn't wait for the request and always returns `ok: true`. A failed refund still shows "Refunded N orders!".
- **C3** `app.js:32`: the customer name is written into `innerHTML` unescaped, so any customer can run script in the admin session.
- **C4** `app.js:35`: unchecking an order never removes it from `selected`, so unchecked orders get refunded.

**High**
- **Refund flow:**
  - There is no confirmation step, no empty-selection guard and no double-click guard.
  - The toast never clears.
  - Failed loads and non-OK HTTP responses are unhandled, and out-of-order search responses overwrite newer ones.
- **Pagination:** it skips orders 0–9, and the page count is off.
- **Accessibility:**
  - The Refund control is a `<span>`, so keyboard users can't reach it.
  - The focus outline is removed.
  - The filter and row checkboxes have no accessible names.
  - Order status is shown only by a coloured dot.
  - Muted text fails contrast.
  - The table is a fixed 1000px wide.
- **README claims that fail** (the first two also show up in the accessibility and key findings above):
  - "WCAG 2.1 AA with 44px targets"
  - "key never leaves the server"
  - "refunds are confirmed"
  - the pricing arithmetic (neither reading of the $15 gives $1,440)

**Medium and Low**
- **Medium (8):**
  - Tax and the loyalty discount are computed in the render function, in floating point.
  - An empty result shows `$NaN`.
  - Prev and Next have no bounds.
  - Refund can be submitted repeatedly.
  - The search text isn't URL-encoded.
  - The toast has no live region.
  - The Prev and Next buttons are tiny.
  - The toast pulses forever and ignores reduced motion.
- **Low (1):** the "10,000 orders instantly" README claim is unmeasured.

**Top five fixes**
1. Move the key behind a server and rotate it.
2. Make `refund()` await and check the response, with a confirm step and an in-flight guard.
3. Make selection a Set that unchecking removes from.
4. Build rows with DOM nodes or `textContent`, not `innerHTML`.
5. Make Refund a real `<button>`, restore focus styles and label the controls.

**Not checked:** nothing was run in a browser or against a live API. The reviewers had no shell, so all 33 scenarios are traced from the code. Contrast ratios are hand-computed and the 390px layout is read from the CSS. I did not run the page checks, mutation tests or any project tests. I didn't offer an outside reviewer or the spot-check, because this run was unattended.

**Not reviewed:** nothing was skipped for the budget.

Next:
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.