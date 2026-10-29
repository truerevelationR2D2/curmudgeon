**BLOCK** · Counts: 0 Critical, 3 High, 10 Medium, 2 Low

I reviewed all four files with three blind reviewers and a script-counted vote. Blind verifiers checked every kept finding. No file was changed. Every scenario was traced from the code. Nothing was run or driven in a browser. The scripted scan found 0 FAIL. The variant hunt found no further variants.

**High**
1. **Price accepts non-finite values (`app.js:18`).** `Infinity` and `1e400` pass the `> 0` check. The page shows "Infinity", and the posted invoice carries `price: null`.
2. **Double-send guard is a 1-second timer (`app.js:25`).** A server that takes 3 seconds lets a second click send a duplicate invoice.
3. **Network failure is silent (`app.js:26`).** An offline Send or Void is an unhandled rejection with no message to the user.

**Medium, in short**
- **Money display:** rows and total disagree on float math and rounding.
- **Add line:** a whitespace-only client is saved as an empty name, and a bad quantity or price is dropped with no message.
- **Send:**
  - An empty invoice can be posted.
  - A successful send shows nothing.
- **Void:**
  - Void sends no invoice id.
  - Void does nothing for the only user the page defines.
  - Void has no confirmation and sits beside Send with the same styling.
  - The admin check exists only in the browser (`app.js:32`).
- **Live region:** the whole list is rewritten with `innerHTML`, so a screen reader re-reads every line on each add.

**Low:** the draft is lost on reload, and each client name is a dead `#` link.

**Verifier adjustments:** the verifiers downgraded Void doing nothing from High to Medium and the lost-draft finding from Medium to Low. They rated the browser-only admin check unclear because no server code was in the payload. I kept that one as an uncertain risk: read the `/api/invoices/void` handler to settle it.

**Fixes worth the most per hour**
1. One `send()` wrapper with an in-flight flag, a disabled button, try/catch and an announced result.
2. One price and quantity parser in integer cents, with visible errors.
3. Keep the invoice id from the Send response, and enable Send and Void only when they have something to act on.
4. Confirm the server enforces the void role, then hide the button for non-admins.
5. Move announcements to a separate `role=status` element.

Not done: the optional outside reviewer was not offered, and the spot-check was not run because it needs your answers. The full teardown, with evidence for each finding, is in `.critic/last-review.md`.

To fix every finding, run `/curmudgeon:review fix`. To fix one, run `/curmudgeon:fix patch [id]`.