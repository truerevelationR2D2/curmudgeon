```json
[
  {
    "file": "store.js",
    "line": 53,
    "quote": "    return Array.isArray(data) ? data.filter((r) => r && typeof r.name === \"string\") : [];",
    "title": "Loaded recipes are only checked for a string name. A missing id or a non-numeric minutes value gets through, which breaks delete and the total.",
    "failing_case": "localStorage 'recipes' holds [{\"name\":\"Soup\"}]. The entry loads with no id, so render() writes data-id=\"undefined\". Clicking Delete makes recipes.find return undefined, and describe(r) throws 'Cannot read properties of undefined'. The recipe can never be deleted. If an entry instead has minutes as a string, e.g. {\"id\":\"1\",\"name\":\"A\",\"minutes\":\"5\"}, totalMinutes produces string concatenation or NaN after the next add."
  },
  {
    "file": "app.js",
    "line": 33,
    "quote": "  if (!confirm(`Delete ${describe(r)}?`)) return;",
    "title": "r is not checked for undefined, even though describe's comment says it is never null. The lookup fails whenever the id doesn't match, so the handler throws and nothing is deleted.",
    "failing_case": "A stored recipe without an id, or with a duplicate or non-string id such as the number 5. dataset.id is the string \"5\", so find with === returns undefined and describe(undefined) throws a TypeError."
  },
  {
    "file": "app.js",
    "line": 45,
    "quote": "  return rows.map(([name, minutes]) => ({ id: newId(), name, minutes: Number(minutes) }));",
    "title": "importRecipes does no validation. It keeps blank lines, doesn't trim, and lets NaN minutes through. The results are recipes that corrupt totalMinutes.",
    "failing_case": "importRecipes(\"Soup,20\\n\") returns a second row {name:\"\", minutes:0}. importRecipes(\"Stew,abc\") returns minutes NaN, so totalMinutes becomes NaN. A CRLF file leaves a trailing \\r on the minutes field. A name that contains a comma is split wrongly."
  }
]
```