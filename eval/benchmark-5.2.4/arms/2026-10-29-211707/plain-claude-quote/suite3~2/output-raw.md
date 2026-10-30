```json
[
  {
    "file": "store.js",
    "line": 7,
    "quote": "    return Array.isArray(data) ? data.filter((r) => r && typeof r.name === \"string\") : [];",
    "title": "Loaded records are only checked for a string name. A missing id, or a minutes value that isn't a number, passes through.",
    "failing_case": "localStorage 'recipes' = '[{\"name\":\"Soup\",\"minutes\":\"20\"},{\"name\":\"Pie\"}]'. Both records load. totalMinutes then returns \"0\" + \"20\" + undefined, which is the string \"020undefined\". Alternatively it gives NaN, depending on the order of the records. The status line after the next add shows 'Total cooking time: NaN minutes' or a garbled string. Neither record has an id, so render writes data-id=\"undefined\"."
  },
  {
    "file": "app.js",
    "line": 33,
    "quote": "  if (!confirm(`Delete ${describe(r)}?`)) return;",
    "title": "`r` can be undefined, so describe(r) throws and the delete does nothing. The comment on describe() claims it is never null.",
    "failing_case": "Stored data has a recipe with no id, or two recipes with ids the page can't match (an old format, for example). Click Delete on it. The li has data-id=\"undefined\", `recipes.find((x) => x.id === \"undefined\")` returns undefined, and `describe(undefined)` throws a TypeError. The recipe can never be deleted."
  },
  {
    "file": "app.js",
    "line": 35,
    "quote": "  saveRecipes(recipes);",
    "title": "The result of the save on delete is ignored, yet the UI reports success.",
    "failing_case": "Storage is full or blocked. Delete a recipe. saveRecipes returns false, but the status says 'Deleted “X”.'. After a reload the recipe is back, because the removal was never persisted."
  },
  {
    "file": "store.js",
    "line": 9,
    "quote": "    return [];  // storage blocked or corrupt: start empty; app.js tells the user",
    "title": "The comment says app.js tells the user when loading fails, but app.js never does. A blocked or corrupt store looks like an empty one, and the next save overwrites it.",
    "failing_case": "localStorage 'recipes' holds corrupt JSON such as '{bad'. loadRecipes returns [] with no message. The user adds one recipe, and saveRecipes overwrites the existing data with just that recipe."
  },
  {
    "file": "app.js",
    "line": 45,
    "quote": "  return rows.map(([name, minutes]) => ({ id: newId(), name, minutes: Number(minutes) }));",
    "title": "importRecipes does no validation. Blank lines, a trailing newline, CRLF endings and names that contain commas all produce bad records. Nothing sanitises the name or the minutes.",
    "failing_case": "importRecipes(\"Soup,20\\n\") returns a second record {name:\"\", minutes:0}, because Number(undefined) is NaN and Number(\"\") is 0. CRLF input leaves \"\\r\" on the minutes field. The empty-name record would pass a plain filter on `typeof name === 'string'`."
  }
]
```