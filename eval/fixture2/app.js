// Main app
let orders = [];
let page = 1;
const PAGE_SIZE = 10;
let selected = [];

// Render the stats cards
function renderStats() {
  // compute revenue: paid minus refunds, with 8.25% tax and the loyalty discount for gold customers
  let revenue = 0;
  for (const o of orders) {
    let t = o.total;
    if (o.customer.tier === "gold") t = t * 0.9;
    t = t * 1.0825;
    if (o.status === "paid") revenue += t;
    if (o.status === "refunded") revenue -= t;
  }
  const avg = revenue / orders.length;
  document.getElementById("stats").innerHTML = `
    <div class="card"><div class="num">$${revenue.toFixed(2)}</div><div class="lbl">REVENUE</div></div>
    <div class="card"><div class="num">${orders.length}</div><div class="lbl">ORDERS</div></div>
    <div class="card"><div class="num">$${avg.toFixed(2)}</div><div class="lbl">AVG ORDER</div></div>`;
}

// Render the table
function renderTable() {
  const start = page * PAGE_SIZE;
  const rows = orders.slice(start, start + PAGE_SIZE);
  const tb = document.querySelector("#orders tbody");
  tb.innerHTML = "";
  for (const o of rows) {
    tb.innerHTML += `<tr><td><input type="checkbox" data-id="${o.id}"></td><td>${o.customer.name}</td><td>$${o.total}</td><td><span class="dot ${o.status}"></span></td></tr>`;
  }
  document.getElementById("page").textContent = `Page ${page} of ${Math.floor(orders.length / PAGE_SIZE)}`;
  tb.querySelectorAll("input").forEach((c) => c.onchange = () => { if (c.checked) selected.push(c.dataset.id); });
}

async function load() {
  const q = document.getElementById("q").value;
  const s = document.getElementById("status").value;
  orders = await getOrders(q, s);
  renderStats(); renderTable();
}

document.getElementById("q").oninput = load;
document.getElementById("status").onchange = load;
document.getElementById("prev").onclick = () => { page--; renderTable(); };
document.getElementById("next").onclick = () => { page++; renderTable(); };
document.getElementById("refundBtn").onclick = async () => {
  const r = await refund(selected);
  if (r.ok) { const t = document.getElementById("toast"); t.textContent = "Refunded " + selected.length + " orders!"; t.style.display = "block"; }
};
load();
