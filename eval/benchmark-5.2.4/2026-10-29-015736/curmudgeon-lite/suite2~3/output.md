**BLOCK** · Counts: 5 Critical, 12 High, 8 Medium, 1 Low

I changed no project files. The review used the lite tier with one blind reviewer. The merge script counted 26 findings, and I copied that count rather than the reviewer's own summary, which didn't add up. The scripted scan reported 0 FAIL. I didn't pass `--page`, so its browser checks didn't run; the reviewer drove the app in Chromium with the API mocked instead.

Blind verifiers confirmed all 17 Critical and High findings. The 8 Medium findings weren't verified in this tier, so they carry lower confidence.

The five Criticals:
1. **API key in the browser (`api.js:3`):** the key is a string literal in client-side JavaScript. The README says it never leaves the server.
2. **Refund always reports success (`api.js:12`):** `refund()` doesn't wait for the request and returns `ok: true` regardless. With the refund endpoint answering 500, the toast still read "Refunded 2 orders!".
3. **Deselected orders get refunded (`app.js:35`):** unchecking an order never removes it from the selection, so tick, untick and Refund still refunds it.
4. **Unescaped output (`app.js:32`):** customer name and id go into `innerHTML` unescaped. This one is traced from the code, not run, so it is marked "likely".
5. **Refund control unreachable by keyboard (`index.html:19`):** it is a plain `<span>`, so Tab skips it.

The 12 High findings fall into four groups:
- **Refund and stats logic:** refund fires on one click and on an empty selection; an empty result shows `$NaN`; unthrottled search requests apply in arrival order.
- **Pagination:** page 1 starts at the 11th order.
- **Accessibility and layout:** contrast, sideways scroll at 390 px, status shown only by colour, unnamed controls, and removed focus outlines.
- **README claims:** the pricing example is wrong, since 12 seats at $15 with 20% off comes to $1,728 a year (or $144 if $15 is the yearly price), not $1,440. The full WCAG 2.1 AA claim is also contradicted by the code.

The teardown with every finding is saved at `.critic/last-review.md`.

Not checked: race ordering, reduced motion, 200% zoom and screen-reader announcements are traced from the code, not run. The README's "10,000 orders instantly" claim is unmeasured.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.