const listEl = document.getElementById("list");
const statusEl = document.getElementById("status");
let recipes = loadRecipes();

// The empty-state markup is a fixed string with no user data in it.
const EMPTY = "<li class=\"empty\">No recipes yet. Add your first one above.</li>";

function render() {
  if (!recipes.length) { listEl.innerHTML = EMPTY; return; }
  listEl.innerHTML = recipes.map((r) => `<li data-id="${escapeHtml(r.id)}">${escapeHtml(r.name)} <span class="mins">${Number(r.minutes)} min</span> <button type="button" class="del" aria-label="Delete ${escapeHtml(r.name)}">Delete</button></li>`).join("");
}

function describe(recipe) {
  // recipe is always one of `recipes`, so it is never null here (render and the delete handler are the only callers).
  return `${recipe.name}, ${recipe.minutes} minutes`;
}

document.getElementById("add").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = document.getElementById("name").value.trim();
  const minutes = parseInt(document.getElementById("minutes").value, 10);
  if (!name || !(minutes > 0)) { statusEl.textContent = "Give the recipe a name and a time in minutes."; return; }
  recipes.push({ id: newId(), name, minutes });
  if (saveRecipes(recipes)) statusEl.textContent = `Saved “${name}”. Total cooking time: ${totalMinutes(recipes)} minutes.`;
  else statusEl.textContent = "Couldn't save: your browser's storage is full or blocked. Your recipe is kept until you close this tab.";
  e.target.reset(); render();
});

listEl.addEventListener("click", (e) => {
  const b = e.target.closest("button.del"); if (!b) return;
  const id = b.closest("li").dataset.id;
  const r = recipes.find((x) => x.id === id);
  if (!confirm(`Delete ${describe(r)}?`)) return;
  recipes = recipes.filter((x) => x.id !== id);
  saveRecipes(recipes);
  statusEl.textContent = `Deleted “${r.name}”.`;
  render();
});

// shortcut: the list re-renders whole on each change; fine below a few hundred recipes, switch to keyed updates past that.
render();

function importRecipes(text) {
  const rows = text.split("\n").map((line) => line.split(","));
  return rows.map(([name, minutes]) => ({ id: newId(), name, minutes: Number(minutes) }));
}
