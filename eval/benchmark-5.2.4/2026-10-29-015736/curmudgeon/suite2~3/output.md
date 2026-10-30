**BLOCK** · Counts: 5 Critical, 15 High, 7 Medium, 0 Low

Three blind reviewers raised 81 findings and a script merged them to 27. Blind verifiers confirmed all 27. The full teardown is in `.critic/last-review.md`. I changed no project files; the run's output went to `.critic/`.

**Critical**
- **C1** `api.js:3`: the API key is a literal in client-side JavaScript. Anyone can read it and use it to refund orders.
- **C2** `api.js:12`: `refund()` always returns success without checking the request. With the refunds endpoint answering 500, the page still said "Refunded 2 orders!".
- **C3** `app.js:32`: a customer name is written into `innerHTML` unescaped. A name containing an `<img onerror>` payload ran script in the page (driven).
- **C4** `app.js:35`: the selection list only grows. Tick 11, untick 11, tick 12, and both 11 and 12 get refunded.
- **C5** `index.html:19`: the Refund control is a `<span>`, so keyboard and screen-reader users can't reach it.

**High**
- **Refund flow:**
  - One click refunds with no confirmation, though the README says refunds are confirmed.
  - A double-click sends the refund twice.
  - Failed or non-JSON order responses leave the page blank with no message.
  - Every keystroke fires a request and the last response to arrive wins.
- **Paging and stats:**
  - The first page skips orders 1–10 (`app.js:27`).
  - Prev and Next have no bounds.
  - An empty result shows `$NaN` as AVG ORDER.
- **Accessibility and layout:**
  - Focus outlines are removed.
  - The filter and checkboxes have no labels.
  - Several text colours fail contrast (for example #aaa on white is 2.32:1).
  - Status is shown only as a colour.
  - A fixed 1000 px table forces sideways scroll on a phone.
- **README claims:**
  - The README says the page meets WCAG 2.1 AA, which it doesn't.
  - Its pricing example says $1,440, but 15 × 12 × 12 × 0.8 = $1,728.

**Medium** (7): unencoded search text, tax and discount rules inside the render function, page count rounding down, an empty refund still posting, and a toast that isn't announced, never goes away and pulses forever.

**Fixes worth the most per hour**
1. Rewrite the refund path: a real button, a proper selection, a confirm step, and check the response.
2. Stop injecting HTML and add a CSP.
3. Move the API key to a server and rotate it.
4. Fix paging together with the empty and error states.
5. Correct the README claims, then the accessibility basics.

**Not checked:**
- There was no real backend, so idempotency of `POST /refunds` and how the server handles duplicate query parameters are untested.
- Contrast ratios were computed, not measured on screen.
- No screen reader was run.
- Reviewer C traced its cases instead of running them, and A and B traced a few.
- No page-level browser checks ran, because no `--page` was given.
- The variant hunt found nothing, and no outside reviewer was used.

Next: `/curmudgeon:review fix` fixes everything, or `/curmudgeon:fix patch [id]` fixes one finding.