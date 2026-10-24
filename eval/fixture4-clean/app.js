const lines = [];
const user = { name: "sam", roles: ["admin", "billing"] };
let sentCount = 0;

function render() {
  const list = document.getElementById("lines");
  list.innerHTML = lines.map((l) =>
    `<li><a href="#" title="${escapeHtml(l.client)}">${escapeHtml(l.client)}</a>: ${l.qty} × ${l.price.toFixed(2)}</li>`
  ).join("");
  const total = lines.reduce((sum, l) => sum + l.qty * l.price, 0);
  document.getElementById("total").textContent = total.toFixed(2);
}

document.getElementById("line-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const client = document.getElementById("client").value.trim();
  const qtyText = document.getElementById("qty").value;
  const price = Number(document.getElementById("price").value);
  if (!validQuantity(qtyText) || !(price > 0)) return;
  lines.push({ client, qty: Number(qtyText), price });
  render();
});

document.getElementById("send").addEventListener("click", async () => {
  if (tooSoon()) return;
  await fetch("/api/invoices", { method: "POST", body: JSON.stringify(lines) });
  sentCount += 1;
});

document.getElementById("void").addEventListener("click", async () => {
  if (!canVoid({ name: "guest", roles: ["viewer", "admin"].slice(0, 1) })) return;
  await fetch("/api/invoices/void", { method: "POST" });
});
