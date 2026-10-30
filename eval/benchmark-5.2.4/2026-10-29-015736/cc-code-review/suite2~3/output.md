```json
[
  {
    "file": "api.js",
    "line": 2,
    "summary": "A live-looking API key is hardcoded in client-side JS and sent from the browser.",
    "failure_scenario": "Anyone who loads api.js or opens DevTools can read the key and use it against the API. README line 6 says 'the API key never leaves the server', which is false."
  },
  {
    "file": "api.js",
    "line": 20,
    "summary": "refund() does not await the fetch and always returns {ok:true}, and it ignores the response status and any rejection.",
    "failure_scenario": "The network is down or the API returns 4xx/5xx. The UI still shows 'Refunded N orders!' although nothing was refunded, and the rejected promise goes unhandled. README line 9 says refunds are confirmed before they are sent, but no confirmation step exists."
  },
  {
    "file": "app.js",
    "line": 49,
    "summary": "Pagination is off by one: page starts at 1 but the slice start is page*PAGE_SIZE.",
    "failure_scenario": "On first load, page 1 shows orders 10-19 and the first 10 orders are never shown. 'Prev' goes to page 0, then to negative pages, which show an empty table. 'Next' has no upper bound."
  },
  {
    "file": "app.js",
    "line": 56,
    "summary": "The page count uses Math.floor, so the last partial page is dropped. It also gives 'of 0' for fewer than 10 orders.",
    "failure_scenario": "With 25 orders the label reads 'Page 1 of 2' when 3 pages are needed. With 5 orders it reads 'Page 1 of 0'."
  },
  {
    "file": "app.js",
    "line": 54,
    "summary": "customer.name and other API fields are interpolated into innerHTML without escaping, which allows XSS. innerHTML += inside the loop is also quadratic.",
    "failure_scenario": "A customer named '<img src=x onerror=...>' runs script in the dashboard, and the script can read the key from api.js. Rebuilding the whole tbody on every row also slows rendering badly for large lists, contradicting the 'renders 10,000 orders instantly' claim."
  },
  {
    "file": "app.js",
    "line": 57,
    "summary": "The selection handler only pushes ids and never removes them on uncheck. It also never clears or dedupes, and it is lost on re-render.",
    "failure_scenario": "The user checks order 5, unchecks it, and clicks Refund. Order 5 is still in `selected` and is refunded. Checking the same box twice sends duplicate ids. After paging or filtering, checkboxes are redrawn unchecked but `selected` still holds the old ids, so hidden orders get refunded."
  },
  {
    "file": "app.js",
    "line": 40,
    "summary": "Dividing by orders.length gives NaN when the list is empty. Revenue is also computed over unrelated rows and with questionable math.",
    "failure_scenario": "A search with no results sets avg to 0/0 = NaN and shows '$NaN'. Pending orders are ignored. Tax of 8.25% is applied to revenue, and the gold discount is applied to totals that are probably already discounted. The 'AVG ORDER' divides net revenue by all orders, including refunded and pending ones."
  },
  {
    "file": "api.js",
    "line": 15,
    "summary": "query and status are put into the URL without encodeURIComponent, no res.ok check is made, and out-of-order responses are not handled on every keystroke.",
    "failure_scenario": "Typing 'a&status=paid' or '#' corrupts or injects query parameters. A 401/500 JSON error body is assigned to `orders`, so orders.slice throws. Fast typing fires overlapping requests with no debounce, and a slower, stale response can overwrite the newer one."
  },
  {
    "file": "index.html",
    "line": 94,
    "summary": "The refund control is a non-focusable span with no role or keyboard handler, the checkboxes and inputs have no labels, and styles.css removes the focus outline.",
    "failure_scenario": "Keyboard and screen-reader users cannot trigger the refund action, since a span cannot be reached by Tab or activated with Enter. The inputs have no accessible name. `outline:none` on focus (styles.css line 122) removes the focus indicator. These contradict the README's 'Fully accessible, WCAG 2.1 AA' claim. Other failures include the contrast of #aaa on white, #c7c2f0 on purple, and 10px dots, and the status shown by colour only. Targets are about 20px, not 44px."
  },
  {
    "file": "README.md",
    "line": 8,
    "summary": "The pricing arithmetic is wrong.",
    "failure_scenario": "12 seats at $15 is $180 a month, or $2,160 a year. With 20% off that is $1,728, not $1,440 ($1,440 would be $120/seat/yr, i.e. $10/seat/month). The README also claims 'renders 10,000 orders instantly' with no measurement, and the code only renders a 10-row page."
  }
]
```