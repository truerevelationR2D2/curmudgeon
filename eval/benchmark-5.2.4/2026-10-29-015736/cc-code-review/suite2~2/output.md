```json
[
  {
    "file": "api.js",
    "line": 3,
    "summary": "A Stripe-style secret key is hardcoded in client-side JS and sent as a Bearer token from the browser.",
    "failure_scenario": "Anyone who loads api.js or opens DevTools can read the key and call the refunds and orders endpoints. This contradicts the README claim that 'the API key never leaves the server'."
  },
  {
    "file": "api.js",
    "line": 11,
    "summary": "refund() does not await the fetch and always returns {ok:true}, so HTTP errors and network failures are ignored.",
    "failure_scenario": "The refund POST returns 401 or 500, or the network is down. The UI still shows 'Refunded N orders!', and a rejected promise goes unhandled. The user believes money was refunded when it was not."
  },
  {
    "file": "app.js",
    "line": 40,
    "summary": "Pagination is off by one. page starts at 1 but start = page * PAGE_SIZE, so the first 10 orders are skipped.",
    "failure_scenario": "On first load the table shows orders 10-19. Prev goes to page 0, which shows the first 10, and then to negative pages, where slice(-10, 0) is empty. Nothing clamps page at either end."
  },
  {
    "file": "app.js",
    "line": 47,
    "summary": "The page count uses Math.floor, so the last partial page is dropped, and an empty list shows 'Page 1 of 0'.",
    "failure_scenario": "With 25 orders it shows 'Page 1 of 2' although there are 3 pages. With 5 orders it shows 'of 0'. Next can run past the last page with no bound."
  },
  {
    "file": "app.js",
    "line": 48,
    "summary": "The selection handler only pushes ids and never removes them on uncheck. It also allows duplicates, and the checkboxes lose their checked state after a page change or re-render.",
    "failure_scenario": "The user checks order A, unchecks it, then clicks Refund. A is still in `selected` and gets refunded. Checking the same box twice sends the id twice. After load() the selection survives in the array but the checkboxes show as unchecked."
  },
  {
    "file": "app.js",
    "line": 45,
    "summary": "Customer name and other API fields are interpolated into innerHTML unescaped, which is an XSS hole. The table is also rebuilt with `innerHTML +=` inside the loop, which is quadratic.",
    "failure_scenario": "A customer named `<img src=x onerror=...>` runs script in the dashboard, which also holds the API key. Rebuilding the table once per row re-parses all earlier rows every time."
  },
  {
    "file": "app.js",
    "line": 31,
    "summary": "avg = revenue / orders.length gives NaN when the list is empty. Revenue also applies tax to refunds and subtracts the gold discount inconsistently.",
    "failure_scenario": "A search with no matches makes `$NaN` show in the AVG ORDER card. The average divides net revenue (paid minus refunded) by all orders, including pending ones, so it is not an average order value."
  },
  {
    "file": "api.js",
    "line": 6,
    "summary": "The query and status are put into the URL without encodeURIComponent, and res.ok is not checked. Every keystroke also fires a request with no debounce and no stale-response guard.",
    "failure_scenario": "Searching 'a&status=refunded' or 'x#' alters the query string. An error response body is parsed as the orders list, so `orders.slice` or `for...of` throws. Out-of-order responses can overwrite newer results."
  },
  {
    "file": "index.html",
    "line": 85,
    "summary": "The 'Refund selected' control is a non-focusable <span> with a click handler, and there is no confirmation step before refunding. The README claims refunds are confirmed.",
    "failure_scenario": "Keyboard and screen-reader users cannot reach or activate it. One click immediately sends refunds for the selected ids with no confirm dialog. The `selected` array is also not cleared after a refund, so a second click re-sends the same ids."
  },
  {
    "file": "README.md",
    "line": 5,
    "summary": "The README makes claims the code contradicts: WCAG AA with 44px targets, 10,000 orders rendered instantly, and the $1,440 price.",
    "failure_scenario": "styles.css removes focus outlines (`outline:none`), uses #aaa text on white, and styles buttons at 12px with 2px padding. The table has a fixed 1000px width, and the animated toast never respects reduced motion. The table shows only 10 rows per page and is rebuilt quadratically. The price is also wrong: 12 x $15 x 12 months x 0.8 = $1,728, not $1,440."
  }
]
```