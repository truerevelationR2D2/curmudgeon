const KEY = "recipes";

function loadRecipes() {
  try {
    const raw = localStorage.getItem(KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data.filter((r) => r && typeof r.name === "string") : [];
  } catch (e) {
    return [];  // storage blocked or corrupt: start empty; app.js tells the user
  }
}

function saveRecipes(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
    return true;
  } catch (e) {
    return false;
  }
}

function totalMinutes(list) {
  return list.reduce((sum, r) => sum + r.minutes, 0);
}
