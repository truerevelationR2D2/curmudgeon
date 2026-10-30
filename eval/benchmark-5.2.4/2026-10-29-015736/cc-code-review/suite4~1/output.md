```json
[
  {
    "file": "guards.js",
    "line": 10,
    "summary": "canVoid uses indexOf's truthiness, so the check is inverted: admins are denied and almost every non-admin is allowed.",
    "failure_scenario": "indexOf returns -1 when the role is absent, and -1 is truthy. For user sam with roles [viewer, billing], indexOf('admin') is -1, so canVoid returns true and a non-admin can void invoices. A user whose roles are ['admin'] gets 0, which is falsy, so the real admin is refused. A user with ['admin', 'x'] gets 0, also refused. Use roles.includes('admin')."
  },
  {
    "file": "app.js",
    "line": 28,
    "summary": "lastSend is never updated, so the one-second send guard never triggers. A double click sends the invoice twice.",
    "failure_scenario": "tooSoon() compares Date.now() with lastSend, which stays 0 forever. It always returns false. Nothing sets lastSend, and there is no in-flight lock while the await fetch is pending. Two quick clicks on Send POST the same invoice twice. This produces a duplicate invoice. Set lastSend = Date.now() before the fetch, or disable the button while the request runs."
  },
  {
    "file": "guards.js",
    "line": 18,
    "summary": "validQuantity uses !isNaN on a string, so it accepts an empty, whitespace-only, negative, zero, fractional or Infinity quantity.",
    "failure_scenario": "The qty field is optional and is not marked required. If it is empty, isNaN('') is false, so validQuantity returns true and Number('') gives 0. A line with qty 0 is pushed. '-5' passes, so the total goes negative. '2.5' and '1e9' pass. 'Infinity' passes, and the total becomes Infinity or NaN. Require Number.isInteger(Number(q)) && Number(q) > 0, and reject blank input."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "escapeHtml does not escape double quotes, and its output is placed in a double-quoted title attribute, which allows attribute injection (XSS).",
    "failure_scenario": "A client name such as x\" onmouseover=\"alert(1) is passed through escapeHtml unchanged, because the function escapes only &, < and >. It lands in title=\"...\" and closes the attribute. The injected onmouseover handler then runs on hover. Escape \" and ' too, or build the DOM with textContent and setAttribute."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "The send request sets no Content-Type header, and the code has no try/catch and does not guard against an empty invoice.",
    "failure_scenario": "fetch with a JSON string body defaults to Content-Type text/plain, so a server expecting JSON can reject or mis-parse it. A network failure makes fetch reject, which gives an unhandled rejection with no user feedback, and the button stays usable. Clicking Send with lines empty posts an empty invoice. The void request also sends no invoice id, so the server cannot tell which invoice to void."
  },
  {
    "file": "app.js",
    "line": 19,
    "summary": "The submit handler fails silently on invalid input and does not clear the form after a valid add. The price check accepts Infinity and uses an empty string as 0.",
    "failure_scenario": "A user who types abc as the quantity gets no message, because the handler returns without feedback. A price of '1e999' gives Infinity, and Infinity > 0 is true. After a valid add the inputs keep their values, so a double submit adds a duplicate line. The client side check is the only validation, and the title says no more than that."
  },
  {
    "file": "app.js",
    "line": 2,
    "summary": "The client-side role check is the only guard for the void action. The user object is hard-coded in the browser, so the permission check is cosmetic and can be bypassed.",
    "failure_scenario": "The user and roles are literals in app.js. Anyone can edit them in devtools, or call fetch('/api/invoices/void') directly. Unless the server also enforces the admin role, any signed-in user can void. The fix is to enforce the role on the server and make the client check a UI hint only."
  },
  {
    "file": "app.js",
    "line": 8,
    "summary": "The href=\"#\" link in each line has no purpose and jumps the page to the top when clicked.",
    "failure_scenario": "Each rendered line wraps the client name in <a href=\"#\">. Clicking it changes the URL hash and scrolls to the top, and keyboard users get an extra tab stop with no action. It should be plain text, or a button or link with a real target."
  },
  {
    "file": "index.html",
    "line": 16,
    "summary": "The qty and price inputs lack required, type and min attributes, so the browser does not validate them.",
    "failure_scenario": "Only client is marked required. Submitting with qty or price blank is accepted by the browser and reaches the handler, which rejects it silently. A user on a phone gets no hint about what was wrong. Using type=number with min and step, plus required, gives native validation and messages."
  }
]
```