```json
[
 {
  "file": "app.js",
  "line": 13,
  "quote": "    if (o.customer.tier === \"gold\") t = t * 0.9;",
  "title": "Gold discount and 8.25% tax are applied to the stored total, so revenue is misstated. The stored total is presumably already what the customer paid, so applying them again is wrong.",
  "failing_case": "A paid gold order with total 100 is counted as 100*0.9*1.0825 = 97.43 instead of 100. Revenue is off for every order."
 },
 {
  "file": "app.js",
  "line": 18,
  "quote": "  const avg = revenue / orders.length;",
  "title": "Division by zero when there are no orders. The result is NaN, and `NaN.toFixed(2)` returns the string \"NaN\", so the card shows $NaN.",
  "failing_case": "Search for a name that matches no customers. orders is [], so avg is 0/0 = NaN and the card shows \"$NaN\"."
 },
 {
  "file": "app.js",
  "line": 12,
  "quote": "    let t = o.total;",
  "title": "The average divides net revenue (paid minus refunds) by all orders, pending ones included. The 'AVG ORDER' figure is therefore wrong.",
  "failing_case": "One paid order of 100 and nine pending orders give an average of about 10.83 instead of 108.25."
 },
 {
  "file": "app.js",
  "line": 27,
  "quote": "  const start = page * PAGE_SIZE;",
  "title": "Pages are 1-based, as the label shows, but slicing treats page as 0-based. The first page skips the first 10 orders.",
  "failing_case": "On load page=1, so start=10 and orders 0-9 are never displayed. With 10 or fewer orders the table is empty."
 },
 {
  "file": "app.js",
  "line": 34,
  "quote": "  document.getElementById(\"page\").textContent = `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}`;",
  "title": "The page count uses floor instead of ceil. It shows 0 pages for fewer than 10 orders and omits the partial last page.",
  "failing_case": "With 25 orders it shows 'Page 1 of 2' and the last 5 orders can't be reached. With 5 orders it shows 'Page 1 of 0'."
 },
 {
  "file": "app.js",
  "line": 47,
  "quote": "document.getElementById(\"prev\").onclick = () => { page--; renderTable(); };",
  "title": "Neither paging handler is bounded, and the page is not reset when the filter changes. Prev can go to zero or negative. Next can go past the last page. A new search keeps the old page, which can be beyond the new results.",
  "failing_case": "Click Prev on page 1 to get page 0, then Prev again to get page -1. slice(-20, -10) then returns the wrong rows. Or go to page 3, search for something with 5 results, and the table is empty."
 },
 {
  "file": "app.js",
  "line": 32,
  "quote": "    tb.innerHTML += `<tr><td><input type=\"checkbox\" data-id=\"${o.id}\"></td><td>${o.customer.name}</td><td>$${o.total}</td><td><span class=\"dot ${o.status}\"></span></td></tr>`;",
  "title": "Customer name is inserted into innerHTML without escaping, which allows XSS. The `+=` on innerHTML inside the loop also re-parses the whole table on every row and discards the handlers and checked state set earlier.",
  "failing_case": "A customer named `<img src=x onerror=alert(1)>` runs script when the table is rendered."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  tb.querySelectorAll(\"input\").forEach((c) => c.onchange = () => { if (c.checked) selected.push(c.dataset.id); });",
  "title": "Unchecking a box never removes the id from `selected`. Checking it again adds a duplicate. The selection is also never cleared on re-render or after a refund, while the re-rendered checkboxes appear unchecked.",
  "failing_case": "Check order 5, uncheck it, then click Refund. Order 5 is refunded anyway. Checking and unchecking twice sends 5 twice."
 },
 {
  "file": "app.js",
  "line": 50,
  "quote": "  const r = await refund(selected);",
  "title": "There is no handling of an empty selection, and no error handling. The success toast shows even when the request fails or nothing is selected.",
  "failing_case": "Click 'Refund selected' with nothing checked. The toast says 'Refunded 0 orders!'. If the server returns 500 the toast still says it succeeded."
 },
 {
  "file": "api.js",
  "line": 11,
  "quote": "  fetch(`${API_BASE}/refunds`, { method: \"POST\", headers: { Authorization: \"Bearer \" + API_KEY, \"Content-Type\": \"application/json\" }, body: JSON.stringify({ ids }) });",
  "title": "The fetch promise is neither awaited nor returned, and the function always returns {ok:true}. Failures and rejections go unreported, and a network error causes an unhandled rejection.",
  "failing_case": "The API returns 403 or the network is down. refund() still resolves {ok:true} and the UI reports the refund as done."
 },
 {
  "file": "api.js",
  "line": 6,
  "quote": "  const res = await fetch(`${API_BASE}/orders?q=${query}&status=${status}`, { headers: { Authorization: \"Bearer \" + API_KEY } });",
  "title": "The query parameters are not URL-encoded, and the HTTP status is not checked before `res.json()`. Error responses are then treated as the orders list.",
  "failing_case": "Searching 'a&status=paid' injects an extra parameter. A 401 or 500 JSON error body is assigned to `orders`, and `for (const o of orders)` throws because it is not iterable."
 },
 {
  "file": "api.js",
  "line": 3,
  "quote": "const API_KEY = \"__PLANTED_STRIPE_KEY__\";",
  "title": "The API key is hard-coded in client-side source and sent from the browser, so anyone can read it.",
  "failing_case": "Anyone who opens the page source or the network tab can copy the key and call the refunds API."
 },
 {
  "file": "app.js",
  "line": 45,
  "quote": "document.getElementById(\"q\").oninput = load;",
  "title": "A request is sent on every keystroke with no debounce and no handling of out-of-order responses. A slow earlier response can overwrite a newer one.",
  "failing_case": "Type 'ab' quickly. If the response for 'a' arrives after the one for 'ab', the table shows results for 'a' while the box says 'ab'."
 }
]
```
