// The same module written safely.
export function render(el, text) {
  el.textContent = text;
  let data = null;
  try { data = JSON.parse(localStorage.getItem("cart")); } catch (e) { report(e); }
  try { save(data); } catch (e) { report(e); }
  return data;
}
