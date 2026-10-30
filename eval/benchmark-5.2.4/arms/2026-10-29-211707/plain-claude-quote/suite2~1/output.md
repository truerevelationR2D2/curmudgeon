```json
[
 {
  "file": "app.js",
  "line": 27,
  "quote": "  const start = page * PAGE_SIZE;",
  "title": "Page index is 1-based (page starts at 1, label says 'Page 1') but the slice offset treats it as 0-based, so the first page of results is skipped.",
  "failing_case": "Load with 25 orders: page=1 shows orders 10-19, and orders 0-9 can never be seen. Prev goes to page 0, which is the real first page, labelled 'Page 0'."
 },
 {
  "file": "app.js",
  "line": 34,
  "quote": "  document.getElementById(\"page\").textContent = `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}`;",
  "title": "Total page count is rounded down instead of up, so it is wrong whenever the last page is partial, and it is 0 for fewer than 10 orders.",
  "failing_case": "25 orders shows 'Page 1 of 2' (should be 3). 5 orders shows 'Page 1 of 0'."
 },
 {
  "file": "app.js",
  "line": 47,
  "quote": "document.getElementById(\"prev\").onclick = () => { page--; renderTable(); };",
  "title": "Prev and Next have no bounds checks, so page can go below the first page or past the last, leaving an empty table and a nonsensical label.",
  "failing_case": "Click Prev on the first page: page becomes 0 and then -1, giving a negative slice start and 'Page -1 of N'. Click Next repeatedly past the end: an empty table."
 },
 {
  "file": "app.js",
  "line": 45,
  "quote": "document.getElementById(\"q\").oninput = load;",
  "title": "A new search or filter does not reset page to 1, so the user can end up on a page beyond the filtered results. Also, load() has no debounce and no guard against out-of-order responses, so a slow earlier request can overwrite newer results.",
  "failing_case": "Go to page 3, then type a query that matches 4 orders: the table is empty and the label says page 3. Typing 'ab' quickly: if the response for 'a' arrives after the response for 'ab', stale data is shown."
 },
 {
  "file": "app.js",
  "line": 18,
  "quote": "  const avg = revenue / orders.length;",
  "title": "Division by zero when there are no orders gives NaN (0/0). Dividing net revenue by all orders, including pending and refunded ones, is also misleading.",
  "failing_case": "Search for text that matches nothing: the AVG ORDER card shows '$NaN'."
 },
 {
  "file": "app.js",
  "line": 13,
  "quote": "    if (o.customer.tier === \"gold\") t = t * 0.9;",
  "title": "Revenue is computed from float arithmetic on order totals, and the discount and tax are applied again on the client to the total. If the server's total is already discounted or taxed, revenue is double-counted. Float math on money also accumulates rounding error.",
  "failing_case": "A gold customer's order with a server total of 100 (already discounted) is counted as 90*1.0825 = 97.425. Summing many such values drifts by cents from the true total."
 },
 {
  "file": "app.js",
  "line": 32,
  "quote": "    tb.innerHTML += `<tr><td><input type=\"checkbox\" data-id=\"${o.id}\"></td><td>${o.customer.name}</td><td>$${o.total}</td><td><span class=\"dot ${o.status}\"></span></td></tr>`;",
  "title": "Customer name is inserted into innerHTML without escaping, which is a stored XSS. Using += on innerHTML inside the loop also re-parses the whole table on every row, and it destroys earlier rows' state.",
  "failing_case": "A customer named `<img src=x onerror=alert(1)>` runs script when the table renders."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  tb.querySelectorAll(\"input\").forEach((c) => c.onchange = () => { if (c.checked) selected.push(c.dataset.id); });",
  "title": "Unchecking never removes the id from selected, and ids are pushed again on each re-check. Checkbox state is lost on re-render or paging, but selected persists, so hidden or stale orders get refunded.",
  "failing_case": "Check order 5, then uncheck it, then click Refund: order 5 is still refunded. Check an order, change the page, and click Refund: the order from the other page is refunded too. Check, uncheck and re-check gives selected=[5,5]."
 },
 {
  "file": "app.js",
  "line": 51,
  "quote": "  if (r.ok) { const t = document.getElementById(\"toast\"); t.textContent = \"Refunded \" + selected.length + \" orders!\"; t.style.display = \"block\"; }",
  "title": "The success toast always shows, even when the refund failed or nothing was selected. selected is never cleared after the refund, and the orders are not reloaded, so the UI stays stale and a second click refunds the same orders again.",
  "failing_case": "Click 'Refund selected' with nothing checked: the toast says 'Refunded 0 orders!'. If the server returns 500, the toast still says success. Click twice: the same ids are sent again."
 },
 {
  "file": "api.js",
  "line": 11,
  "quote": "  fetch(`${API_BASE}/refunds`, { method: \"POST\", headers: { Authorization: \"Bearer \" + API_KEY, \"Content-Type\": \"application/json\" }, body: JSON.stringify({ ids }) });",
  "title": "The fetch promise is neither awaited nor checked, and refund() returns {ok:true} unconditionally. Network errors and HTTP errors are never reported, and an unhandled rejection can occur.",
  "failing_case": "The server returns 500 or the network is offline: refund() still resolves {ok:true}, and the UI reports success while no refund happened."
 },
 {
  "file": "api.js",
  "line": 3,
  "quote": "const API_KEY = \"__PLANTED_STRIPE_KEY__\";",
  "title": "A secret API key is hardcoded in client-side JavaScript, so anyone who loads the page can read it and call the refund API.",
  "failing_case": "Open DevTools or view api.js: the bearer token is visible, and can be used to POST /refunds directly."
 },
 {
  "file": "api.js",
  "line": 6,
  "quote": "  const res = await fetch(`${API_BASE}/orders?q=${query}&status=${status}`, { headers: { Authorization: \"Bearer \" + API_KEY } });",
  "title": "Query parameters are not URL-encoded, and the response status is not checked before res.json(). A query containing & or # corrupts the request, and an error response breaks the callers.",
  "failing_case": "Searching 'a&status=refunded' injects an extra parameter. A 401 or 500 with an error body makes orders a non-array, so orders.slice and the for..of loop throw a TypeError."
 }
]
```
