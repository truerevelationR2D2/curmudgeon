```json
[
  {
    "file": "store.js",
    "line": 53,
    "summary": "loadRecipes only checks that `name` is a string. `id` and `minutes` from storage are not validated, so malformed records pass through.",
    "failure_scenario": "Storage holds [{\"name\":\"Soup\"}] or minutes saved as a string. totalMinutes then returns NaN or a concatenated string such as \"020\", and render shows \"NaN min\". A record with no id renders data-id=\"undefined\". Delete then finds no recipe, `r` is undefined, and describe(undefined) throws a TypeError inside the click handler. The button silently does nothing and the record can never be removed."
  },
  {
    "file": "store.js",
    "line": 54,
    "summary": "A JSON.parse failure or blocked storage returns [] with no message, although the comment says app.js tells the user. app.js never does.",
    "failure_scenario": "The stored value is corrupt or truncated. The app starts empty and shows 'No recipes yet'. The next add or delete calls saveRecipes and overwrites the corrupt value, so recoverable data is lost permanently and the user was never warned."
  },
  {
    "file": "app.js",
    "line": 35,
    "summary": "The delete handler ignores the return value of saveRecipes, then reports 'Deleted' and re-renders regardless.",
    "failure_scenario": "Storage is full or blocked, so saveRecipes returns false. The UI says Deleted and the item vanishes. On reload the item is back, because the delete was never persisted and the user was not told. The add path handles this failure, but delete does not."
  },
  {
    "file": "app.js",
    "line": 33,
    "summary": "`r` can be undefined if the id is not found, for example duplicate or missing ids from storage or a stale DOM. describe(r) and `r.name` then throw. The describe comment claims it is never null.",
    "failure_scenario": "A stored record has no id, or the list was re-rendered between the click and the lookup. recipes.find returns undefined and confirm(`Delete ${describe(r)}?`) throws a TypeError. The delete silently fails with no feedback."
  },
  {
    "file": "util.js",
    "line": 43,
    "summary": "importRecipes is unused dead code, and it is buggy if wired in. It does not trim, skip blank lines or handle \\r. It does not validate names or NaN minutes, and a quoted comma splits the name.",
    "failure_scenario": "Importing \"Soup,20\\r\\n\\nCake,abc\" gives {name:\"Soup\",minutes:20}, then {name:\"\",minutes:NaN}, then {name:\"Cake\",minutes:NaN}. Empty-name and NaN records are accepted. totalMinutes becomes NaN and the blank-name entries are saved, and loadRecipes accepts them because the name is still a string."
  },
  {
    "file": "util.js",
    "line": 81,
    "summary": "getJson is dead code. Nothing calls it, and it is a network helper in an app whose README says nothing is sent anywhere.",
    "failure_scenario": "A future caller could use it to send requests, which contradicts the 'nothing is sent anywhere' claim. Until then it is unused code that reviewers must read for no benefit."
  },
  {
    "file": "app.js",
    "line": 21,
    "summary": "parseInt silently truncates input such as '1.5' or '12abc' to 1 or 12 instead of rejecting it.",
    "failure_scenario": "The user enters 1.5 minutes. The form's step defaults to 1, so browser validation normally catches it, but any bypass such as a pasted value is saved as 1 minute with no warning. Number() plus Number.isInteger would reject it."
  },
  {
    "file": "app.js",
    "line": 26,
    "summary": "The form is reset and the list re-rendered even when validation failed on the first branch or when saving failed. Keyboard focus is also never returned after delete re-renders the list.",
    "failure_scenario": "A keyboard user presses Delete. The focused button is destroyed by innerHTML replacement, so focus drops to the body and the user loses their place in the list. Screen-reader users hear only the status text."
  }
]
```