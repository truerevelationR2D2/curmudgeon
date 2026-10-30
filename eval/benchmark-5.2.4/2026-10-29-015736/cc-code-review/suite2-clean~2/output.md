```json
[
  {
    "file": "app.js",
    "line": 120,
    "summary": "Refund is allowed for any selected order regardless of status, and the confirm amount sums raw order.total for all of them.",
    "failure_scenario": "The user ticks an already-refunded or pending order and clicks Refund. The confirm dialog quotes that order's total as money going back to the customer. The request is sent anyway, so the server either double-refunds or rejects the whole batch. The UI never filters to status === 'paid'."
  },
  {
    "file": "app.js",
    "line": 128,
    "summary": "A fresh Idempotency-Key is generated on every click, so the retry protection the README promises does not work for user retries.",
    "failure_scenario": "A refund times out or the connection drops after the server processed it. The user clicks Refund again, which generates a new UUID. The server sees a new key and refunds again. The README says 'a repeated request does not refund twice', but the key is per click, not per selection."
  },
  {
    "file": "app.js",
    "line": 129,
    "summary": "The refund response body is ignored, so partial failures are reported as full success.",
    "failure_scenario": "The server returns 200 with per-id results, or refunds only some ids. The toast still says 'Refunded N orders.' The README claims success is reported 'only after the server confirms it'. The code confirms only that the HTTP status was 2xx."
  },
  {
    "file": "domain.js",
    "line": 13,
    "summary": "Number(raw.total) coerces null, '', [] and false to 0 and true to 1, so these records pass validation instead of being skipped.",
    "failure_scenario": "The API sends { id: 'A1', total: null } or total: ''. The order is shown as $0.00 and is selectable for refund. The 'no numeric total' guard in the comment is bypassed, and the 'skipped' notice is never shown. Negative totals are also accepted."
  },
  {
    "file": "app.js",
    "line": 123,
    "summary": "The refund confirmation amount uses order.total, but the dashboard's revenue uses a gold discount plus tax, so the two figures disagree for the same order.",
    "failure_scenario": "A gold-tier paid order with total 100.00 contributes 98.18 to revenue. The refund dialog and the table show 100.00. The user cannot reconcile the figures. Which amount the customer actually receives is unspecified."
  },
  {
    "file": "domain.js",
    "line": 46,
    "summary": "summarise's average divides by all orders, including refunded, pending and unknown ones, which contribute 0 revenue.",
    "failure_scenario": "10 orders, 5 paid at $100 and 5 pending. 'Average per order' shows about half the true paid-order average. The statistic is misleading when the status filter is 'All'."
  },
  {
    "file": "app.js",
    "line": 144,
    "summary": "The status change handler calls load() without clearing the pending search debounce timer.",
    "failure_scenario": "The user types a query and changes the status within 250 ms. load() runs immediately, and the stale searchTimer fires again, causing a redundant second request and a second selection clear. The user's ticked checkboxes are wiped a moment after the first load settles."
  },
  {
    "file": "app.js",
    "line": 98,
    "summary": "Every load, including the post-refund reload and any search, silently clears the user's selection.",
    "failure_scenario": "The user ticks several orders, then types a search character or filters. The search reloads and clears all selections without notice. The refund button resets to 'Refund selected'. The user can believe a refund covers rows they ticked earlier."
  },
  {
    "file": "api.js",
    "line": 12,
    "summary": "A response body that is aborted mid-read throws AbortError out of res.json(), and the catch converts it to a generic ApiError.",
    "failure_scenario": "A superseded request is aborted after the headers arrive but during body read. The AbortError is wrapped as 'not valid JSON'. load() then relies only on the latestRequest check to hide it. Any caller without that check, or a refund, would show a misleading error. The AbortError guard at fetch time is not applied to the json() call."
  },
  {
    "file": "api.js",
    "line": 5,
    "summary": "There is no request timeout or 401/403 handling.",
    "failure_scenario": "The session expires and the proxy returns 401 or a redirected login HTML. The user sees 'The server answered 401' or 'not valid JSON' with no prompt to sign in again. A hung refund request keeps the UI on 'Refunding…' with the button disabled indefinitely."
  }
]
```