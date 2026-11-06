// Small DOM behaviours (legacy app.js enhanceFloat).
import type { Directive } from 'vue';

const FLOAT_TYPES = /^(text|email|tel|url|search|password|number)$/;
const syncs = new WeakMap<HTMLElement, () => void>();

// Floating labels on a .field: a labelled text box, text area or select shows its label inside the box and lifts
// it onto the border once the box is focused or filled. Legacy enhanced every .field on the page; installFloats()
// does the same for every .field Vue renders, and v-float stays for explicit use. Safe to call twice.
export function enhanceFloat(field: HTMLElement): void {
  if (syncs.has(field)) return;
  const label = field.querySelector(':scope > label[for]');
  const control = label && document.getElementById(label.getAttribute('for') ?? '');
  if (!control || !field.contains(control)) return;
  const isSelect = control.matches('select');
  if (!isSelect && !control.matches('textarea') && !(control.matches('input') && FLOAT_TYPES.test((control as HTMLInputElement).type))) return;
  const sync = () => field.classList.toggle('is-filled', isSelect || (control as HTMLInputElement).value !== '');
  syncs.set(field, sync);
  field.classList.add('float');
  if (control.matches('textarea')) field.classList.add('float-area');
  sync();
  control.addEventListener('input', sync);
  control.addEventListener('change', sync);
  // The calendar popup and digit grouping set values without typing.
  field.addEventListener('click', () => setTimeout(sync));
}

function enhanceWithin(root: ParentNode): void {
  if (root instanceof HTMLElement && root.matches('.field')) enhanceFloat(root);
  root.querySelectorAll<HTMLElement>('.field').forEach(enhanceFloat);
}

let pending = false;
// v-model sets a value without an input event; resync every floating field once after Vue has patched the DOM.
export function scheduleFloatSync(): void {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    document.querySelectorAll<HTMLElement>('.field.float').forEach((f) => syncs.get(f)?.());
  });
}

export function installFloats(root: HTMLElement): void {
  enhanceWithin(root);
  new MutationObserver((records) => {
    for (const r of records) r.addedNodes.forEach((n) => { if (n instanceof HTMLElement) enhanceWithin(n); });
  }).observe(root, { childList: true, subtree: true });
}

export const vFloat: Directive<HTMLElement> = {
  mounted(field) {
    enhanceFloat(field);
  },
  updated(field) {
    syncs.get(field)?.();
  },
};
