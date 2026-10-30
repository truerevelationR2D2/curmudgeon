The review is finished, and I'm showing the teardown now. I changed no payload files. The only new files are Curmudgeon's own state in `.critic/`.

**BLOCK** · Counts: 0 Critical, 2 High, 9 Medium, 1 Low

Three blind reviewers raised 38 raw findings, and a script merged them to 12 kept and 2 dropped. Blind verifiers checked 11 of the 12, and the scripted scan had 0 FAIL. The variant hunt found none. Every scenario was traced from the code, and none was run.

**High**
- **C1** `app.js:26` (`F-992fdd63`, 3/3): Send has no try/catch. Offline gives silence and success gives silence, because `sentCount` is never shown.
- **C2** `guards.js:23` (`F-8ecea8d5`, 3/3): the send guard is a one-second timer, not an in-flight lock. A request that takes 3 s, with a second click at 1.5 s, posts the same invoice twice. There is no idempotency key.

**Medium**
- **C3** `app.js:1` (`F-6260eb41`): lines live only in memory, so a refresh loses them.
- **C4** `app.js:10` (`F-319e9af8`): money is summed as unrounded floats and Infinity is accepted as a price. A price of 0.004 × 1000 shows a row of 0.00 and a total of 4.00. A price of `1e999` is sent as `null`.
- **C5** `app.js:16` (`F-81a2bc00`): a client name of only spaces passes `required` and is added as a blank line.
- **C6** `app.js:19` (`F-ba5588ab`): an invalid quantity or price is rejected silently, with no message or announcement.
- **C7** `app.js:25` (`F-0095ffed`): Send with no lines posts `[]`.
- **C8** `app.js:33` (`F-69eebb56`): Void has no confirmation, names no invoice and reports nothing on success. It sits next to Send.
- **C9** `index.html:21` (`F-7a9add6f`): the whole list is rewritten inside an `aria-live` region, so a screen reader can re-read every line on each add.
- **C10** `app.js:32` (`F-0ff7b3a5`): Void is shown to a non-admin and does nothing. The verifier lowered this from High.
- **C11** `app.js:2` (`F-191b833a`): the void permission is checked only in the browser. This is [UNCERTAIN RISK] - Requires verification, because the server code isn't in the payload.

**Low**
- **C12** `app.js:8` (`F-595e1a80`): each client name is a link to `#` that goes nowhere.

**Nit:** `app.js:26` sends the JSON with no `Content-Type`, so it goes as `text/plain`.

**Dropped**
- `F-d8782c9e`: a single vote, and not executed.
- `F-866e7758`: a single vote, and not executed.

**Fixes worth the most per hour**
1. Make Send an in-flight lock with try/catch, visible success and failure, and an idempotency key (C1, C2).
2. Store money as integer cents, check `isFinite`, and show inline errors (C4, C5, C6).
3. Disable Send until there is a line, and persist the draft or warn before leaving (C3, C7).
4. Give Void an invoice id and a confirmation, and enforce the role on the server (C8, C10, C11).
5. Append list items instead of rewriting the live region (C9).

**Not checked:** nothing ran in a browser, Node or a screen reader. The server behind `/api/invoices` and `/api/invoices/void` isn't in the payload, so C7 and C11 depend on it.

**Not reviewed:** no payload file was skipped. The page checks (axe, keyboard, layout) didn't run because I passed no `--page`. I also skipped the optional outside reviewer and the spot-check.

The full teardown is in `/tmp/dm-hkrtc_6c/work/.critic/last-review.md`, and the change map is `/tmp/dm-hkrtc_6c/work/.critic/change-map.md`.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.