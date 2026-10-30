I read all four files (`app.js`, `guards.js`, `index.html`, `styles.css` was not needed) and changed nothing. I didn't run the code. Each failure below comes from reading it.

**Bugs**

1. **`app.js:25-26` with `guards.js:21-26`: a failed or blocked send is swallowed, and the duplicate-send guard is weak.**
   - `tooSoon()` records `lastSend` before the request is made.
   - Sequence: click Send and the request fails (`!res.ok`). Click "Try again" within 1s. `tooSoon()` returns true and the click does nothing, with no message.
   - Sequence: click Send on a slow connection (request takes more than 1s). Click again at 1.5s. The guard passes and a second POST goes out, so the invoice is created twice.
   - Nothing in the code locks the button while a request is in flight, and `lines` is not cleared after a successful send, so any later click re-sends the same lines.

2. **`app.js:26`: no error handling around `fetch`.**
   - If the network is down, the server is unreachable or the request is blocked, `fetch` rejects. The `await` throws, so the `!res.ok` branch and its alert never run.
   - Result: an unhandled promise rejection and no feedback to the user.
   - The same applies to `app.js:33` (void).

3. **`app.js:26`: an empty invoice can be sent.**
   - Sequence: load the page and click "Send invoice" with no lines added. It POSTs `[]`.
   - `sentCount` also increments at line 28, but nothing ever reads it.

4. **`app.js:16, 20`: a whitespace-only client is accepted.**
   - The `required` attribute in `index.html:14` accepts `"   "`.
   - Sequence: enter client `"   "`, qty `1`, price `5` and submit. After `.trim()` the client is `""`, so the pushed line is `{client:"", ...}`, which renders as an empty link.

5. **`app.js:18-19`: `Number()` accepts price strings that aren't plain decimals.**
   - `"Infinity"` passes `price > 0`. The total becomes `Infinity` and the page shows "Infinity" in `#total` and "Infinity" as the line price.
   - `"1e9"` and `"0x10"` (which becomes 16) also pass.
   - Rejected input at line 19 returns silently, with no message to the user.

6. **`guards.js:16`: there is no upper bound on quantity.**
   - Sequence: enter qty `99999999999999999999`. The regex passes and `Number(...)` becomes 1e20, which is past exact integer range.
   - The total then goes to scientific notation or loses precision. `toFixed` returns `"100000000000000000000.00"` here, and loses accuracy beyond that.

7. **`app.js:2` with `guards.js:11` and `app.js:32`: Void can never work as shipped.**
   - The hardcoded user has roles `["viewer","billing"]`, so `canVoid` is always false and the click handler returns silently.
   - The role check is client-side only, so it protects nothing unless the server enforces it too.
   - The void POST carries no invoice ID, so even for an admin the server can't tell which invoice to void.

8. **`app.js:26`: the request is malformed.**
   - It sends a JSON string without a `Content-Type: application/json` header. The default is `text/plain`, so a server that parses JSON by content type will reject or ignore the body.

9. **`app.js:10-11`: totals are summed in floating point.**
   - Sequence: add three lines of qty 1 at price `0.1` each. The reduce gives `0.30000000000000004`, which `toFixed(2)` hides, but money rounding errors accumulate on larger sums.
   - Example: `1.005.toFixed(2)` gives `"1.00"`.
   - The rendered per-line price at line 8 and the total at line 11 can disagree by a cent.
   - Amounts should be kept in integer cents.

Severity: 1, 2, 4 and 8 are the ones most likely to cause real harm (duplicate or lost invoices, bad data). Number 7 means a feature that never works. The rest are validation gaps.

I found no HTML-injection bug. `escapeHtml` covers `&`, `<`, `>`, `"` and `'` in both the text and `title` positions.