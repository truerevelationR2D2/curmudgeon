**BLOCK** · Counts: 0 Critical, 1 High, 9 Medium, 2 Low

This was a lite-tier review with one blind reviewer. Only the High finding was blind-verified. The nine Mediums were not, so their confidence is lower. The scripted scan reported 0 FAIL. No project files changed; the only new files are Curmudgeon's own `.critic/` state folder. The full teardown is saved at `.critic/last-review.md`.

**High**
- **C1 `site/about.html:15`** (`F-68e390fc`, likely): the link text says `shop.example.com` but the href goes to `https://www.example.com/`. Every other page treats shop.example.com as the shop host, and nothing maps www.example.com to it. A visitor who clicks lands on a host the page never named. A verifier confirmed this by tracing the code, not by running it. How bad it is depends on what www.example.com actually is.

**Medium**
- **C2 `about.html:10`** (`F-d2482626`): a dev live-reload script from `http://localhost:8080` is left in the shipped page, over plain http with no integrity hash. The CSP blocks it today, but every visitor's browser still tries to load it.
- **C3 `login.html:7`** (`F-7152c651`): the pages' own CSP (`script-src 'self'`) blocks the third-party scripts they load. This affects login, about and checkout.
- **C4 `login.html:8`** (`F-17a226ed`): the integrity value on all three third-party scripts is base64 of ASCII filler (`foobarbaz…`), not a real SHA-384 digest. It looks like script pinning but pins nothing.
- **C5 `about.html:7`** (`F-9f93d3a6`): the CSP nonce is the fixed string `r4nd0m`, and no script tag uses it. Anyone who can inject markup can reuse it.
- **C6 `checkout.html:14`** (`F-209b6839`): Pay is a plain POST with no double-submit guard. A double click can charge twice unless the server dedupes, and the server code isn't in this payload.
- **U1 `about.html:19`** (`F-250b68db`): the CSP blocks the map iframe, so visitors see an empty box.
- **U2 `login.html:4`** (`F-746f8c29`): none of the three pages has a viewport meta. On a phone the page lays out at about 980 px and users must pinch-zoom to type.
- **U3 `checkout.html:13`** (`F-82e17914`): checkout shows no order or total and has only a card number field. No spec is in the payload, so this is inferred from convention.
- **U4 `login.html:16`** (`F-b83e7719`): the email and password fields have no autocomplete tokens (WCAG 1.3.5, AA).

**Low**
- **L1 `about.html:9`** (`F-8a75c55e`): `/js/site.js` doesn't exist, so every About load returns 404.
- **L2 `about.html:16`** (`F-53998fd1`): the link text "index.html" names a file, but the link opens a docs site root.

**Nits (not counted):**
- `_headers` is possibly not read from here, and the CSP lacks frame-ancestors, form-action and base-uri.
- The sign-in page tells users to pay a card bill at an unrelated bank site.

**Five fixes worth the most per hour**
1. Make the link on `about.html:15` point where its text says.
2. Decide what each third-party script is for. Fix the CSP and digests, or remove the tags, on all three pages.
3. Add an idempotency token and disable-on-submit to Pay.
4. Remove the localhost reload tag and the dead `/js/site.js` tag.
5. Add the viewport meta and the autocomplete tokens.

**Not checked:** server-side double-charge protection, the real deployment of `_headers`, and what www.example.com really is.

**Not reviewed:** the nine Medium findings were not blind-verified. No page was given to the browser scan, so the axe, keyboard and layout checks did not run. No outside reviewer was used.

Next steps:
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.