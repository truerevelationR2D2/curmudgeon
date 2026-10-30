**BLOCK** · Counts: 2 Critical, 13 High, 10 Medium, 2 Low

This was the lite tier with one blind reviewer, in review mode. No project file changed. The only new thing in the repo is the `.critic/` folder, which Curmudgeon writes its run files to. All 15 Critical and High findings went to blind verification, and the verifiers confirmed every one. The scripted scan found 0 FAIL, 10 WARN and 19 NOTE. I did not triage those rows. The reviewer never saw them.

**Critical**
1. `api.js:3`: the API key is hard-coded in client JavaScript and sent as a Bearer token from the browser. The `POST /refunds` endpoint is reachable with it. The repo contains only a redacted placeholder, but the pattern is the defect.
2. `app.js:32`: the customer name goes into `innerHTML` unescaped. The reviewer ran a mocked API with `<img onerror>` as the name, and the script executed.

**High**
- **Refund:**
  - `refund()` always returns `ok: true`. With `POST /refunds` answered 500, the toast still read "Refunded 2 orders!".
  - Refund fires on one click with no confirmation, and it posts even with nothing selected.
  - The selection list never drops unchecked ids, so an order the user deselected still gets refunded.
- **Data and loading:**
  - HTTP errors are never handled. A 500 leaves the stats and table blank with no message.
  - The first 10 orders are never shown, because the page offset is off by one.
  - Typing fires one unthrottled fetch per keystroke, and a stale response can overwrite a newer one.
- **Accessibility:**
  - The main action is a `<span>`, so keyboard users cannot reach it.
  - Focus outlines are removed.
  - Several text colours fail 4.5:1 contrast (2.06–2.64:1 as computed by the verifier).
  - The fixed 1000 px table scrolls sideways at phone width.
- **README claims that the code contradicts:**
  - "The API key never leaves the server."
  - "Refunds are confirmed before they are sent."
  - "Meets WCAG 2.1 AA, including 44 px touch targets."

**Medium and Low**
- Pricing: the README's $1,440 matches neither billing reading ($1,728 or $144).
- Search: the text is not URL-encoded.
- Stats: an empty result shows `$NaN`.
- Paging: Prev and Next have no bounds.
- Other findings cover the status dot, missing labels, the toast announcement and animation, and the unmeasured "10,000 orders instantly" claim.

**Top fixes by value per hour**
1. Move the key behind a server-side proxy and rotate it.
2. Build rows with `textContent` instead of `innerHTML`.
3. Make `refund()` check the response, use a real `<button>`, and add a confirm and empty-selection guard.
4. Make the selection a Set and fix the page offset and bounds.
5. Correct or delete the four false README claims.

**Not checked:** contrast was computed, not measured in a browser. Screen-reader behaviour was traced, not run. The 10,000-order speed claim was not benchmarked.

**Not reviewed:** I did not run the variant hunt, which is a full-tier step. The 12 Medium and Low findings were not blind-verified, because the lite tier verifies Critical and High only, so their confidence is lower. No outside reviewer was added.

The full teardown is in `/tmp/dm-kaht3ixl/work/.critic/last-review.md`.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only one.