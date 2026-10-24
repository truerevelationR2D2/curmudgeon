// Planted: real code the code rules must still catch.
export function render(el, html) {
  el.innerHTML += html;
  document.write(html);
  const data = JSON.parse(localStorage.getItem("cart"));
  try { save(data); } catch (e) {}
  setTimeout(() => eval(data.code), 0);
  return data;
}
