**BLOCK** · Counts: 0 Critical, 5 High, 6 Medium, 3 Low

The scripted scan found nothing (0 FAIL, 0 WARN); the review found 14 defects. Of those, 12 were confirmed by blind verifiers; one was left unclear and one was downgraded. Nothing was executed except by reviewer C, who drove the High findings in Chromium (SB23, SB24, SB26, SB28, SB33). The rest were traced from the code. I changed no payload files. The run wrote its working files under `.critic/`, but I did not save `.critic/last-review.md` or stamp the run.

#### INTENT GATE
Not needed: review mode never waits. The stated intent was only the commit message "task", which is too thin to check.
**Asked but not done:** none. **Done but not asked:** none.

#### RISK MAP
1. `app.js` (35 lines): money, network sends, input parsing and rendering.
2. `guards.js` (26 lines): the permission check, quantity validation and the send timer.
3. `index.html` (29 lines): the form and the live region.
4. `styles.css` (5 lines).

All four files were read in full by all three reviewers.

#### SANDBOX LEDGER
The script wrote 33 lines, SB1–SB33. In short: 10 scenarios across 3 reviewers; most findings below cite SB1, SB4, SB6, SB7, SB9, SB11, SB23, SB24, SB26, SB28 and SB33. Scenarios that held: no persistence to corrupt, 500 lines still cheap, 390 px and 200% zoom fine, and `<img onerror>` input is escaped. The full table is in `.critic/counts.md`.

#### 1. CODE AND ARCHITECTURE
- **C1** `app.js:10` | **IMPACT: High** | `F-9ead6925` · confirmed · votes 3/3 | **Defect:** the total sums unrounded floats, so it disagrees with the displayed unit prices.
  - **Evidence:** verifier traced `app.js:8-11`.
  - **Failing case:** quantity 1000 at price 1.005. The row shows 1.00 and the total shows 1005.00, a 5.00 mismatch. Sub-cent prices are accepted and POSTed unrounded.
  - **Remediation theory:** hold money as integer cents, rounded when the line is created.
- **C2** `app.js:19` (also `app.js:18`) | **IMPACT: High** | `F-61ed8e5b` · confirmed · votes 2/3 | **Defect:** the price check accepts Infinity.
  - **Evidence:** SB11, SB33 (driven).
  - **Failing case:** price `1e400` gives Infinity, so the total shows "Infinity" and `JSON.stringify` sends `null` as the price.
  - **Remediation theory:** require `Number.isFinite(price)` and a cent-precision check.
- **C3** `app.js:28` | **IMPACT: High** | `F-c398de34` · confirmed · votes 3/3 | **Defect:** a successful send shows nothing, keeps the lines, and the counter is never displayed.
  - **Evidence:** SB7. `sentCount` is read nowhere.
  - **Failing case:** the user clicks Send, sees nothing, and clicks again after 1 s. The same invoice is posted twice. The client sends no idempotency key.
  - **Remediation theory:** show a result, clear or lock the draft after success, and send an idempotency key.
- **C4** `app.js:32` | **IMPACT: High** | `F-0ff7b3a5` · confirmed · votes 3/3 | **Defect:** Void is shown and enabled for a user who can never use it, and the click does nothing.
  - **Evidence:** SB1, SB23 (driven).
  - **Failing case:** user "sam" has roles `viewer` and `billing`. Clicking Void returns at `app.js:32` with no message.
  - **Remediation theory:** hide or disable the control when `canVoid` is false, or say why.
- **C5** `guards.js:23` | **IMPACT: High** | `F-8ecea8d5` · confirmed · votes 3/3 | **Defect:** the double-send guard is a one-second timer, not an in-flight lock.
  - **Evidence:** SB4, SB26 (driven).
  - **Failing case:** with a response slower than 1 s, a second click at 1.1 s posts again while the first request is pending.
  - **Remediation theory:** use an in-flight flag that disables the button until the request settles.
- **C6** `app.js:16` | **IMPACT: Medium** | `F-df4d8ece` · confirmed · votes 3/3 | **Defect:** a whitespace-only client passes `required`, is trimmed to empty, and is added as a line with no client name. **Failing case:** type three spaces for the client and submit. **Remediation theory:** re-check the trimmed value.
- **C7** `app.js:19` | **IMPACT: Medium** | `F-8d2c8e86` · confirmed · votes 3/3 | **Defect:** an invalid quantity or price is dropped silently. **Evidence:** SB9. **Failing case:** type 2.5 as the quantity and click Add line; nothing happens and nothing is announced. **Remediation theory:** show an inline error and move focus to the field.
- **C8** `app.js:25` | **IMPACT: Medium** | `F-0095ffed` · confirmed · votes 2/3 | **Defect:** Send posts an empty invoice. **Evidence:** SB24 (driven). **Failing case:** click Send on a fresh page and `[]` goes to `/api/invoices`. **Remediation theory:** disable Send while there are no lines.
- **C9** `app.js:26` | **IMPACT: Medium** (verifier lowered it from High) | `F-992fdd63` · confirmed · votes 3/3 | **Defect:** Send and Void have no catch around `fetch`. **Evidence:** SB28 (driven). **Failing case:** offline, `fetch` rejects, no message appears, and Send stays locked for 1 s. The verifier lowered it because the request never left, so a retry is safe and no data is lost. **Remediation theory:** wrap the call in try/catch and show the same alert as the `!res.ok` branch.
- **C10** `app.js:33` (also `app.js:31`) | **IMPACT: Medium** | `F-6bec38dc` · confirmed · votes 3/3 | **Defect:** Void is a one-click irreversible action that names no invoice, has no confirm step, and reports no success. **Failing case:** an admin clicks Void and `POST /api/invoices/void` goes out with no body; on success nothing changes on screen. What the server voids is not in the payload. **Remediation theory:** send the invoice id, confirm first, and show the result.
- **C11** `guards.js:11` | **IMPACT: Medium** | `F-882d64b5` · likely · votes 3/3 | **Defect:** the only void permission check in the payload runs in the browser, against a client-held role list. **Evidence:** the verifier could neither trace nor refute it, because the server is not in the payload. **[UNCERTAIN RISK] - Requires verification:** a console user can bypass the check. It matters only if the server trusts the client. Confirm that the void endpoint enforces the role. **Remediation theory:** enforce the role on the server.
- **L1** `app.js:8`: each client name is a link to `#`, which does nothing and adds a tab stop per line. Make it plain text. (`F-15d23d98`, confirmed, 2/3)
- **L2** `app.js:21`: the form keeps its values after Add line, so a second click adds a duplicate. Reset the form and refocus it. (`F-da403a6f`, confirmed, 1/3)
- **L3** `index.html:21`: the live region is rebuilt wholesale, so each add re-announces the whole list, and the total is not announced. (`F-7a9add6f`, likely, 3/3)

**Nits** (not counted):
- the client link points to `#`;
- Add line, Send and Void share one style, with no primary action and the destructive one not set apart;
- the draft lives only in memory and the form is not refocused after Add;
- the JSON body has no Content-Type header, so it goes out as text/plain;
- a wrongly entered line cannot be edited or removed.

#### 2. UI/UX & INTERACTION FRICTION
The UX defects are C3, C4, C7 and L3 above. No page run (`--page` was not given), so the axe, keyboard, focus, responsive and speed checks did not run.
- **Heuristic violated:** visibility of system status (C3, C4, C7).
- **WCAG 3.3.1 Error Identification (Level A)** (C7).
- **WCAG 4.1.3 Status Messages (Level AA)** (C3, L3).

#### 3. THE "ANTI-AI" CLEANUP
None found. The one-style buttons and the `#` links are listed as a Nit and L1.

#### 4. CLAIMS, NUMBERS AND CONSISTENCY
Not applicable: no documents are in the payload.

#### 5. VERDICT
**BLOCK**
Counts: 0 Critical, 5 High, 6 Medium, 3 Low (total 14).
Panel: 3 blind reviewers. 4 findings were dropped (single vote, not executed), none retracted, none refuted, none hidden by rulings, none noted as like past dismissals.

The five fixes worth the most per hour:
1. Hold money as integer cents and reject non-finite prices (C1, C2).
2. Disable Send while a request is in flight or there are no lines, and send an idempotency key (C3, C5, C8).
3. Add try/catch and a visible success or failure state for Send and Void (C3, C9, C10).
4. Hide or disable Void when `canVoid` is false, and have the server enforce the role (C4, C11).
5. Show inline errors for invalid quantity, price and client (C6, C7).

**Dropped** (single vote, not executed), listed in `.critic/counts.md`:
- the Void request names no invoice;
- lines cannot be edited or removed;
- the draft is lost on refresh;
- the buttons share one style.

Not checked:
- the server (`/api/invoices` and `/api/invoices/void` are not in the payload), so authorization and duplicate handling there are unverified;
- a real screen reader;
- a measured contrast ratio;
- the 390 px layout, which was traced, not driven.

Not reviewed: nothing was skipped for budget. The page-based checks (axe, keyboard, focus, responsive, speed) did not run because no page was given. The `deps` and `ci` checks had nothing to read.

Variants: none (the variant hunt found 0 candidates).

Change map: `.critic/change-map.md`

Run notes:
- The first `apply` counted the verdicts as unclear because I had abbreviated them. I rebuilt them with the verifiers' full evidence and ran `apply` again, so the counts above come from the second run.
- I did not run `critic_ledger.py stamp` or the spot-check.
- Reviewers A and B ran with Bash denied, so their findings are traced, not executed.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.