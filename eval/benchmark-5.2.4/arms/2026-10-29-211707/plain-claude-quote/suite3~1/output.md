```json
[
 {
  "file": "app.js",
  "line": 33,
  "quote": "  if (!confirm(`Delete ${describe(r)}?`)) return;",
  "title": "r from recipes.find is not guaranteed to exist, contrary to the comment on describe(). When the lookup fails, describe(undefined) throws and the click handler dies. This is reachable with stored recipes that have no id or a non-string id.",
  "failing_case": "Stored recipe {\"id\":123,\"name\":\"A\",\"minutes\":5}. The DOM data-id is the string \"123\", but x.id === id compares number 123 to string \"123\" and fails. r is undefined, and clicking Delete throws a TypeError."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  saveRecipes(recipes);",
  "title": "The result of saveRecipes on delete is ignored, so the status message says 'Deleted' even when the save failed. The recipe comes back after a reload.",
  "failing_case": "With storage full or blocked, click Delete on a recipe. The UI shows 'Deleted “X”.' and removes it, but localStorage is unchanged, so after a reload the recipe is back."
 },
 {
  "file": "app.js",
  "line": 44,
  "quote": "  const rows = text.split(\"\\n\").map((line) => line.split(\",\"));",
  "title": "importRecipes does no validation. A trailing newline, a blank line or CRLF produces empty or garbled rows. Names with commas are truncated. A missing or invalid minutes value becomes 0 or NaN, which the add form would never accept. Rows with an empty name are kept.",
  "failing_case": "Input \"Soup,20\\n\" yields [{name:\"Soup\",minutes:20},{name:\"\",minutes:0}], an empty-name recipe with 0 minutes. Input \"Soup,20\\r\\nPie,abc\" yields minutes NaN for Pie. Calling it on \"Soup\" gives minutes NaN, and totalMinutes then returns NaN."
 }
]
```
