**BLOCK** · Counts: 0 Critical, 3 High, 8 Medium, 3 Low

Three blind reviewers, a script-counted vote and blind verification produced these 14 findings. I changed no source files. Every case is traced from the code. The reviewers had no shell, so nothing was executed. The scripted scan returned 0 FAIL, and the variant hunt found 0 variants.

**High**
1. **Price accepts `Infinity`** (`app.js:19`, `F-a5e8edbc`): `1e999` passes the check, and `JSON.stringify` then sends `null` as the price.
2. **Duplicate invoice on Send** (`app.js:25`, `F-3b76d424`): a 1-second timer guards Send, not an in-flight flag. A second click at 1.5 s during a slow request sends the same lines again. A success shows nothing.
3. **Network failure on Send is silent** (`app.js:26`, `F-992fdd63`): a rejected `fetch` is never caught. The cooldown also starts before the request, so a quick retry is dropped.

**Medium** (8)
- **`F-6260eb41`:** the draft lives only in memory, and lines can't be edited or removed.
- **`F-9ead6925`:** the total is summed from unrounded prices while the lines show rounded ones, so they can disagree.
- **`F-7db44266`:** a whitespace-only client name is accepted and stored as an empty string.
- **`F-e3ea9b3c`:** Send posts an empty invoice when there are no lines.
- **`F-11ae4ec8`:** a successful send shows nothing and leaves the lines in place.
- **`F-0ff7b3a5`:** Void is a silent dead button for the signed-in user.
- **`F-caf52c76`:** Void names no invoice, asks for no confirmation and shows no success.
- **`F-e1421453`:** invalid quantity or price is dropped with no message. A comma decimal like `9,50` is rejected.

**Low** (3)
- **`F-191b833a`:** the void permission is checked only in the browser.
- **`F-c5e5de33`:** client names render as dead `#` links.
- **`F-7a9add6f`:** the live region re-announces the whole list on each add.

There are also 2 nits. The two single-vote findings that were dropped are both covered by findings above.

**What I couldn't confirm**
- The server isn't in the repo. I don't know whether it enforces the admin role or accepts an empty or unnamed request.
- I didn't run page checks in a browser, because no `--page` was passed.
- The live-region behaviour is untested with a screen reader.
- The two Low findings about the dead links and the live region were kept on 3/3 votes without blind verification.

**Fixes worth the most per hour**
1. Make Send safe: disable it while a request is in flight, require at least one line, clear the draft on success and send an idempotency key.
2. Wrap both fetches in `try/catch` and show failures.
3. Parse price and quantity in one tested function, and keep money in integer cents.
4. Add a Remove button per line and persist the draft.
5. Fix Void: confirm, send the invoice id, and give a reason when the user lacks permission.

Full teardown: `/tmp/dm-aoh740wx/work/.critic/last-review.md`

To fix everything, run `/curmudgeon:review fix`. To fix one finding, run `/curmudgeon:fix patch [id]`.