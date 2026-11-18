// Home-screen grid editor (owner decision 2026-11-17, option «الف», like a Samsung One UI home screen), shared by the
// dashboard and the patient form layout. One board is a CSS grid; each item element carries `data-g-id`.
//
// Pointer: press an item (anywhere except its links and buttons, or on its grip) and drag; it lifts and follows the
// pointer, a dashed spot shows where it will land, and the items it would cover slide to the nearest free spot
// (`makeRoom`). Letting go keeps that arrangement; a spot outside the grid or with no room left shows red and the
// item goes back. A tap selects the item: it gets a handle on each edge; dragging a handle resizes it in whole cells
// inside its limits, and neighbours slide away the same way.
// Keyboard on the grip: Space or Enter picks the item up, arrows move it one cell, Enter or Space drops it, Escape
// puts everything back; Shift + arrows resize it. The live region says each step.
import { computed, ref } from 'vue';
import { clampSize, fits, makeRoom } from './grid-math';
import type { Item } from './grid-math';
import { fa } from './fmt';

export type Side = 'top' | 'bottom' | 'start' | 'end';
type Limits = { min: number[]; max: number[] };

export function useGridEditor(o: {
  items: () => Item[];
  commit: (items: Item[]) => void;
  cols: () => number;
  rows: number;
  limits: (id: string) => Limits;
  label: (id: string) => string;
  say: (t: string) => void;
  board: () => HTMLElement | null;
  noRoom: string;
}) {
  const preview = ref<Item[] | null>(null);
  const ghost = ref<(Item & { ok: boolean }) | null>(null);
  const lifted = ref<string | null>(null);
  const carried = ref<string | null>(null);
  const sel = ref<string | null>(null);
  const shown = computed(() => preview.value ?? o.items());

  const elOf = (id: string) => o.board()?.querySelector<HTMLElement>(`[data-g-id="${CSS.escape(id)}"]`) ?? null;
  const sizeText = (i: Item) => fa(`${i.w}×${i.h}`);

  function geometry() {
    const b = o.board()!;
    const cs = getComputedStyle(b);
    const r = b.getBoundingClientRect();
    const gap = parseFloat(cs.columnGap) || 0;
    const rowGap = parseFloat(cs.rowGap) || 0;
    const row = parseFloat(cs.gridAutoRows) || parseFloat(cs.gridTemplateRows.split(' ')[0]) || 100;
    return { r, px: (r.width + gap) / o.cols(), py: row + rowGap, rtl: cs.direction === 'rtl' };
  }

  // Try `cand` against the current items: the arrangement with room made, or null when it does not fit. The result
  // keeps the items' order, so Vue never moves an element in the DOM (a moved element would lose the focus).
  function tryPlace(cand: Item): Item[] | null {
    const out = makeRoom(cand, o.items(), o.cols(), o.rows);
    if (!out) return null;
    const at = new Map(out.map((i) => [i.id, i]));
    return o.items().map((i) => at.get(i.id)!);
  }

  // ---- pointer: move ------------------------------------------------------------------------------------------
  // The board's style (pitch, direction) is read once per press; its position is read on each move.
  let op: null | {
    kind: 'move' | 'resize'; id: string; side?: Side; sx: number; sy: number; ex: number; ey: number;
    start: Item; moved: boolean; key: string; result: Item[] | null; g: ReturnType<typeof geometry>;
  } = null;

  function down(ev: PointerEvent, id: string) {
    if (ev.button !== 0 || op) return;
    const t = ev.target as HTMLElement;
    if (t.closest('a, input, select, textarea, label, .pl-x, .g-handle') || (t.closest('button') && !t.closest('[data-grip]'))) return;
    const el = elOf(id);
    if (!el) return;
    ev.preventDefault();
    const r = el.getBoundingClientRect();
    const g = geometry();
    const start = o.items().find((i) => i.id === id)!;
    op = { kind: 'move', id, sx: ev.clientX, sy: ev.clientY, ex: g.rtl ? r.right - ev.clientX : ev.clientX - r.left, ey: ev.clientY - r.top, start, moved: false, key: '', result: null, g };
    listen();
  }

  function handleDown(ev: PointerEvent, id: string, side: Side) {
    if (ev.button !== 0 || op) return;
    ev.preventDefault();
    ev.stopPropagation();
    const start = o.items().find((i) => i.id === id)!;
    op = { kind: 'resize', id, side, sx: ev.clientX, sy: ev.clientY, ex: 0, ey: 0, start, moved: false, key: '', result: null, g: geometry() };
    listen();
  }

  function listen() {
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', cancel);
    window.addEventListener('keydown', onEsc);
  }
  function unlisten() {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', cancel);
    window.removeEventListener('keydown', onEsc);
  }
  const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') cancel(); };

  function onMove(ev: PointerEvent) {
    if (!op) return;
    if (!op.moved && Math.hypot(ev.clientX - op.sx, ev.clientY - op.sy) < 5) return;
    op.moved = true;
    const g = { ...op.g, r: o.board()!.getBoundingClientRect() }; // the page may scroll while a card is carried
    const s = op.start;
    if (op.kind === 'move') {
      lifted.value = op.id;
      const el = elOf(op.id);
      if (el) el.style.transform = `translate(${ev.clientX - op.sx}px, ${ev.clientY - op.sy}px)`;
      const w = Math.min(s.w, o.cols());
      const raw = g.rtl ? (g.r.right - (ev.clientX + op.ex)) / g.px : (ev.clientX - op.ex - g.r.left) / g.px;
      const x = Math.max(0, Math.min(o.cols() - w, Math.round(raw)));
      const y = Math.max(0, Math.min(o.rows - s.h, Math.round((ev.clientY - op.ey - g.r.top) / g.py)));
      const key = `${x}:${y}`;
      if (key === op.key) return;
      op.key = key;
      const cand = { ...s, x, y, w };
      op.result = tryPlace(cand);
      // the lifted item keeps its own cell in the grid (it is drawn under the pointer); the others show the result
      preview.value = op.result ? op.result.map((i) => (i.id === s.id ? s : i)) : null;
      ghost.value = { ...cand, ok: Boolean(op.result) };
      o.say(op.result ? '' : o.noRoom);
      return;
    }
    const lim = o.limits(s.id);
    const dx = Math.round((g.rtl ? op.sx - ev.clientX : ev.clientX - op.sx) / g.px); // + = towards the inline end
    const dy = Math.round((ev.clientY - op.sy) / g.py);
    let { x, y, w, h } = s;
    if (op.side === 'end') w = clampSize(s.w + dx, h, lim.min, [Math.min(lim.max[0], o.cols() - s.x), lim.max[1]]).w;
    if (op.side === 'start') { w = clampSize(s.w - dx, h, lim.min, [Math.min(lim.max[0], s.x + s.w), lim.max[1]]).w; x = s.x + s.w - w; }
    if (op.side === 'bottom') h = clampSize(w, s.h + dy, lim.min, [lim.max[0], Math.min(lim.max[1], o.rows - s.y)]).h;
    if (op.side === 'top') { h = clampSize(w, s.h - dy, lim.min, [lim.max[0], Math.min(lim.max[1], s.y + s.h)]).h; y = s.y + s.h - h; }
    const key = `${x}:${y}:${w}:${h}`;
    if (key === op.key) return;
    op.key = key;
    const result = tryPlace({ ...s, x, y, w, h });
    if (!result) { o.say(o.noRoom); return; }
    op.result = result;
    preview.value = result;
    o.say(`اندازه‌ی ${sizeText({ ...s, w, h })}`);
  }

  function onUp() {
    const cur = op;
    finish();
    if (!cur) return;
    if (!cur.moved) { if (cur.kind === 'move') sel.value = sel.value === cur.id ? null : cur.id; return; }
    if (cur.result) {
      o.commit(cur.result);
      o.say(cur.kind === 'move' ? `«${o.label(cur.id)}» گذاشته شد.` : `اندازه‌ی ${sizeText(cur.result.find((i) => i.id === cur.id)!)}`);
    }
  }
  function cancel() { finish(); }
  function finish() {
    if (op) { const el = elOf(op.id); if (el) el.style.transform = ''; }
    op = null;
    preview.value = null;
    ghost.value = null;
    lifted.value = null;
    unlisten();
  }

  // ---- keyboard ---------------------------------------------------------------------------------------------
  let before: Item[] | null = null;
  function key(ev: KeyboardEvent, id: string) {
    const arrow = ev.key.startsWith('Arrow');
    const rtl = getComputedStyle(ev.currentTarget as HTMLElement).direction === 'rtl';
    const it = o.items().find((i) => i.id === id)!;
    // + = towards the inline end: in RTL that is ArrowLeft
    const dx = ev.key === 'ArrowLeft' ? (rtl ? 1 : -1) : ev.key === 'ArrowRight' ? (rtl ? -1 : 1) : 0;
    const dy = ev.key === 'ArrowDown' ? 1 : ev.key === 'ArrowUp' ? -1 : 0;
    if (arrow && ev.shiftKey) {
      ev.preventDefault();
      const lim = o.limits(id);
      const s = clampSize(it.w + dx, it.h + dy, lim.min, lim.max);
      const result = (s.w !== it.w || s.h !== it.h) && tryPlace({ ...it, ...s });
      if (result) o.commit(result);
      else if (s.w !== it.w || s.h !== it.h) { o.say(o.noRoom); return; }
      o.say(`اندازه‌ی ${sizeText(o.items().find((i) => i.id === id)!)}`);
      return;
    }
    if (ev.key === ' ' || ev.key === 'Enter') {
      ev.preventDefault();
      if (carried.value === id) { carried.value = null; before = null; o.say(`«${o.label(id)}» گذاشته شد.`); }
      else { carried.value = id; before = o.items(); o.say(`«${o.label(id)}» برداشته شد. با کلیدهای جهت جابه‌جا کنید.`); }
      return;
    }
    if (ev.key === 'Escape' && carried.value === id) {
      ev.preventDefault();
      if (before) o.commit(before);
      carried.value = null; before = null;
      o.say('جابه‌جایی لغو شد.');
      return;
    }
    if (arrow && carried.value === id) {
      ev.preventDefault();
      const cand = { ...it, x: it.x + dx, y: it.y + dy };
      const result = fits([], cand, o.cols(), o.rows) ? tryPlace(cand) : null;
      if (!result) { o.say(o.noRoom); return; }
      o.commit(result);
      o.say(`ستون ${fa(cand.x + 1)}، ردیف ${fa(cand.y + 1)}`);
    }
  }
  function blur(id: string) {
    if (carried.value === id) { carried.value = null; before = null; }
  }

  return { preview, ghost, lifted, carried, sel, shown, down, handleDown, key, blur, cancel };
}
