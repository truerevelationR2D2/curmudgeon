```json
[
  {
    "file": "store.js",
    "line": 53,
    "summary": "loadRecipes only checks that `name` is a string. Stored entries with a missing `id` or a non-numeric `minutes` are accepted.",
    "failure_scenario": "localStorage holds [{\"name\":\"x\"}] from an older version or a hand edit. It renders with data-id=\"undefined\" and `NaN min`. Clicking Delete makes `recipes.find(x => x.id === \"undefined\")` return undefined, because the real id is undefined and not the string. `describe(undefined)` then throws a TypeError, so the entry can never be deleted. If `minutes` is a string such as \"20\", totalMinutes concatenates strings (\"0\"+\"20\"...) and the Saved status shows a nonsense total."
  },
  {
    "file": "app.js",
    "line": 32,
    "summary": "The delete handler assumes `find` always returns a recipe, and the comment in describe() asserts that without any check.",
    "failure_scenario": "If the id lookup misses (the missing-id case above, or a stale node), `r` is undefined. `describe(r)` throws before the confirm dialog opens, and the click silently does nothing. The comment at line 14 states an invariant that nothing enforces."
  },
  {
    "file": "app.js",
    "line": 35,
    "summary": "The delete handler ignores the return value of saveRecipes and always reports \"Deleted\".",
    "failure_scenario": "Storage is full or blocked, so saveRecipes returns false. The UI says Deleted “X” and removes it from the list, but the recipe is still in localStorage and reappears on reload. The add path handles this failure and the delete path does not."
  },
  {
    "file": "store.js",
    "line": 55,
    "summary": "When storage is corrupt or blocked, loadRecipes returns [] silently. The comment says app.js tells the user, and app.js never does.",
    "failure_scenario": "The stored JSON is corrupt, or parse throws. The app starts empty and shows no warning. The next Save overwrites the whole key, so any recoverable data is destroyed."
  },
  {
    "file": "app.js",
    "line": 43,
    "summary": "importRecipes is dead code and would produce bad records if it were used.",
    "failure_scenario": "Nothing calls it. If it were wired up, it would not trim names or skip blank lines. A trailing newline would yield {name: undefined, minutes: 0}, and a non-numeric minutes value would give NaN. It would also bypass the `minutes > 0` validation and the `name` string filter in loadRecipes."
  },
  {
    "file": "util.js",
    "line": 12,
    "summary": "getJson is unused dead code. It is a network helper in an app whose README says nothing is sent anywhere.",
    "failure_scenario": "A reader or a plugin-review reviewer sees a fetch helper and has to check that it is never called. It contradicts the README statement \"nothing is sent anywhere\" and adds maintenance surface for no caller."
  },
  {
    "file": "app.js",
    "line": 21,
    "summary": "The minutes check uses parseInt, so decimal input is silently truncated and trailing junk is accepted. The 1–600 limit is not enforced in JS.",
    "failure_scenario": "Entering \"1.5\" stores 1 minute. Programmatic or paste input such as \"20abc\" stores 20. A value like 99999 passes the JS check if the HTML constraint is bypassed, because only `> 0` is tested."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "After a failed save, the new recipe stays only in memory, and the status message is replaced by nothing else. The list gives no indication of which items are unsaved.",
    "failure_scenario": "Storage is blocked. The user adds several recipes and each one overwrites the same warning. On reload everything is gone. The warning is also only in a polite live region, which is easy to miss."
  },
  {
    "file": "README.md",
    "line": 6,
    "summary": "The README line about \"3 recipes of 20, 35 and 45 minutes total 100 minutes\" is a hard-coded example that no code or test backs.",
    "failure_scenario": "The arithmetic is correct (20+35+45=100). The README presents it as a fact about the app, but it is not tied to the code or a fixture, so it goes stale unnoticed if totalMinutes changes."
  }
]
```