**BLOCK** · Counts: 3 Critical, 12 High, 8 Medium, 0 Low

I changed no project files. The only new folder is `.critic/`, where the review keeps its working files. The full teardown is saved at `.critic/last-review.md`.

This was the lite tier with one blind reviewer. The scripted scan found 0 FAIL, but it ran without a page, so the browser checks didn't run. The reviewer was refused Bash, so every finding is traced from the code, not run. The verifiers confirmed 15 of the 17 Critical and High findings and downgraded 2 to Medium.

**Critical**
- **C1** `api.js:3` (`F-189324fd`): `API_KEY` is hard-coded in a script the browser loads and sent as a Bearer header. Anyone can read it in View Source. `README.md:6` says it never leaves the server.
- **C2** `app.js:32` (`F-01fabe72`): customer name, id and status go into `innerHTML` unescaped. A customer named `<img src=x onerror=…>` runs script in the operator's page, which also holds the API key.
- **C3** `app.js:35` (`F-4f017d5a`): the selection list only grows. Tick A, untick A, tick B, then click Refund, and both A and B are refunded.

**High**
- **C4** `api.js:12` (`F-03684ca6`): `refund()` never awaits the request and always returns ok. A server error or offline still shows "Refunded N orders!".
- **C5** `app.js:49` (`F-9c00f31c`): refund fires on one click with no confirmation, even with nothing selected. `README.md:9` says refunds are confirmed.
- **C6** `app.js:49` (`F-72f6628d`): there's no guard against a double-click, so two identical refund requests go out. Whether the money moves twice depends on the backend.
- **C7** `app.js:27` (`F-13c5f86a`): the page starts at 1 but the slice treats it as 0-based. The first 10 orders are never shown, and Prev shows "Page 0 of 2".
- **C8** `app.js:45` (`F-456ed704`): there's a request per keystroke with no debounce or cancel, so out-of-order responses overwrite newer ones. An error response makes the loop at `app.js:11` throw.
- **U1** `index.html:19` (`F-e7c515be`): the refund control is a `<span>`, so keyboard users can't reach it.
- **U2** `styles.css:19` (`F-cb785a5c`): the focus outline is removed with no replacement.
- **U3** `styles.css:9` (`F-6ed276f8`): the `#aaa` text has a contrast of 2.32:1 on white and 2.06:1 on the cream body, below the 4.5:1 minimum.
- **U4** `app.js:32` (`F-660caa60`): order status is shown only as a coloured dot, and the row checkboxes have no names.
- **U5** `styles.css:13` (`F-ddb2a576`): the table is a fixed 1000px wide, so the page scrolls sideways at 390px and at 200% zoom.
- **D1** `README.md:8` (`F-35d110b6`): the pricing is wrong. 12 seats at $15 with 20% off comes to $1,728 or $144 depending on the reading, never the quoted $1,440.
- **D2** `README.md:5` (`F-d306b8a9`): the WCAG 2.1 AA claim is false on this code. Criterion 2.5.5 is also AAA, not AA.

**Medium (8)**
- `F-95378953`: an empty result shows a `$NaN` average (downgraded from High).
- `F-128da2ac`: the status select has no label and the first table header is empty (downgraded from High).
- `F-9e74ede6`: the page count rounds down and Prev/Next aren't clamped.
- `F-f98ae1d3`: the search text goes into the URL unencoded.
- `F-fc3b0708`: discount, tax and revenue rules live inside the render function, using floating-point money.
- `F-0e57e23d`: the toast isn't a live region and never closes.
- `F-9f4e4d27`: the toast pulses forever with no reduced-motion override.
- `F-84336235`: the README's "instantly" has no measurement behind it.

The last six Medium findings (all but the two downgraded ones) had no verifier, because the lite tier only verifies Critical and High. They stay in at lower confidence. One more item, a stock look in `styles.css:3`, is listed as a Nit and isn't counted.

The five fixes worth the most per hour:
1. Take the API key out of the client and rotate it.
2. Escape or use `textContent` for every order field.
3. Fix the selection state, and give refund a confirmation, an in-flight guard and an awaited result.
4. Make the refund control a `<button>` and restore a visible focus ring.
5. Fix the pagination offset, then the README claims.

Not checked: nothing was run, no browser was used, and the reviewer couldn't read the "Browser integrity" lens section. Contrast and pricing were computed by the verifiers.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only one.