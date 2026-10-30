```json
[
 {
  "file": "app.js",
  "line": 27,
  "quote": "  const start = page * PAGE_SIZE;",
  "title": "Page index is 1-based in the label but 0-based in the slice, so page 1 skips the first 10 orders",
  "failing_case": "Load 25 orders. page starts at 1, so start=10 and the first 10 orders never show. Prev goes to page 0 and shows the first page, which is labelled 'Page 0'."
 },
 {
  "file": "app.js",
  "line": 34,
  "quote": "  document.getElementById(\"page\").textContent = `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}`;",
  "title": "Total page count is rounded down, and is 0 when there are fewer than 10 orders",
  "failing_case": "With 25 orders it shows 'of 2' although 3 pages exist. With 5 orders it shows 'Page 1 of 0'. It should use Math.ceil."
 },
 {
  "file": "app.js",
  "line": 47,
  "quote": "document.getElementById(\"prev\").onclick = () => { page--; renderTable(); };",
  "title": "Prev and Next are not bounded, and the filters do not reset the page",
  "failing_case": "Click Prev on page 1 and the page becomes 0, then -1, and the table is empty. Click Next past the end and the table is empty. Go to page 3, then search for something with few results, and the stale page number shows an empty table."
 },
 {
  "file": "app.js",
  "line": 18,
  "quote": "  const avg = revenue / orders.length;",
  "title": "Division by zero when no orders are returned",
  "failing_case": "A search with no matches gives orders=[], so avg = 0/0 = NaN and the card shows '$NaN'. Revenue is also divided by all orders, not just paid ones."
 },
 {
  "file": "app.js",
  "line": 13,
  "quote": "    if (o.customer.tier === \"gold\") t = t * 0.9;",
  "title": "The discount and tax are applied to o.total, which is probably already the paid amount. Revenue then disagrees with the Total column, which shows the raw o.total.",
  "failing_case": "A gold customer order with total 100 and status paid adds 97.43 to the revenue card. The table row shows $100."
 },
 {
  "file": "app.js",
  "line": 32,
  "quote": "    tb.innerHTML += `<tr><td><input type=\"checkbox\" data-id=\"${o.id}\"></td><td>${o.customer.name}</td><td>$${o.total}</td><td><span class=\"dot ${o.status}\"></span></td></tr>`;",
  "title": "Customer name is inserted as HTML without escaping (XSS). Using += on innerHTML inside the loop re-parses the table on every row, which is quadratic.",
  "failing_case": "A customer named '<img src=x onerror=alert(1)>' runs script when the table renders."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  tb.querySelectorAll(\"input\").forEach((c) => c.onchange = () => { if (c.checked) selected.push(c.dataset.id); });",
  "title": "Unchecking a box never removes the id from `selected`, and ids are duplicated on re-check. Selection also does not match the rendered checkboxes after paging or reloading.",
  "failing_case": "Check order 5, uncheck it, then click Refund. Order 5 is still refunded. Check, uncheck and check it again and the id is in the list twice."
 },
 {
  "file": "app.js",
  "line": 45,
  "quote": "document.getElementById(\"q\").oninput = load;",
  "title": "The search fires a request on every keystroke with no debounce, and responses can arrive out of order. An older slow response can overwrite the newer one.",
  "failing_case": "Type 'ab'. The response for 'a' arrives after the response for 'ab', so the table shows results for the wrong query."
 },
 {
  "file": "app.js",
  "line": 50,
  "quote": "  const r = await refund(selected);",
  "title": "There is no error handling or selection reset. `selected` is not cleared after a refund, there is no check for an empty selection, and the toast reports success regardless of the real result.",
  "failing_case": "Click Refund with nothing selected and the toast says 'Refunded 0 orders!'. A second refund click re-sends the same ids."
 },
 {
  "file": "api.js",
  "line": 11,
  "quote": "  fetch(`${API_BASE}/refunds`, { method: \"POST\", headers: { Authorization: \"Bearer \" + API_KEY, \"Content-Type\": \"application/json\" }, body: JSON.stringify({ ids }) });",
  "title": "The fetch is neither awaited nor checked, and refund() always returns {ok:true}. Failures and network errors are swallowed, with an unhandled rejection.",
  "failing_case": "The server returns 500 or the network is down. The UI still shows 'Refunded N orders!' and no refund happened."
 },
 {
  "file": "api.js",
  "line": 6,
  "quote": "  const res = await fetch(`${API_BASE}/orders?q=${query}&status=${status}`, { headers: { Authorization: \"Bearer \" + API_KEY } });",
  "title": "The query and status are not URL-encoded, and res.ok is not checked before res.json().",
  "failing_case": "Searching 'a&status=paid' or 'Smith & Sons' breaks or injects query parameters. A 401 or 500 error body is parsed as the orders list, so `for (const o of orders)` throws."
 },
 {
  "file": "api.js",
  "line": 3,
  "quote": "const API_KEY = \"__PLANTED_STRIPE_KEY__\";",
  "title": "A secret API key is hard-coded in client-side code that is shipped to every browser.",
  "failing_case": "Anyone who opens the page source or DevTools reads the key and can call the orders and refunds API."
 }
]
```
