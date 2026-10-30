```json
[
  {
    "file": "app.js",
    "line": 112,
    "summary": "Each click of Refund calls newIdempotencyKey(), so the key identifies a click and not the refund attempt.",
    "failure_scenario": "The user confirms a refund and the request times out after the server has already processed it. The UI says the refund was not confirmed. The selection is still set, so the user clicks Refund again. A new UUID is sent, the server treats it as a new refund, and the customers are refunded twice. The key needs to be kept for the same selection until the server confirms or the user changes the selection."
  },
  {
    "file": "app.js",
    "line": 107,
    "summary": "Any selected order can be refunded, whatever its status. Orders that are already 'refunded', 'pending' or 'unknown' are not excluded or warned about.",
    "failure_scenario": "The user ticks an already-refunded order and confirms. The dialog sums its total, and the POST sends its id. If the server does not reject it, the customer is refunded twice. The confirm dialog also overstates the amount by counting orders that cannot be refunded."
  },
  {
    "file": "app.js",
    "line": 147,
    "summary": "Selections persist across pages, but only the current page's rows are visible. The selection count includes hidden rows.",
    "failure_scenario": "The user ticks 3 orders on page 1, moves to page 2 and ticks 1 more. The button reads 'Refund 4 orders', and the dialog refunds all 4. Page 2 shows one checked row, so the user cannot see what the other 3 are. The only warning is the count in the confirm dialog."
  },
  {
    "file": "domain.js",
    "line": 33,
    "summary": "orderRevenueCents applies a 10% gold discount and 8.25% sales tax to raw.total. Revenue is therefore not the order total shown in the table.",
    "failure_scenario": "An API order with total 100.00 and tier 'gold' is shown as $100.00 in the table. The revenue stat adds 90 × 1.0825 = $97.43 for it, and a standard order adds $108.25. If the API total is already net of discount or inclusive of tax, revenue is double-adjusted. The Revenue stat will not reconcile with the visible Total column, and no source documents the rule."
  },
  {
    "file": "domain.js",
    "line": 42,
    "summary": "The average divides revenue by orders.length, which counts refunded, pending and unknown orders. These contribute 0 to revenue.",
    "failure_scenario": "Two orders: one paid at $100 and one refunded at $100. Revenue is $108.25 and the average is $54.12, not $108.25 per paid order. The 'Average per order' stat is diluted by every unpaid order and gives a misleading figure."
  },
  {
    "file": "app.js",
    "line": 119,
    "summary": "If the refund succeeds but the following load() fails, the failure is silent. load() catches its own errors, so the refund UI shows success, and load()'s error message overwrites nothing about the refund.",
    "failure_scenario": "The refund succeeds and the toast says 'Refunded 2 orders'. load() then fails on a network blip, shows 'Orders could not be loaded', and the table still lists the old statuses with the selection still ticked. The user sees stale data in which the orders still look refundable, and may click Refund again with a new idempotency key."
  },
  {
    "file": "app.js",
    "line": 100,
    "summary": "load() is not blocked while a refund is in flight, and the refund controls are not blocked while a search is loading.",
    "failure_scenario": "While a refund POST is pending, the debounced search timer fires load(), which clears state.selected. After the refund succeeds, the toast says 'Refunded N orders' based on the saved picked list, but the table is replaced with unrelated results. The user sees a mismatch between the success toast and the table, and the post-refund load() may be aborted or reordered by the earlier load."
  },
  {
    "file": "domain.js",
    "line": 15,
    "summary": "An unrecognised order status becomes 'unknown', but no CSS class and no filter option exist for it. Total strings like '' or null are treated as numeric zero.",
    "failure_scenario": "A record with total: null or total: '' becomes Number(null) = 0 and passes Number.isFinite. It is shown as a $0.00 order instead of being skipped as the 'no numeric total' comment says. The skipped-records note and the revenue figures are then wrong."
  },
  {
    "file": "styles.css",
    "line": 62,
    "summary": "The fixed-position toast sits at the bottom-right and can cover the pager buttons on a 390px viewport.",
    "failure_scenario": "At 390px, after a refund the 5-second toast overlaps the 'Next' button. The user cannot click it until the toast goes away. This contradicts the README claim that the page reflows at 390px."
  },
  {
    "file": "app.js",
    "line": 142,
    "summary": "The search input is not blocked while a refund is in flight, and the search input handler never cancels the pending debounce on Enter or blur.",
    "failure_scenario": "The user types a query, then changes the status select immediately. Both load() calls run, the debounce timer fires a second load(), and the second one aborts the first. The result is redundant requests, and loading and selection flicker."
  }
]
```