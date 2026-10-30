```json
[
  {
    "file": "site/about.html",
    "line": 13,
    "summary": "A dev-only script from http://localhost:8080/reload.js is left in the production page.",
    "failure_scenario": "On shop.example.com, the page requests a script from http://localhost:8080. The request is blocked as mixed content and by the CSP, so the console shows errors. If a visitor has a local server on port 8080, the page would run that server's script. Remove the tag."
  },
  {
    "file": "site/about.html",
    "line": 10,
    "summary": "The meta CSP in about.html does not match the header CSP in _headers. Both policies apply to the page, so the stricter one wins.",
    "failure_scenario": "The _headers CSP allows only script-src 'self'. The meta CSP adds 'nonce-r4nd0m', which is a static value and no script tag carries it. The browser enforces both policies, so https://cdn.example.org/lib.js is blocked. Its integrity attribute makes no difference. The nonce is also guessable and gives no protection."
  },
  {
    "file": "_headers",
    "line": 2,
    "summary": "The header CSP sets script-src 'self' and default-src 'self', so every cross-origin script is blocked. It also omits frame-ancestors, form-action and base-uri.",
    "failure_scenario": "The cross-origin scripts on cdn.example.org (about.html and login.html) and stats.example.org (checkout.html) do not load. The login widget and the checkout stats script break silently. A header CSP of this shape also does nothing to stop form hijacking via a injected base tag or form action."
  },
  {
    "file": "site/checkout.html",
    "line": 38,
    "summary": "The card number field has no inputmode, maxlength or pattern. It is a plain text input.",
    "failure_scenario": "Payment form accepts any text with no client-side format hint, and mobile users get a full keyboard rather than a numeric one. Card data is entered directly into the merchant's own page rather than a hosted payment field, which widens PCI scope."
  },
  {
    "file": "site/about.html",
    "line": 18,
    "summary": "Link text says shop.example.com but the href points to www.example.com. The UK link text is example.co.uk but points to www.example.co.uk.",
    "failure_scenario": "The visible text does not match the destination, which is a misleading link. Users and crawlers are sent to a host different from the shop host that the canonical URL declares. If www.example.com is not the shop, visitors land on the wrong site."
  },
  {
    "file": "site/about.html",
    "line": 19,
    "summary": "The link text 'brochure.pdf' and 'index.html' do not describe their targets. 'index.html' points to https://docs.example.net/, not an index.html file.",
    "failure_scenario": "The label 'index.html' names a file the link does not open, and a user who sees the link text expects a different thing. The PDF link also gives no file-type or size warning."
  },
  {
    "file": "site/login.html",
    "line": 57,
    "summary": "The page invites users to pay a card bill at a third-party bank URL, shown as visible link text on the sign-in page.",
    "failure_scenario": "A sign-in page that tells people to enter payment or bank details at another domain looks like a phishing lure. It sits beside a password form, so a reviewer or a mail filter may flag the page. The copy is also unrelated to signing in."
  },
  {
    "file": "site/about.html",
    "line": 21,
    "summary": "The newsletter form posts email to /subscribe with no CSRF token, no autocomplete hint and no consent text.",
    "failure_scenario": "Any other site can submit a hidden cross-site POST that subscribes an arbitrary address. There is also no consent statement for collecting the email address, which can be a compliance problem."
  },
  {
    "file": "site/about.html",
    "line": 22,
    "summary": "The iframe embeds https://www.example.org/map without a sandbox attribute or a loading hint.",
    "failure_scenario": "The embedded third-party page can run scripts, navigate the top window and show popups with no restriction. With the CSP default-src 'self', the frame is also blocked from loading at all, so the map area is empty."
  },
  {
    "file": "site/login.html",
    "line": 61,
    "summary": "The password field has no autocomplete attribute, and the email field has none either. The sign-in form has no autocomplete=username or current-password.",
    "failure_scenario": "Password managers may fail to fill the form or may suggest the wrong saved entry. Users are pushed toward weaker, hand-typed passwords."
  }
]
```