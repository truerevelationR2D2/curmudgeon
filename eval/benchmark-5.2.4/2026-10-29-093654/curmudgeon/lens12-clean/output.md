**CONCERNS** · Counts: 0 Critical, 0 High, 9 Medium, 3 Low

I reviewed the three pages and `_headers` with three blind reviewers. A script counted their votes, and a blind verifier checked each finding that went to verification. I changed no payload file. The only new thing in the repo is the `.critic/` working folder the review tool writes (`git status` shows it as untracked). The full teardown is in `.critic/last-review.md`.

Medium findings:
1. **`site/about.html:7`:** the CSP nonce is a fixed constant, `r4nd0m`, and no script carries it. Injected markup that uses that nonce would run.
2. **Third-party loads blocked by the pages' own CSP:**
   - `site/about.html:8` (`lib.js`)
   - `site/about.html:19` (the map iframe)
   - `site/checkout.html:7` (the analytics script)
   - `site/login.html:8` (the widget)

   For the checkout script, the verifier assumed the host reads `_headers` the standard way; the repo doesn't say.
3. **`site/login.html:8`, `site/about.html:8` and `site/checkout.html:7`:** all three scripts carry the same placeholder `integrity` value. It is about 39 bytes decoded, and a SHA-384 digest is 48. This is read by eye, not decoded with a tool.
4. **`site/checkout.html:14`:** the checkout asks for a card number but shows no total or items. The Pay button has no busy state, so a double click posts twice. Whether the second post charges twice depends on the server.
5. **All three pages:** there is no viewport meta tag.
6. **`site/login.html:16-17`:** the email and password fields have no `autocomplete` tokens.

The three Lows are a leftover `localhost:8080` live-reload script (`site/about.html:10`) and two misleading link texts (`site/about.html:15` and `:16`). The verifier lowered the first two from Medium.

Scripted checks found 0 FAIL, plus 10 placeholder warnings (`example.*` URLs) and 4 notes. The panel kept 12 of 33 raw findings; one single-vote finding was dropped.

I didn't check:
- Server-side behaviour (CSRF, how cards are handled, double-post handling).
- Phone rendering on a real device. Only reviewer C drove a desktop Chromium; the others traced from the code.
- Anything needing a live page: the browser, axe, keyboard and reflow checks were n/a because no page was given.

I didn't add an outside reviewer or run the spot-check.

`/curmudgeon:review fix` would fix every finding, and `/curmudgeon:fix patch [id]` fixes one.