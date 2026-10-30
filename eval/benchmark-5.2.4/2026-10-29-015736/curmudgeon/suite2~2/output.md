**BLOCK** · Counts: 3 Critical, 17 High, 8 Medium, 0 Low

This was a deep review of all five files, three blind reviewers, no file changed. The scripted scan found 0 failing rows, so every finding comes from the reviewers, and each was checked blind afterwards. The full teardown is in `/tmp/dm-0cg4xu1i/work/.critic/last-review.md`.

The reviewers raised 77 findings. 28 survived, 5 were dropped as single unexecuted votes, and one was downgraded from High to Medium. The variant hunt found none.

**Critical**
- **C1 `api.js:3`:** the bearer key is a constant in a script served to every visitor. It is sent from the browser to the refund endpoint.
- **C2 `app.js:32`:** customer names go into `innerHTML` unescaped. A reviewer drove it in a browser and a name with markup ran script.
- **C3 `index.html:19`:** the Refund control is a `<span onclick>`, so keyboard and screen-reader users can't reach it.

**Top High findings**
- `refund()` returns success whatever the server says. A reviewer drove a 500 response and still got "Refunded 2 orders!".
- Unchecking an order never removes it from the refund list. Deselected orders still get refunded.
- Refunds fire on one click with no confirmation, even with nothing selected.
- Pagination is off by one: the first screen skips orders 1–10, and Prev and Next have no bounds.
- `load()` has no error handling or debounce, so a stale response can overwrite a newer one.
- Focus outlines are removed, several text colours fail contrast, status is shown by colour alone, and the fixed 1000 px table scrolls sideways on a phone.

**README claims that are false**
- "Key never leaves the server" is false (C1).
- "Refunds are confirmed" is false.
- The WCAG 2.1 AA claim is false, and it cites 2.5.5, which is AAA.
- The pricing figure $1,440 doesn't match either reading of the inputs. They give $1,728 or $144.
- "10,000 orders instantly" has no measurement behind it, and the code refetches the whole list on every keystroke.

**Fixes worth the most per hour**
1. Remove and rotate the key, and move refunds behind a server.
2. Stop writing API data into `innerHTML`.
3. Make `refund()` honest: a real button, a confirm step, a correct selection set.
4. Fix the pagination offset and bounds, and reset the page when the filter changes.
5. Add error handling and debounce to `load()`, and encode the query.

**Not checked**
- Hover and focus looks by screenshot, 200% zoom, and a real out-of-order response race.
- The live API's CORS and Content-Type behaviour. Reviewer A stubbed the API.
- Most scenarios were traced rather than driven, because two reviewers had no shell.
- The browser scan didn't run because no page was given.

Next steps:
- `/curmudgeon:review fix` fixes every finding.
- `/curmudgeon:fix patch [id]` fixes one.