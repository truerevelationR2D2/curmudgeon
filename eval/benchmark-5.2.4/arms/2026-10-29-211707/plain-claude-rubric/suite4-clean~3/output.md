I read all four files (`app.js`, `guards.js`, `index.html`, `styles.css`, 95 lines in total) and checked them against the rubrics and sandbox scenarios. I changed no files and ran nothing. Every case below is traced by reading the code, not driven in a browser.

## Findings, most severe first

**1. High: `app.js:25-29`: double submit creates duplicate invoices.**
- The only guard is `tooSoon()`, a 1-second timer from `guards.js:21-26`. There is no in-flight flag, the button is never disabled, and `lines` is never cleared after a send.
- Failing sequence: click Send. If the server takes longer than 1 s, click again at 1.2 s. Both requests post the same lines, so the invoice is created twice.
- A later click after success also re-sends the same lines.

**2. High: `app.js:26-27` (and `:32-34`): `fetch` has no `catch`, so a network failure shows nothing.**
- `fetch` rejects when the network is offline or the server is unreachable. The `!res.ok` branch never runs, and the click handler ends in an unhandled rejection.
- Failing sequence: go offline and click Send or Void. The user sees nothing.
- `tooSoon()` has already set `lastSend` at `app.js:25`. A retry within 1 s is dropped silently, and this also happens after a 4xx or 5xx.

**3. High: `app.js:28`: success is never shown.**
- `sentCount` is incremented but never read or displayed. After a good send the user sees no confirmation, and the lines stay on screen.
- This leads straight to finding 1, because a user who can't tell it worked will click again.

**4. High: `app.js:8,10,11`, with `app.js:18-19`: money handling in floats gives inconsistent amounts.**
- Price `0.004`, qty 1: `0.004 > 0` is true, so the line is accepted. It displays as `0.00 × 1` and the total shows `0.00`, but the payload carries `0.004`.
- Add two lines of qty 1000 at price `0.004`. Each row shows a unit price of `0.00`, while the total shows `8.00`.
- `1.005.toFixed(2)` gives `"1.00"` (a floating-point artefact), so rounding is wrong.
- The sent amounts do not match what the user saw.

**5. High: `app.js:18-19`: `Number()` accepts non-finite values.**
- Typing `1e999` into Unit price gives `Infinity`, and `Infinity > 0` is true, so the line is added. The total shows `"Infinity"`.
- `JSON.stringify` turns `Infinity` into `null`, so the POST at `app.js:26` sends `price: null`. Wrong data reaches the API.
- `"0x10"` and `"1e3"` are also accepted as prices (16 and 1000).
- Related: `validQuantity("99999999999999999999")` passes (`guards.js:16`), which gives a quantity above 2^53 that has lost precision.

**6. High: `app.js:31-35` with `guards.js:10-12`: the void permission is checked only in the browser.**
- `user` is a client-side object, so in the console `user.roles.push("admin")` makes `canVoid` pass. Whether the server also checks the role cannot be seen from this folder.
- The void request carries no invoice id or body, so it is unclear what it voids.
- There is also no confirmation or undo for a destructive action.
- Failing sequence: sam, who has `["viewer","billing"]`, clicks Void. Nothing happens and there is no message (a dead control). A console edit lets them void anyway.

**7. Medium: `app.js:19`: failed validation returns silently.**
- Qty `0`, qty `1.5`, an empty price or price `-3` all hit `return` with no message, no error state and no focus move.
- The user sees the Add line button do nothing.

**8. Medium: `app.js:16,20` with `index.html:14`: a whitespace-only client is accepted.**
- `required` passes `"   "`, and `trim()` makes it `""`, so there is no later check. A line is pushed with an empty client, rendered as an empty link.

**9. Medium: `app.js:24-26`: an empty invoice can be sent.**
- With `lines = []`, clicking Send posts `[]` with no guard. The server may create an empty invoice, or return a 400 that the generic alert wrongly calls "Try again".

**10. Medium: `app.js:26,31`: no `Content-Type` header.**
- The body is a JSON string, so fetch sends `text/plain;charset=UTF-8`. A server that expects `application/json` can reject it or fail to parse it.

**11. Medium: `app.js:1`: state is lost on refresh.**
- `lines` lives only in memory. Refreshing after entering 30 lines loses them, and nothing warns the user. There is no `beforeunload` guard.

**12. Low: `app.js:8`: the client name is rendered as `<a href="#">` with no purpose.**
- Clicking it jumps the page to the top and adds `#` to the URL. It is a fake link, and keyboard users also tab to it.

**13. Low: `app.js:27,34`: the `alert()` messages are blocking, and the Send alert is wrong for non-retryable errors.**
- A 4xx (for example a validation rejection) still says "Try again". The Void alert gives no reason and no next step.

## Sandbox scenario 10 (hostile input)
- `<img src=x onerror=alert(1)>` and `"&q=1#` are escaped by `escapeHtml` in both the text and the `title` attribute. This holds (traced).

## Not findings
- The `styles.css` focus outlines are fine.
- The script order in `index.html` is fine, since `guards.js` loads before `app.js`.