// Drag and drop for the layout editors (legacy app.js enhanceFormLayout / enhanceDashLayout, round 8): a grip lifts
// its item with the pointer (past 6 px a ghost follows the pointer and the item itself becomes the dashed drop spot),
// or with the keyboard (Space or Enter picks it up, arrows move it, Enter drops it, Escape puts it back). A polite
// live region says what happened, with the legacy Persian texts.
//
// The items live in plain reactive arrays (the editor's draft); this module only moves entries between them, so Vue
// keeps rendering the DOM. Markup it expects, with a namespace `ns` per editor list:
//   group element:  data-<ns>-group="<group key>"
//   item element:   data-<ns>-id="<item id>"  :class="{ 'pl-ph': d.lifted.value === id, 'is-kb': d.carried.value === id }"
//   grip button:    data-grip  @pointerdown="d.down($event, id)" @keydown="d.key($event, id)" @blur="d.blur()"
// A flat list is one group. Boxes across cards are one group per card: arrows past the end of a card go on to the
// next card (legacy stepItem), and the pointer picks the card it is over.
import { nextTick, ref } from 'vue';
import { dropIndex } from './layout-state.js';

export type DragGroup<T> = { key: string; items: T[] };

type Rect = { left: number; top: number; width: number; height: number };

const fa = (n: number) => String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);

export function useDragList<T>(opts: {
  ns: string;
  groups: () => DragGroup<T>[];
  idOf: (item: T) => string;
  label: (id: string) => string;
  say: (text: string) => void;
}) {
  const lifted = ref<string | null>(null);
  const carried = ref<string | null>(null);
  let snapshot: T[][] | null = null;
  let moving = false;
  let drag: null | {
    id: string; grip: HTMLElement; pointerId: number; sx: number; sy: number; ox: number; oy: number;
    ghost: HTMLElement | null; groups: { key: string; rect: Rect; items: Rect[] }[]; at: string;
  } = null;

  const sel = (kind: 'id' | 'group', v: string) => `[data-${opts.ns}-${kind}="${CSS.escape(v)}"]`;
  const where = (id: string) => {
    const gs = opts.groups();
    for (let g = 0; g < gs.length; g++) {
      const i = gs[g].items.findIndex((it) => opts.idOf(it) === id);
      if (i >= 0) return { g, i, gs };
    }
    return null;
  };
  function moveTo(id: string, g: number, index: number) {
    const at = where(id);
    if (!at) return;
    const [item] = at.gs[at.g].items.splice(at.i, 1);
    const target = at.gs[g].items;
    target.splice(Math.max(0, Math.min(index, target.length)), 0, item);
  }
  const takeSnapshot = () => { snapshot = opts.groups().map((g) => [...g.items]); };
  function restore() {
    if (!snapshot) return;
    opts.groups().forEach((g, n) => g.items.splice(0, g.items.length, ...(snapshot![n] ?? [])));
    snapshot = null;
  }
  const placeText = (id: string) => {
    const at = where(id);
    return at ? `جای ${fa(at.i + 1)} از ${fa(at.gs[at.g].items.length)}` : '';
  };
  async function refocus(id: string) {
    moving = true;
    await nextTick();
    document.querySelector<HTMLElement>(`${sel('id', id)} [data-grip]`)?.focus();
    moving = false;
  }

  // ---- keyboard ----
  function key(e: KeyboardEvent, id: string) {
    if (carried.value === id) {
      const dir = ({ ArrowRight: -1, ArrowUp: -1, ArrowLeft: 1, ArrowDown: 1 } as Record<string, number>)[e.key];
      if (dir) {
        e.preventDefault();
        const at = where(id)!;
        const len = at.gs[at.g].items.length;
        if (dir < 0 && at.i > 0) moveTo(id, at.g, at.i - 1);
        else if (dir < 0 && at.g > 0) moveTo(id, at.g - 1, at.gs[at.g - 1].items.length);
        else if (dir > 0 && at.i < len - 1) moveTo(id, at.g, at.i + 1);
        else if (dir > 0 && at.g < at.gs.length - 1) moveTo(id, at.g + 1, 0);
        refocus(id);
        opts.say(placeText(id));
      } else if (e.key === 'Enter') { e.preventDefault(); drop(); }
      else if (e.key === 'Escape') {
        e.preventDefault();
        restore();
        carried.value = null;
        refocus(id);
        opts.say('لغو شد.');
      } else if (e.key === ' ') e.preventDefault();
      return;
    }
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      takeSnapshot();
      carried.value = id;
      opts.say(`برداشته شد: «${opts.label(id)}». با کلیدهای جهت جابه‌جا کنید، Enter برای گذاشتن، Esc برای لغو.`);
    }
  }
  function drop() {
    if (!carried.value) return;
    carried.value = null;
    snapshot = null;
    opts.say('گذاشته شد.');
  }
  const blur = () => { if (carried.value && !moving) drop(); };

  // ---- pointer ----
  const page = (r: DOMRect): Rect => ({ left: r.left + scrollX, top: r.top + scrollY, width: r.width, height: r.height });
  function lift(e: PointerEvent) {
    const d = drag!;
    const el = document.querySelector<HTMLElement>(sel('id', d.id));
    if (!el) return;
    const r = el.getBoundingClientRect();
    d.ox = r.left - d.sx;
    d.oy = r.top - d.sy;
    const ghost = el.cloneNode(true) as HTMLElement;
    ghost.removeAttribute(`data-${opts.ns}-id`);
    ghost.classList.add('pl-ghost-drag');
    ghost.style.width = `${Math.min(r.width, 420)}px`;
    ghost.style.height = `${Math.min(r.height, 260)}px`;
    ghost.style.overflow = 'hidden';
    document.body.append(ghost);
    d.ghost = ghost;
    document.body.classList.add('pl-dragging');
    // Every group's place and its other items' places, measured once in page coordinates: live measuring would
    // move the landing spot under the pointer as the list reflows.
    d.groups = opts.groups().map((g) => {
      const gel = document.querySelector<HTMLElement>(sel('group', g.key));
      const items = g.items.map(opts.idOf).filter((x) => x !== d.id)
        .map((x) => document.querySelector<HTMLElement>(sel('id', x)))
        .filter((x): x is HTMLElement => Boolean(x)).map((x) => page(x.getBoundingClientRect()));
      return { key: g.key, rect: gel ? page(gel.getBoundingClientRect()) : { left: 0, top: 0, width: 0, height: 0 }, items };
    });
    takeSnapshot();
    lifted.value = d.id;
    follow(e);
  }
  function follow(e: PointerEvent) {
    const d = drag!;
    if (!d.ghost) return;
    d.ghost.style.left = `${e.clientX + d.ox}px`;
    d.ghost.style.top = `${e.clientY + d.oy}px`;
    const x = e.clientX + scrollX;
    const y = e.clientY + scrollY;
    const dist = (r: Rect) => Math.hypot(Math.max(r.left - x, 0, x - r.left - r.width), Math.max(r.top - y, 0, y - r.top - r.height));
    let g = 0;
    d.groups.forEach((grp, n) => { if (dist(grp.rect) < dist(d.groups[g].rect)) g = n; });
    const index = dropIndex(d.groups[g].items, x, y, true);
    const spot = `${g}:${index}`;
    if (spot !== d.at) { d.at = spot; moveTo(d.id, g, index); }
  }
  function onMove(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (!drag.ghost) {
      if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 6) return;
      lift(e);
      return;
    }
    follow(e);
  }
  function end(keep: boolean) {
    if (!drag) return;
    const d = drag;
    drag = null;
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    window.removeEventListener('keydown', onEsc, true);
    if (!d.ghost) return;
    d.ghost.remove();
    document.body.classList.remove('pl-dragging');
    lifted.value = null;
    if (keep) { snapshot = null; opts.say('گذاشته شد.'); } else { restore(); opts.say('لغو شد.'); }
  }
  const onUp = (e: PointerEvent) => { if (drag && e.pointerId === drag.pointerId) end(true); };
  const onCancel = (e: PointerEvent) => { if (drag && e.pointerId === drag.pointerId) end(false); };
  const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape' && drag) { e.preventDefault(); end(false); } };
  function down(e: PointerEvent, id: string) {
    if (drag || !e.isPrimary || e.button !== 0 || carried.value) return;
    const grip = e.currentTarget as HTMLElement;
    drag = { id, grip, pointerId: e.pointerId, sx: e.clientX, sy: e.clientY, ox: 0, oy: 0, ghost: null, groups: [], at: '' };
    // Window listeners, not pointer capture: Vue moves item nodes while the list reorders, and moving the captured
    // grip would end the capture.
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    window.addEventListener('keydown', onEsc, true);
  }

  return { lifted, carried, down, key, blur };
}
