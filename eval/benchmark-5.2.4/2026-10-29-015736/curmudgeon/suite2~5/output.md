**BLOCK** · Counts: 5 Critical, 13 High, 7 Medium, 1 Low

This was a review only. I changed no project files; the review wrote its own working files under `.critic/`. The full teardown is saved at `/tmp/dm-9jdcje3d/work/.critic/last-review.md`.

Three blind reviewers raised 77 findings. After vote counting and blind verification, 26 stand. Verifiers checked 25 of them and confirmed all 25; none were refuted or lowered. The 26th, a Low about customer names being clipped, was not sent to a verifier. The scripted scan found 0 failures and 10 warnings, and the variant hunt found no variants.

**Critical**
- **API key in the browser:** the key is a literal in `api.js:3` and goes out as a bearer token from the page. README line 6 says the key never leaves the server.
- **Refunds always look successful:** `refund()` doesn't wait for the request and returns `ok: true`. Reviewer A drove it against a stubbed API; the endpoint returned 500 and the page still said "Refunded 3 orders!".
- **Script injection:** customer name, id, total and status go into `innerHTML` unescaped. A customer named `<img onerror=…>` ran script in reviewer A's driven run.
- **No keyboard access to Refund:** "Refund selected" is a `span`, so Tab never reaches it.

**High, the ones that cost money or fail users**
- **Wrong orders refunded:** unticking a row never removes it from the selection, so a refund can go out for an order the user deselected.
- **No guard on refund:** there is no confirmation, and a double-click sends two identical requests.
- **Missing first page:** the first 10 orders never show on load, because the page starts at 1 but the slice starts at `page * 10`.
- **Load errors are silent:** a failed or malformed response leaves the old rows on screen with no message.
- **Accessibility and layout:** focus outlines are removed, status is shown only as a red/green dot, and several controls have no accessible name. Text contrast fails, and the fixed 1000 px table forces sideways scrolling on a phone.

**README claims**
- **Accessibility:** the "WCAG 2.1 AA" claim is false, and 2.5.5 is Level AAA, not AA.
- **Pricing:** at $15 per seat per month, 12 seats for a year at 20% off is $1,728, not the $1,440 the README gives. If $15 is a yearly price, the total is $144. Either way $1,440 is wrong, and the README doesn't say which period it means.
- **Refund confirmation:** "Refunds are confirmed before they are sent" is false, since the code has no confirmation step.

The five fixes worth the most per hour:
1. Take the key out of `api.js`, rotate it, and proxy calls through a server.
2. Make `refund()` await the request and report the real result, with a confirmation and an in-flight guard.
3. Build rows with `textContent` instead of `innerHTML`.
4. Make Refund a `button` and fix the selection list.
5. Delete or fix the false README claims.

**Not checked:** nothing ran against a live API, and cross-browser rendering, 200% zoom and real screen-reader output weren't tested. The "10,000 orders instantly" claim wasn't measured, and the exact revenue cents in the tax and discount finding weren't run. The browser-based scan checks didn't run because no page was given. The package-manifest and CI checks had nothing to look at.

To act on this:
- `/curmudgeon:review fix` fixes every finding.
- `/curmudgeon:fix patch [id]` fixes one finding.