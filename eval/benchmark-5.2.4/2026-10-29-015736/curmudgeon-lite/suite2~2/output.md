**BLOCK** · Counts: 4 Critical, 12 High, 7 Medium, 0 Low

One blind reviewer ran in the lite tier. I reviewed only (no payload file was changed); the tool's own state went to `.critic/`, which is untracked. The scripted scan found 0 FAIL. Blind verifiers confirmed all 16 Critical and High findings. The 7 Medium findings were not verified in the lite tier, so their confidence is "possible". The full teardown is saved at `/tmp/dm-uvyn68of/work/.critic/last-review.md`.

**Critical**
- **C1** `api.js:3`: the API key is a literal in a browser script and is sent from the client. Anyone with DevTools can copy it and call the refund endpoint.
- **C2** `api.js:11`: `refund()` doesn't await the request and always returns `ok: true`. A 401, a 500 or being offline still shows "Refunded N orders!".
- **C3** `app.js:32`: customer name, id and status go into `innerHTML` unescaped. This is stored XSS, and the injected script can read `API_KEY`.
- **C4** `app.js:35`: the selection only grows. Tick 7, untick it, tick 9, and order 7 is still refunded.

**High**
- Pagination is off by one: the first ten orders aren't shown on load, and Prev/Next are unbounded (`app.js:27`).
- `getOrders` ignores the HTTP status, so a failed request leaves the dashboard broken with no message (`api.js:7`).
- Refund fires on one click with no confirmation, no empty check and no double-submit guard (`app.js:49`).
- Accessibility:
  - The Refund control is a `span`, so keyboard users can't reach it.
  - The focus outline is removed from every control.
  - The status select and row checkboxes have no accessible name.
  - Status is shown only as a coloured dot.
  - Small text is below 4.5:1 contrast.
  - The fixed 1000 px table scrolls sideways at 390 px.
- Four README claims are wrong:
  - The pricing figure of $1,440 is wrong under either reading of the price ($1,728 if the $15 is monthly).
  - The WCAG 2.1 AA claim fails.
  - "The key stays on the server" contradicts `api.js`.
  - "Refunds are confirmed first" is false.

**Medium (unverified)**
- Revenue rules hard-coded in a render function.
- `$NaN` and a blank table on an empty result.
- A request on every keystroke, with responses applied out of order.
- Search text not URL-encoded.
- Toast not announced to screen readers.
- Toast ignores reduced motion.
- The "instantly" performance claim has no measurement behind it.

**Fixes worth the most per hour**
1. Move the key behind a server-side proxy and rotate it.
2. Make `refund()` await and check the result, and fix the selection set.
3. Escape rendered values.
4. Use a real `<button>` with focus rings, a confirmation and an in-flight guard.
5. Correct the README claims.

**Not checked:** I never ran the app. Every scenario was traced from the code, and the contrast and pricing figures were computed by hand. No browser checks ran, so there's no axe, keyboard-reach or screenshot evidence. I also didn't check whether the real key is live, or whether a customer can control their own name in the backend.

To act on this, `/curmudgeon:review fix` fixes every finding, and `/curmudgeon:fix patch [id]` fixes one.