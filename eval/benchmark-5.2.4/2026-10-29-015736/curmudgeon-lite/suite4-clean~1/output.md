**BLOCK** · Counts: 0 Critical, 3 High, 7 Medium, 2 Low

I changed none of the four source files. The only new files are under `.critic/`. Review took the lite tier: 1 blind reviewer, with verification of the High findings only. The scripted scan reported 0 FAIL. I read the payload, 95 lines in `app.js`, `guards.js`, `index.html` and `styles.css`, only through the reviewer and verifier agents.

**High** (each confirmed by a blind verifier, but traced, not run)
- **H1 `app.js:10`:** the total is summed from unrounded prices. Two lines at 0.125 each display 0.13, but the total shows 0.25, and the lines add up to 0.26.
- **H2 `app.js:26`:** Send has no try/catch and shows nothing on success or failure. An offline failure is silent, so the user clicks again.
- **H3 `guards.js:23`:** the double-send guard is a one-second timer, not an in-flight lock. A request slower than 1 s, or a click at 1.1 s, posts the invoice twice.

**Medium** (single vote, no verifier verdict because the lite tier verifies High only; confidence "possible")
- **M1:** an empty invoice can be sent.
- **M2:** an invalid quantity or price is dropped silently.
- **M3:** a whitespace-only client is accepted.
- **M4:** a wrong line can't be removed or edited, and the form isn't reset after adding.
- **M5:** the Void button does nothing, with no message, for non-admins, and a network failure on void is also silent.
- **M6:** Void has no confirmation or lock.
- **M7:** the void permission is checked only in the browser, against a hard-coded user object. The server isn't in the payload, so this is an uncertain risk. Check that the server enforces the role.

**Low**
- **L1:** each client name is a dead `href="#"` link.
- **L2:** `Number()` price parsing accepts `Infinity` and `0x10`.

The two nits are listed in `.critic/last-review.md` and not counted.

**Not checked**
- Every scenario was traced, none driven. The reviewer had no shell, and I didn't run `node` for the rounding case in H1.
- I ran no page checks (no `--page` given).
- One reviewer means no cross-check on the single-vote findings.

The full teardown is in `.critic/last-review.md`. To fix everything, run `/curmudgeon:review fix`. To fix one finding, run `/curmudgeon:fix patch [id]`.