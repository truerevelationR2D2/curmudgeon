```json
[
  {
    "file": "app.js",
    "line": 128,
    "summary": "A fresh Idempotency-Key is generated on every click, so the key cannot stop a user retry from refunding twice.",
    "failure_scenario": "The user confirms a refund and the server processes it, but the response is lost (timeout, dropped connection). The UI shows 'refund was not confirmed' and the selection is still there. The user clicks Refund again, newIdempotencyKey() returns a new UUID, and the server treats it as a new request, so the customers are refunded twice. The key should be created once per attempt and reused until the outcome is known."
  },
  {
    "file": "app.js",
    "line": 120,
    "summary": "Refund accepts any selected order whatever its status, and the confirmation sums o.total for all of them.",
    "failure_scenario": "The user selects an order that is already 'refunded', 'pending' or 'unknown' (every row has a checkbox). The confirm dialog promises to send that amount back and the request is sent. If the server does not reject it, the order is refunded twice or money is returned for an order that was never paid. The dialog also shows a total that includes orders that were never charged."
  },
  {
    "file": "domain.js",
    "line": 11,
    "summary": "Number(raw.total) turns null, '', [], false and whitespace into 0, so the 'no numeric total' check does not reject them.",
    "failure_scenario": "The API returns {id: 1, total: null} or {id: 2, total: ''}. Number() gives 0, which is finite, so the order is kept and shown as $0.00. It is not counted in 'skipped' and it is selectable for a refund. The incomplete record is silently displayed as a real zero-value order, and the comment says it should be dropped."
  },
  {
    "file": "app.js",
    "line": 130,
    "summary": "After a successful refund, load() resets state.page to 0 and clears the selection, and the toast is the only feedback.",
    "failure_scenario": "The user is on page 3, refunds two orders, and the table jumps back to page 1 with the keyboard focus lost. Separately, if the follow-up load() fails, it shows an error in #message while the toast says 'Refunded', and the stale table still shows the old statuses."
  },
  {
    "file": "app.js",
    "line": 145,
    "summary": "The pager buttons disable themselves after being activated, so keyboard focus is lost.",
    "failure_scenario": "A keyboard user presses Next on the second-to-last page. renderTable() sets next.disabled = true while it has focus, so focus drops to <body>. The user has to tab back to the pager from the top of the page. This contradicts the README claim that every control is reachable by keyboard."
  },
  {
    "file": "app.js",
    "line": 144,
    "summary": "A status change does not cancel a pending search debounce timer, so load() runs a second time.",
    "failure_scenario": "The user types in the search box and then changes the status within 250 ms. load() runs immediately, then searchTimer fires and calls load() again, which aborts the first request and sends a duplicate. The selection and page are reset twice, and anything the user selected in between is lost."
  },
  {
    "file": "domain.js",
    "line": 33,
    "summary": "orderRevenueCents rounds with Math.round, which rounds negative half-cents toward zero. It also applies the discount and tax to totals that may already include them.",
    "failure_scenario": "A credit with a negative total, such as -0.005 or a gold-tier -1.05 order, rounds differently from the 'half up per order' rule in the comment. The revenue figure then disagrees with what the billing system computes. The 'Average per order' also divides revenue by every order in the list, including refunded and pending ones, which understates the average per paid order."
  },
  {
    "file": "app.js",
    "line": 65,
    "summary": "Table and stats are rebuilt with no handling for focus or for the screen-reader announcement of the search results.",
    "failure_scenario": "Each search sets #message to an empty string when there are results, so the role=status region announces nothing about the result count. Screen-reader users get no feedback that the table changed. The README only admits that screen readers have not been tested."
  },
  {
    "file": "README.md",
    "line": 3,
    "summary": "The README states axe-core results and a '<100 ms with 10,000 orders' measurement that nothing in the repo supports. The 'checkboxes are 24 px' note also does not match the 44 px claim for fields and buttons.",
    "failure_scenario": "The repo has no test, script or benchmark that produces the axe or timing numbers, so a reviewer cannot recompute them. The renderTable() code only renders 10 rows, so a 10,000-order timing says nothing about the claim. The claims read as verified facts but cannot be checked."
  }
]
```