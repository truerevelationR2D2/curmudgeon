// The browser holds no credential. It calls the same-origin proxy with the user's session cookie;
// the server adds the API key and decides whether this user may refund.
const API_BASE = "/api/v1";

class ApiError extends Error {}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(API_BASE + path, { credentials: "same-origin", ...options });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError("The server could not be reached. Check your connection and try again.");
  }
  if (!res.ok) throw new ApiError(`The server answered ${res.status} ${res.statusText}`.trim() + ".");
  try {
    return await res.json();
  } catch {
    throw new ApiError("The server sent a response that is not valid JSON.");
  }
}

// Resolves to { orders, skipped }: skipped counts records dropped as invalid.
async function getOrders(query, status, signal) {
  const params = new URLSearchParams({ q: query, status });
  const data = await request(`/orders?${params}`, { signal });
  if (!Array.isArray(data)) throw new ApiError("The server sent an unexpected response for the order list.");
  const orders = data.map(normaliseOrder).filter(Boolean);
  return { orders, skipped: data.length - orders.length };
}

// The idempotency key lets the server ignore a repeated refund request for the same attempt.
async function refund(ids, idempotencyKey) {
  return request("/refunds", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ ids }),
  });
}
