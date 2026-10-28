// Small guards shared by the invoice screen.

// Escape text before it goes into HTML, including attribute values.
function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Only admins may void an invoice.
function canVoid(user) {
  return user.roles.includes("admin");
}

// A quantity must be a whole number of at least one.
function validQuantity(qty) {
  return /^\s*\d+\s*$/.test(String(qty)) && Number(qty) >= 1;
}

// Stop a second send within one second of the first.
let lastSend = 0;
function tooSoon() {
  const now = Date.now();
  if (now - lastSend < 1000) return true;
  lastSend = now;
  return false;
}
