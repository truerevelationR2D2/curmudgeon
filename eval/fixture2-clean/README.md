# OrderDesk

An order dashboard: search, filter by status, page through orders and refund selected ones.

- **Accessibility:** every control is reachable by keyboard, has a visible focus outline and a name; status is shown in words, not colour alone; the page reflows at 390 px. axe-core reports no WCAG 2.1 A or AA violations with orders loaded. Buttons and fields are at least 44 px high (the 2.5.5 target, which is AAA in WCAG 2.1); checkboxes are 24 px (2.5.8, an AA rule in WCAG 2.2). Not yet tested with a screen reader.
- **Security:** the browser holds no API key. It calls the same-origin proxy at `/api/v1` with the user's session cookie. The server must:
  - add the API key to requests it forwards, and keep the key out of every file served to the browser;
  - check that the signed-in user may list orders and issue refunds, and protect `POST /api/v1/refunds` against cross-site requests;
  - honour the `Idempotency-Key` header on refunds, so a repeated request does not refund twice;
  - rotate the API key that earlier versions of `api.js` shipped to browsers. That key must be treated as leaked.
- **Performance:** the table shows 10 orders per page. Search waits 250 ms after typing stops, cancels the previous request and ignores late responses. With 10,000 orders from a mocked local API, a search re-renders in under 100 ms; this has not been measured against the real API.
- **Pricing:** the Team plan is $15 per seat per month; 12 seats on annual billing at 20% off is $1,728 a year (12 × $15 × 12 = $2,160, less 20%).
- **Refunds:** the dashboard asks for confirmation, with the order count and amount, before sending a refund, and reports success only after the server confirms it.
