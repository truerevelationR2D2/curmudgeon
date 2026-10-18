const PAGE_SIZE = 10;
const SEARCH_DELAY_MS = 250;
const TOAST_MS = 5000;

const state = { orders: [], page: 0, selected: new Set(), refunding: false, loading: false };
let latestRequest = null;
let searchTimer = null;
let toastTimer = null;

const $ = (id) => document.getElementById(id);
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function setMessage(text, isError = false) {
  const el = $("message");
  el.textContent = text;
  el.classList.toggle("error", isError);
}

function showToast(text) {
  const t = $("toast");
  t.textContent = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.textContent = ""; }, TOAST_MS);
}

function renderStats() {
  const s = summarise(state.orders);
  $("stat-revenue").textContent = money.format(s.revenue);
  $("stat-count").textContent = String(s.count);
  $("stat-average").textContent = s.average == null ? "—" : money.format(s.average);
}

function renderRow(order) {
  const tr = document.createElement("tr");
  const pick = document.createElement("td");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = state.selected.has(order.id);
  box.setAttribute("aria-label", `Select order ${order.id}, ${order.customer.name}`);
  box.addEventListener("change", () => {
    if (box.checked) state.selected.add(order.id); else state.selected.delete(order.id);
    renderRefundButton();
  });
  pick.append(box);

  const name = document.createElement("td");
  name.textContent = order.customer.name;
  const total = document.createElement("td");
  total.className = "num";
  total.textContent = money.format(order.total);
  const status = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `status ${order.status}`;
  badge.textContent = order.status;
  status.append(badge);

  tr.append(pick, name, total, status);
  return tr;
}

function renderTable() {
  state.page = clampPage(state.page, state.orders.length, PAGE_SIZE);
  const start = state.page * PAGE_SIZE;
  const frag = document.createDocumentFragment();
  for (const o of state.orders.slice(start, start + PAGE_SIZE)) frag.append(renderRow(o));
  document.querySelector("#orders tbody").replaceChildren(frag);

  const pages = pageCount(state.orders.length, PAGE_SIZE);
  $("page").textContent = `Page ${state.page + 1} of ${pages}`;
  $("prev").disabled = state.page === 0;
  $("next").disabled = state.page >= pages - 1;
}

function selectedOrders() {
  return state.orders.filter((o) => state.selected.has(o.id));
}

function renderRefundButton() {
  const n = state.selected.size;
  const btn = $("refundBtn");
  btn.textContent = state.refunding ? "Refunding…" : n ? `Refund ${plural(n, "order")}` : "Refund selected";
  btn.disabled = state.refunding || state.loading || n === 0;
}

async function load() {
  if (latestRequest) latestRequest.abort();
  const controller = new AbortController();
  latestRequest = controller;
  state.loading = true;
  renderRefundButton();
  setMessage("Loading orders…");
  try {
    const { orders, skipped } = await getOrders($("q").value, $("status").value, controller.signal);
    if (latestRequest !== controller) return;
    state.orders = orders;
    state.page = 0;
    state.selected.clear();
    renderStats();
    renderTable();
    const notes = [];
    if (!orders.length) notes.push("No orders match this search.");
    if (skipped) notes.push(`${plural(skipped, "record")} could not be shown because the data is incomplete.`);
    setMessage(notes.join(" "));
  } catch (err) {
    if (err.name === "AbortError" || latestRequest !== controller) return;
    console.error("Loading orders failed", err);
    setMessage(`Orders could not be loaded. ${err.message}`, true);
  } finally {
    if (latestRequest === controller) { state.loading = false; latestRequest = null; renderRefundButton(); }
  }
}

function newIdempotencyKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function refundSelected() {
  const picked = selectedOrders();
  if (!picked.length || state.refunding) return;
  const amount = picked.reduce((sum, o) => sum + o.total, 0);
  if (!confirm(`Refund ${plural(picked.length, "order")} totalling ${money.format(amount)}? This sends money back to the customers.`)) return;

  state.refunding = true;
  renderRefundButton();
  try {
    await refund(picked.map((o) => o.id), newIdempotencyKey());
    showToast(`Refunded ${plural(picked.length, "order")}.`);
    await load();
  } catch (err) {
    console.error("Refund failed", err, picked.map((o) => o.id));
    setMessage(`The refund was not confirmed. ${err.message} Reload and check the order statuses before trying again.`, true);
  } finally {
    state.refunding = false;
    renderRefundButton();
  }
}

$("q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(load, SEARCH_DELAY_MS);
});
$("status").addEventListener("change", load);
$("prev").addEventListener("click", () => { state.page--; renderTable(); });
$("next").addEventListener("click", () => { state.page++; renderTable(); });
$("refundBtn").addEventListener("click", refundSelected);
load();
