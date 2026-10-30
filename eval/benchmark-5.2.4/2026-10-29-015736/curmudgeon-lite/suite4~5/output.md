**BLOCK** · Counts: 0 Critical, 3 High, 9 Medium, 0 Low

I reviewed all four files at the lite tier, with one blind reviewer and one verifier. No project file was changed. The review wrote only its own output under `.critic/`, and the full teardown is in `.critic/last-review.md`.

Nothing was executed, because the reviewer couldn't run Bash. Every case below is traced by hand. The scripted checks found 0 FAIL, but the page checks didn't run because I gave no `--page`.

**High**
1. **`F-8cd9cc61`, `guards.js:10`:** `canVoid` is inverted. `indexOf("admin")` returns -1 (truthy) for non-admins and 0 (falsy) for an admin who is first in the list. So viewers can void and the admin is blocked. The verifier lowered this from Critical because it is only a client-side gate and the server isn't in the payload.
2. **`F-217d6fed`, `guards.js:24`:** `tooSoon` never trips, because `lastSend` is never assigned. A double-click on Send posts the invoice twice.
3. **`F-baa39b0f`, `guards.js:18`:** `validQuantity` is `!isNaN(qty)`, so it accepts blank, negative, zero and `Infinity`. A quantity of -3 at price 10 gives a total of -30.00.

**Medium (9)**
- `F-12358b37`: `escapeHtml` skips quotes, so `title="..."` can be broken out of. It is self-XSS today. No patch is offered because the checker flagged the proposed fix's quoting as unbalanced.
- Void:
  - `F-191b833a`: the role is a hard-coded client object and the only void check is in the browser.
  - `F-caf52c76`: Void is one click, irreversible, has no invoice id in the request, and sits next to Send.
- Send path:
  - `F-992fdd63`: a failed or offline `fetch` is never caught.
  - `F-4aa36c5b`: an empty invoice can be sent.
  - `F-11ae4ec8`: a successful send is invisible, and the lines stay in place.
- Form and display:
  - `F-e1421453`: bad quantity or price is dropped silently.
  - `F-9ead6925`: the shown unit price is rounded but the total isn't.
  - `F-609ede0a`: client names are dead `href="#"` links.

There is also one nit, not counted: the aria-live list is rebuilt with `innerHTML` on every add.

Only the three Highs and the escape finding were verified. The other eight Medium findings were not, which the lite tier allows. The server side, screen-reader behaviour and a browser run are not checked, so a full-tier or `--page` run would cover them.

The two fixes worth the most per hour are `includes("admin")` plus a test, and a real quantity validator. Run `/curmudgeon:review fix` to fix everything, or `/curmudgeon:fix patch [id]` for one finding.