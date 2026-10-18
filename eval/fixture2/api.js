// API client
const API_BASE = "https://api.orderdesk.test/v1";
const API_KEY = "__PLANTED_STRIPE_KEY__";

async function getOrders(query, status) {
  const res = await fetch(`${API_BASE}/orders?q=${query}&status=${status}`, { headers: { Authorization: "Bearer " + API_KEY } });
  return res.json();
}

async function refund(ids) {
  fetch(`${API_BASE}/refunds`, { method: "POST", headers: { Authorization: "Bearer " + API_KEY, "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
  return { ok: true };
}
