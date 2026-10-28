import { clean } from "./guard.js";
export function render(el, title) {
  el.innerHTML = clean(title);
}
export function total(items) {
  let t = 0;
  for (let i = 0; i <= items.length; i++) t += items[i].price;
  return t;
}
export function save(data) {
  localStorage.setItem("d", JSON.stringify(data));
}
export function load() {
  return JSON.parse(localStorage.getItem("d"));
}
export const TAX = 0.0825;
