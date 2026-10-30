Bugs found (no files changed). Line numbers for `guards.js` are its own; the `cat -n` above ran on continuous numbering, so I give the real per-file lines.

1. **`guards.js:45` — `canVoid` is inverted.** `indexOf` returns `-1` (truthy) when "admin" is absent, and `0` (falsy) when "admin" is the first role.
   - Fails with: `user = {roles:["viewer","billing"]}` (the signed-in `sam`). `indexOf` gives `-1`, so `canVoid` returns true and a non-admin can void.
   - A real admin with `roles:["admin"]` gets `0`, so `canVoid` returns false and the admin is blocked.
   - Fix: use `includes("admin")`.

2. **`guards.js:58-60` and `app.js:25-28` — the double-send guard never works.** `lastSend` is never assigned, so it stays `0`. `Date.now() - 0` is always at least 1000, so `tooSoon()` is always false.
   - Fails with: double-click "Send invoice". Two POSTs go out and `sentCount` increases by 2.
   - Also, nothing disables the button during the `await`, so a slow network gives the same result.
   - Fix: set `lastSend = Date.now()` before the `fetch`.

3. **`guards.js:52-54` — `validQuantity` accepts bad quantities.** `isNaN("")` is false, `isNaN(" ")` is false, and negatives, zero and decimals pass.
   - Fails with: leave Quantity empty. `Number("")` is `0`, so a line with qty 0 is pushed.
   - Fails with: `-5` adds a line with negative total. `2.5` or `1e9` are accepted for an integer quantity.
   - `Infinity` also passes. `isNaN("Infinity")` is false, so the total shows `Infinity`.
   - Fix: require `Number.isInteger(Number(q)) && Number(q) > 0` and a non-empty trimmed string.

4. **`app.js:19` — price check allows `Infinity`.** `!(price > 0)` rejects `NaN`, `0` and negatives, but `Infinity` passes.
   - Fails with: price `Infinity` or `1e999`. `toFixed` then shows "Infinity" and the total becomes "Infinity".
   - Fix: use `Number.isFinite(price) && price > 0`.

5. **`app.js:16, 20` — the client name can be blank.** The `required` attribute on the input only applies to native form validation.
   - Fails with: a client of only spaces. The browser accepts it, `.trim()` makes it `""`, and a line with an empty client is pushed.
   - Fix: check `if (!client) return;`.

6. **`guards.js:40` — `escapeHtml` does not escape `"`.** It is used inside the attribute `title="..."` at `app.js:8`.
   - Fails with: client `x" onmouseover="alert(1)`. The quote closes the attribute and injects an event handler, which is XSS.
   - Fix: also escape `"` as `&quot;` and `'` as `&#39;`.

7. **`app.js:26` — the send handler never checks for an empty invoice, and there is no error handling.**
   - Fails with: click "Send invoice" with no lines. It POSTs `[]`.
   - Fails with: network failure. `fetch` rejects, nothing catches it, the user sees nothing, and the unhandled rejection is silent.
   - The same applies to void at `app.js:33`.
   - Also, there is no `Content-Type` header, so the body is sent as `text/plain`. A JSON-parsing server may reject or mis-parse it.

8. **`app.js:8-11` — floating-point money.** The total is a float sum of `qty * price`, rounded only for display.
   - Fails with: three lines of `1 × 0.1`, and then `0.1 × 3`. The displayed rounding can differ from the sum of the displayed line values (for example `1.005` shows as `1.00`, while the total of many such lines drifts by a cent).
   - Fix: use integer cents.

9. **`app.js:2, 32` — role check is client-side only.** `user` is a hard-coded constant, and the void authorization lives only in the browser. Even once #1 is fixed, anyone can call `POST /api/invoices/void` directly. This is only a bug if the server doesn't also enforce roles, which I can't see from this folder.

10. **`app.js:7-9` — `render()` rebuilds the whole list on each add.** Nothing is wrong functionally. The `href="#"` link will jump the page to the top and add a `#` to the URL when clicked. That is minor.

I didn't run any of this; each finding comes from reading the code.