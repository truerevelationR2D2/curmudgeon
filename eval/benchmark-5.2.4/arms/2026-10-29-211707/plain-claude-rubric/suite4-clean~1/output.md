I found 9 bugs, ordered by severity. I read all four files (`app.js`, `guards.js`, `index.html`, `styles.css`) and traced the code. I did not run anything or change any files. The post-review filter in `rubrics.md` drops a claim unless there's a concrete failing case, so each bug has one.

**High**

1. **`app.js:25-29`, `guards.js:21-26` – the send guard blocks retries after a failure and doesn't stop duplicates.**
   - `tooSoon()` records `lastSend` before the request runs, so a failed send still counts as a send.
   - Failing case: click Send, get the "not sent" alert, and click again within 1 second. `tooSoon()` returns true and the retry is dropped with no message.
   - The guard is time-based, not in-flight. If the POST takes more than 1 second, a second click sends the same invoice again.
   - On success, `lines` is never cleared and nothing is shown to the user. Clicking Send again after 1 second posts the same lines again, creating a duplicate invoice. Only `sentCount` changes.

2. **`app.js:26` and `app.js:32` – a network failure is uncaught.**
   - `fetch` rejects when the network is down, on a DNS failure, or when the request is blocked. Neither handler has a try/catch.
   - Failing case: go offline and click Send. The click handler's promise rejects, nothing is shown, and the user gets no cause or next step. The same happens on Void.
   - Only HTTP errors (`!res.ok`) are handled.

3. **`app.js:26` – an empty invoice can be sent.**
   - There is no `lines.length` check. On a fresh page, clicking Send posts `[]` and counts it as sent.

4. **`app.js:19` – bad numeric input gets through the price check.**
   - `Number()` accepts `"1e999"` (Infinity), `"0x10"` (16) and `"1e3"` (1000). `price > 0` passes for all of them.
   - Failing case: enter price `1e999`. The total shows `Infinity`, and `JSON.stringify` turns the price into `null` in the POST body.
   - Failing case: enter price `0x10`. The line is booked at 16.00, although the user typed hex.

5. **`app.js:10-11` and `app.js:8` – money is calculated in floats and the displayed total can differ from the displayed lines.**
   - Each line is shown rounded with `toFixed(2)`, but the total sums the unrounded values.
   - Failing case: add three lines with qty 1 and price `0.004`. Each line shows `0.00`, but the total shows `0.01`.
   - Failing case: price `1.005` shows `1.00`, because the float is stored as 1.00499… .
   - The invoice total is wrong by the rubric's definition, and the POST sends unrounded floats.

**Medium**

6. **`app.js:16-20` – a blank client is accepted.**
   - The `required` attribute counts `"   "` as filled, and the code trims it to `""` without rechecking.
   - Failing case: enter client `   ` with valid qty and price. The line is added, and `<a>` renders empty. It is invisible and has no accessible name.

7. **`app.js:19` – invalid input is rejected with no feedback.**
   - Failing case: qty `0`, `abc` or `2.5`, or price `-1`. Clicking "Add line" does nothing, and the user can't tell why. The rubric's state and error-copy rows apply.

8. **`app.js:31-33` and `guards.js:10-12` – Void does nothing for most users, with no message.**
   - `user.roles` is `["viewer","billing"]`, so `canVoid` is false and the click returns silently. The button looks live, and a click gives no sign that it didn't run.
   - The admin check exists only in the browser, and the `user` object is hardcoded in client code. The server has to enforce it, and the POST carries no user or token, so I can't confirm it does. This is the "client trusted to enforce limits" row.
   - The void request has no body, so it names no invoice to void.

**Low**

9. **`app.js:8` – each line's client name is a dead link.**
   - It is `<a href="#">` with no handler. Clicking it jumps to the top of the page and adds `#` to the URL. Keyboard users get a tab stop that does nothing. It should be plain text.

**Checked and holds**

- Hostile input in `client` (`<img src=x onerror=alert(1)>`, `"&q=1#`) is escaped in both the text and the `title` attribute.
- `validQuantity` rejects `0`, `-1`, `1.5`, `""` and non-ASCII digits.
- The CSS focus outlines are present.