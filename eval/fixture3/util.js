const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let lastId = 0;
function newId() {
  // Date.now() alone collides on fast clicks, so a counter breaks ties.
  const now = Date.now();
  lastId = now > lastId ? now : lastId + 1;
  return String(lastId);
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}
