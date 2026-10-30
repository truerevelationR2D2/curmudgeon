```json
[
 {
  "file": "app.js",
  "line": 18,
  "quote": "  const avg = revenue / orders.length;",
  "title": "Average order divides by zero when there are no orders, so the card shows NaN or Infinity",
  "failing_case": "Type a search with no matches. orders is [], revenue is 0, and 0/0 is NaN, so the AVG ORDER card shows $NaN."
 },
 {
  "file": "app.js",
  "line": 13,
  "quote": "    if (o.customer.tier === \"gold\") t = t * 0.9;",
  "title": "The gold discount and tax are applied to the displayed revenue, but the table shows the raw total. Order amounts differ between the two. Revenue and average are also computed from the same adjusted figures.",
  "failing_case": "A gold customer's $100 paid order shows $100 in the table, but revenue counts 97.425."
 },
 {
  "file": "app.js",
  "line": 27,
  "quote": "  const start = page * PAGE_SIZE;",
  "title": "Page numbering is off by one. page starts at 1, so the first 10 orders are skipped. Page 0 is also reachable, and the page label shows 1-based numbers.",
  "failing_case": "With 25 orders, the initial view shows orders 11-20 and never shows the first 10 orders."
 },
 {
  "file": "app.js",
  "line": 34,
  "quote": "  document.getElementById(\"page\").textContent = `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}`;",
  "title": "The total page count uses floor instead of ceil. Zero is shown when there are fewer than 10 orders, and a partial last page is omitted.",
  "failing_case": "With 25 orders the label says 'Page 1 of 2' instead of 3 pages. With 5 orders it says 'of 0'."
 },
 {
  "file": "app.js",
  "line": 47,
  "quote": "document.getElementById(\"prev\").onclick = () => { page--; renderTable(); };",
  "title": "Prev and Next have no bounds checks, so page can go to 0 or negative, or past the end. A negative start makes slice return the wrong rows or an empty table.",
  "failing_case": "Click Prev twice. page is -1, start is -10, and slice(-10, 0) returns an empty table."
 },
 {
  "file": "app.js",
  "line": 48,
  "quote": "document.getElementById(\"next\").onclick = () => { page++; renderTable(); };",
  "title": "Next can go past the last page, which shows an empty table. page also isn't reset when a new search or filter loads.",
  "failing_case": "Go to page 3, then type a search that returns 5 orders. load() leaves page at 3, so the table is empty."
 },
 {
  "file": "app.js",
  "line": 32,
  "quote": "    tb.innerHTML += `<tr><td><input type=\"checkbox\" data-id=\"${o.id}\"></td><td>${o.customer.name}</td><td>$${o.total}</td><td><span class=\"dot ${o.status}\"></span></td></tr>`;",
  "title": "Customer name and other API fields go into innerHTML unescaped, which is XSS. Re-parsing the HTML on every += is also quadratic, and it drops the checkbox state.",
  "failing_case": "A customer named <img src=x onerror=alert(1)> runs script when the table renders."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  tb.querySelectorAll(\"input\").forEach((c) => c.onchange = () => { if (c.checked) selected.push(c.dataset.id); });",
  "title": "Unchecking never removes the id from selected, so duplicates accumulate. Checked boxes are not restored after re-render, and selections persist across pages and reloads.",
  "failing_case": "Check order 5, uncheck it, then click Refund. Order 5 is still refunded, because selected is ['5']."
 },
 {
  "file": "app.js",
  "line": 50,
  "quote": "  const r = await refund(selected);",
  "title": "Refund is sent without confirmation or an empty-selection check. After the refund, selected is never cleared and the orders are not reloaded. The toast always reports success.",
  "failing_case": "Click Refund selected with nothing selected. It posts an empty list and shows 'Refunded 0 orders!'. Clicking it twice re-sends the same ids."
 },
 {
  "file": "api.js",
  "line": 11,
  "quote": "  fetch(`${API_BASE}/refunds`, { method: \"POST\", headers: { Authorization: \"Bearer \" + API_KEY, \"Content-Type\": \"application/json\" }, body: JSON.stringify({ ids }) });",
  "title": "The fetch promise isn't awaited and its response isn't checked, and refund() always returns {ok:true}. Failures and network errors are reported as success, with an unhandled rejection.",
  "failing_case": "The API returns 500 or the network is down. The UI still shows 'Refunded N orders!'."
 },
 {
  "file": "api.js",
  "line": 6,
  "quote": "  const res = await fetch(`${API_BASE}/orders?q=${query}&status=${status}`, { headers: { Authorization: \"Bearer \" + API_KEY } });",
  "title": "The query is not URL-encoded, and res.ok is not checked. Special characters corrupt the query string, and an error response body is parsed as orders.",
  "failing_case": "Search 'a&status=paid' or 'Smith & Co'. The '&' splits the parameter. A 401 returns an error object, and orders.slice then throws."
 },
 {
  "file": "api.js",
  "line": 3,
  "quote": "const API_KEY = \"__PLANTED_STRIPE_KEY__\";",
  "title": "An API key is hardcoded in client-side source, so anyone loading the page can read it.",
  "failing_case": "Open DevTools or view api.js and copy the Bearer token."
 },
 {
  "file": "app.js",
  "line": 45,
  "quote": "document.getElementById(\"q\").oninput = load;",
  "title": "There is no debounce and no handling of out-of-order responses. A slow earlier response can overwrite a newer one.",
  "failing_case": "Type 'ab' quickly. The response for 'a' arrives after the one for 'ab', so the table shows results for 'a' while the box says 'ab'."
 },
 {
  "file": "index.html",
  "line": 19,
  "quote": "    <span class=\"refund\" id=\"refundBtn\">Refund selected</span>",
  "title": "The refund control is a span, not a button, so it can't be focused or used from the keyboard.",
  "failing_case": "Tab to the toolbar. The refund control is skipped, and Enter or Space can't trigger it."
 }
]
```
