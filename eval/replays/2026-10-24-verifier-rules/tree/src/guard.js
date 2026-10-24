// Escapes text before it goes into HTML.
export function clean(text) { return String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`); }
