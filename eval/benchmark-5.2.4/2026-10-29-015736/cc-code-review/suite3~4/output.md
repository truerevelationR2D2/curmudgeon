```json
[
  {
    "file": "app.js",
    "line": 66,
    "summary": "A recipe loaded from storage can lack a valid `id`, so the delete handler's `find` returns undefined and `describe(undefined)` throws.",
    "failure_scenario": "`loadRecipes` only checks `typeof r.name === 'string'`. A stored entry like {\"name\":\"x\",\"minutes\":5} with no id renders `data-id=\"undefined\"`. `dataset.id` is then the string 'undefined', which never equals the real `undefined` id, so `r` is undefined. Clicking Delete throws a TypeError inside `describe` (line 49), and the entry can never be removed. The comment on line 48 claims r is never null, which is wrong."
  },
  {
    "file": "store.js",
    "line": 87,
    "summary": "Loaded data is validated only for a string `name`; `minutes` and `id` are not checked, so `totalMinutes` can return NaN or a concatenated string.",
    "failure_scenario": "A stored item such as {\"name\":\"a\"} (no minutes) or {\"name\":\"a\",\"minutes\":\"30\"} passes the filter. `totalMinutes` then returns NaN, or '030…' from string concatenation. The status line then says 'Total cooking time: NaN minutes' after every save."
  },
  {
    "file": "store.js",
    "line": 89,
    "summary": "Corrupt or unreadable storage silently becomes an empty list, and the comment's claim that app.js tells the user is false. The next save overwrites the original data.",
    "failure_scenario": "If the JSON under 'recipes' is corrupt, `loadRecipes` returns []. app.js never reports it. The user adds one recipe, `saveRecipes` writes over the old value, and whatever was recoverable is lost without any warning."
  },
  {
    "file": "app.js",
    "line": 69,
    "summary": "The result of `saveRecipes` is ignored on delete, yet the status says 'Deleted'.",
    "failure_scenario": "If storage is full or blocked, the delete succeeds only in memory. The UI shows 'Deleted “X”.', and the recipe comes back on reload with no warning. The add path does report a failed save, so the two paths are inconsistent."
  },
  {
    "file": "app.js",
    "line": 55,
    "summary": "`parseInt` truncates or misreads values that `<input type=number>` accepts, so a different number is saved than the user typed.",
    "failure_scenario": "Typing '1e2' (valid in a number input, meaning 100) gives `parseInt('1e2', 10)` = 1, so the recipe is saved as 1 minute. '2.5' is saved as 2 with no message."
  },
  {
    "file": "app.js",
    "line": 77,
    "summary": "`importRecipes` is dead code, and it does no validation if it is ever called.",
    "failure_scenario": "Nothing calls it. If it were wired up, a trailing newline or a blank line would produce {name: undefined, minutes: NaN}. A name containing a comma would be truncated. Non-numeric minutes would pass through unchecked. Remove it, or validate its rows and filter out the invalid ones."
  },
  {
    "file": "util.js",
    "line": 15,
    "summary": "`getJson` is unused, and its `fetch` contradicts the README's 'nothing is sent anywhere'.",
    "failure_scenario": "It is dead code that adds network capability to an app documented as offline-only. A reviewer checking the privacy claim would have to rule it out. Remove it."
  },
  {
    "file": "app.js",
    "line": 71,
    "summary": "After Delete, `render()` rebuilds the list and drops the focused button, so keyboard focus is lost.",
    "failure_scenario": "A keyboard or screen-reader user presses Delete and confirms. The focused button is removed from the DOM and focus resets to the body. They must tab through the page again to reach the next item."
  },
  {
    "file": "app.js",
    "line": 59,
    "summary": "On a failed save the form is reset and the status message tells the user the recipe 'is kept until you close this tab', which may not hold.",
    "failure_scenario": "Storage is blocked. The recipe lives only in the `recipes` array and is lost on reload, and the status message does not clearly warn that the data will not persist. The next successful action can also overwrite the status text."
  },
  {
    "file": "app.js",
    "line": 74,
    "summary": "The 'shortcut' comment promises a few hundred recipes of headroom, but `render` rebuilds the whole `innerHTML` on every change and has no virtualization or measurement behind that figure.",
    "failure_scenario": "The threshold is an unmeasured claim in a comment. With large imported or stored lists, each add or delete re-renders the entire list."
  }
]
```