```json
[
 {
  "file": "app.js",
  "line": 33,
  "quote": "  if (!confirm(`Delete ${describe(r)}?`)) return;",
  "title": "Deleting a stored recipe that has no id throws, and the comment in describe() claims this can't happen. loadRecipes() only checks that name is a string, so a stored entry without an id is accepted. render() writes data-id=\"undefined\" for it. The click handler reads that as the string \"undefined\", so recipes.find(x => x.id === id) returns undefined and describe(undefined) throws a TypeError.",
  "failing_case": "Set localStorage.recipes to '[{\"name\":\"Soup\",\"minutes\":10}]' and reload. Click Delete on Soup. The click handler throws \"Cannot read properties of undefined (reading 'name')\", so the recipe can never be deleted."
 },
 {
  "file": "store.js",
  "line": 23,
  "quote": "  return list.reduce((sum, r) => sum + r.minutes, 0);",
  "title": "loadRecipes() does not validate minutes, so a missing or non-numeric value makes the sum NaN or a concatenated string.",
  "failing_case": "Set localStorage.recipes to '[{\"name\":\"A\",\"minutes\":\"5\"},{\"name\":\"B\"}]' and reload. Add a recipe. The status line says \"Total cooking time: NaN minutes\". With only string values such as \"5\", the sum becomes the string \"05…\"."
 },
 {
  "file": "app.js",
  "line": 45,
  "quote": "  return rows.map(([name, minutes]) => ({ id: newId(), name, minutes: Number(minutes) }));",
  "title": "importRecipes does no validation. Blank lines, a trailing newline or CRLF endings produce recipes with an empty or undefined name and NaN minutes. Names containing commas are truncated. Blank trailing lines are not skipped and the result is not saved.",
  "failing_case": "importRecipes(\"Soup,10\\n\") returns a second entry {name:\"\", minutes:NaN}. importRecipes(\"Soup,10\\r\\n\") gives minutes Number(\"10\\r\") = 10 for the first row, but a final blank line still yields {name:\"\", minutes:NaN}. That entry breaks totalMinutes and passes loadRecipes' name check."
 },
 {
  "file": "app.js",
  "line": 35,
  "quote": "  saveRecipes(recipes);",
  "title": "The result of saveRecipes is ignored on delete, while the add path reports failures. If storage is full or blocked, the status still says \"Deleted\", but the recipe returns on the next reload.",
  "failing_case": "With localStorage.setItem throwing, as in a private window or when the quota is exceeded, click Delete on a recipe. The UI says \"Deleted “X”.\" and removes it. After a reload the recipe is back."
 }
]
```
