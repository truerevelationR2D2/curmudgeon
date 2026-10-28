// Decoys: every risky name below sits in a comment or a string, so none is a finding.
// Never call document.write( or eval( here, and don't use el.innerHTML += in a loop.
/* An empty catch like `catch (e) {}` swallows errors; JSON.parse( must be in a try. */
export const HELP = "Avoid document.write( and eval( in templates; prefer textContent over innerHTML +=";
export const RULE = 'setInterval( must be cleared; console.log( is for debugging';
export const SAMPLE = `try { x() } catch (e) {} // shown in the docs`;
export function safe(el, text) {
  el.textContent = text;
  return HELP.length + RULE.length + SAMPLE.length;
}
