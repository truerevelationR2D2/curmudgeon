const lines = [];
const user = { name: "sam", roles: ["viewer", "billing"] };  // the signed-in user
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
  const res = await fetch("/api/invoices", { method: "POST", body: JSON.stringify(lines) });
  if (!res.ok) { alert("The invoice was not sent. Try again."); return; }
  sentCount += 1;
});

document.getElementById("void").addEventListener("click", async () => {
  if (!canVoid(user)) return;
  const res = await fetch("/api/invoices/void", { method: "POST" });
  if (!res.ok) alert("The invoice was not voided.");
});
