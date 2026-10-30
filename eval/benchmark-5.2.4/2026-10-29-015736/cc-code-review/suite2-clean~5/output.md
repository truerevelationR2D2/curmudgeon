```json
[
  {
    "file": "app.js",
    "line": 226,
    "summary": "A new Idempotency-Key is generated on every click, so the server cannot deduplicate a retry of a refund that may have already gone through.",
    "failure_scenario": "The user confirms a refund and the response is lost (timeout or dropped connection) after the server processed it. The UI says 'not confirmed'. The user clicks Refund again with the same selection, which is still selected. newIdempotencyKey() returns a different key, so the server refunds a second time. The README claims a repeated request does not refund twice, but the key is not stable across retries of the same attempt."
  },
  {
    "file": "app.js",
    "line": 217,
    "summary": "selectedOrders() does not exclude orders that are already refunded, pending or of unknown status, so these orders can be submitted for refund.",
    "failure_scenario": "The user ticks an order with status 'refunded' or 'pending', or selects everything under the 'All' filter. The confirm dialog totals them and the POST sends their ids. The result is a double refund, or a refund of an unpaid order, unless the server independently rejects it. The confirm amount also includes refunded orders."
  },
  {
    "file": "api.js",
    "line": 29,
    "summary": "request() requires every successful response to be valid JSON, so an empty-bodied refund success (204 or 200 with no body) is reported as a failure.",
    "failure_scenario": "POST /refunds succeeds and returns 204. res.json() throws, so refund() throws an ApiError. refundSelected shows 'The refund was not confirmed' and skips load(). The money was sent, the list is stale, and the user is encouraged to retry, which makes a double refund likely (see the idempotency-key finding)."
  },
  {
    "file": "domain.js",
    "line": 63,
    "summary": "Number(raw.total) turns null, '', false and [] into a finite 0, so records with a missing total pass validation as $0.00 orders.",
    "failure_scenario": "The API returns {id: 1, total: null}. normaliseOrder keeps it as total 0. The row shows $0.00, the revenue stats are silently wrong, and the 'skipped' warning never fires. The comment says orders with no numeric total are rejected, but this case is not."
  },
  {
    "file": "domain.js",
    "line": 87,
    "summary": "The average divides paid-only revenue by the count of all orders, including refunded, pending and unknown ones.",
    "failure_scenario": "There are 1 paid order of $100 and 3 pending orders. The revenue is $108.25 but the average per order shows $27.06, understating the real figure. The 'Orders' stat also counts non-revenue orders. The labels do not say which denominator is used."
  },
  {
    "file": "app.js",
    "line": 206,
    "summary": "When a reload fails, the previous orders, stats and selection stay on screen with only an error message above them.",
    "failure_scenario": "The user changes the filter to 'refunded' and the request returns 500. The table and stats still show the old results for the previous filter, and the selection is kept. The refund button is enabled again (loading=false, selected.size>0), so the user can refund orders that no longer match the visible filter or search."
  },
  {
    "file": "app.js",
    "line": 193,
    "summary": "The refund-confirm total is a float sum of dollars, and the confirm dialog is the only guard against stale or off-page selections.",
    "failure_scenario": "Selections persist across pages, so orders on other pages are included in the count and total without being visible. Summing 0.1+0.2-style floats can produce a drifting amount, while the rest of the code uses integer cents. The dialog shows 'totalling' a number that may differ from what the server refunds."
  },
  {
    "file": "app.js",
    "line": 228,
    "summary": "After a successful refund, the load() call can be aborted or superseded, and a refund failure message is later overwritten by load()'s setMessage.",
    "failure_scenario": "A debounced search timer fires during or after the refund. load() clears the selection and state.page, and its setMessage('') replaces the refund error or the 'Loading' state. The user loses the 'check the order statuses' warning. The refund also ends up flagged as done while the visible list is mid-reload."
  },
  {
    "file": "index.html",
    "line": 275,
    "summary": "The caption hardcodes 'Orders, 10 per page', which duplicates PAGE_SIZE in app.js.",
    "failure_scenario": "Changing PAGE_SIZE leaves the screen-reader caption wrong. The README performance and accessibility claims also point to a single hand-edited number."
  },
  {
    "file": "README.md",
    "line": 5,
    "summary": "The README states that axe-core reports no WCAG A or AA violations and that the 100 ms search re-render was measured, but the repo has no test or script that backs either claim.",
    "failure_scenario": "A reviewer cannot reproduce the axe-core result or the 10,000-order timing, and neither command nor fixture is included. The claims are unverifiable, and the table rows are 40 px high (8 px padding around the 24 px checkbox), which is below the 44 px target size the README implies."
  }
]
```