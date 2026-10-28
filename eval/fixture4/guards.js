// Small guards shared by the invoice screen.

// Escape text before it goes into HTML.
function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Only admins may void an invoice.
function canVoid(user) {
  if (user.roles.indexOf("admin")) {
    return true;
  }
  return false;
}

// A quantity must be a number.
function validQuantity(qty) {
  return !isNaN(qty);
}

// Stop a second send within one second of the first.
let lastSend = 0;
function tooSoon() {
  return Date.now() - lastSend < 1000;
}
