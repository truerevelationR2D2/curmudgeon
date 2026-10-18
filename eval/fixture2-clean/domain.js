// Business rules for orders. Pure functions: no DOM, no network.
// Rates in basis points so money stays in whole cents (no binary-fraction drift on half cents).
const GOLD_DISCOUNT_BP = 1000; // 10%
const SALES_TAX_BP = 825;      // 8.25%
const STATUSES = ["paid", "refunded", "pending"];

// Returns a clean order, or null when the record cannot be shown safely (no id or no numeric total).
function normaliseOrder(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id == null ? "" : String(raw.id);
  const total = Number(raw.total);
  if (!id || !Number.isFinite(total)) return null;
  const customer = raw.customer && typeof raw.customer === "object" ? raw.customer : {};
  return {
    id,
    total,
    status: STATUSES.includes(raw.status) ? raw.status : "unknown",
    customer: { name: customer.name == null ? "Unknown customer" : String(customer.name), tier: customer.tier === "gold" ? "gold" : "standard" },
  };
}

const applyBp = (cents, bp) => Math.round((cents * bp) / 10000);

// Revenue from one order, in cents, rounded half up per order. A refunded order was never counted as paid, so it nets to zero.
function orderRevenueCents(order) {
  if (order.status !== "paid") return 0;
  const cents = Math.round(order.total * 100);
  const discounted = order.customer.tier === "gold" ? applyBp(cents, 10000 - GOLD_DISCOUNT_BP) : cents;
  return applyBp(discounted, 10000 + SALES_TAX_BP);
}

// Amounts in dollars for display; average is null when there are no orders.
function summarise(orders) {
  const cents = orders.reduce((sum, o) => sum + orderRevenueCents(o), 0);
  return { revenue: cents / 100, count: orders.length, average: orders.length ? cents / orders.length / 100 : null };
}

function pageCount(itemCount, pageSize) {
  return Math.max(1, Math.ceil(itemCount / pageSize));
}

function clampPage(page, itemCount, pageSize) {
  return Math.min(Math.max(0, page), pageCount(itemCount, pageSize) - 1);
}

if (typeof module !== "undefined") module.exports = { normaliseOrder, orderRevenueCents, summarise, pageCount, clampPage };
