// Home-screen grid math (owner decision 2026-11-17, option «الف»: make room, like a Samsung One UI home screen).
// Every item keeps the cell it was put in (x = column from the inline start, y = row, w x h cells); empty cells stay
// empty until the user fills them. Putting or growing an item over others makes room: the items it covers slide to
// the nearest free spot, the rest stay where they are (`makeRoom`). A grid narrower than a saved layout shows the
// items that stick out at the nearest free spot (`fitTo`); this only changes what is drawn until the next save.
// Used by the dashboard (8 to 16 columns, `MAX_COLS` x `ROWS`, backend/apps/dashboard/grid.py) and the patient form
// layout (each card a grid of its own). Node runs this file directly (tools/grid-math.test.mjs).

export const COLS = 8;
export const ROWS = 40;
export const MAX_COLS = 16;

export type Size = { id: string; w: number; h: number };
export type Item = Size & { x: number; y: number };

const overlaps = (a: Item, b: Item) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** True when `cand` stays inside a `cols` x `rows` grid and covers no cell of another item (its own id is ignored). */
export function fits(items: Item[], cand: Item, cols = COLS, rows = ROWS): boolean {
  if (cand.x < 0 || cand.y < 0 || cand.w < 1 || cand.h < 1 || cand.x + cand.w > cols || cand.y + cand.h > rows) return false;
  return items.every((o) => o.id === cand.id || !overlaps(o, cand));
}

/**
 * The free spot for `it` closest to (tx, ty) among `placed`, or null when none is left. A row away counts more
 * more than a column away, so an item pushed aside prefers its own row; ties go to the spot below.
 */
export function nearest(it: Size, placed: Item[], cols: number, tx: number, ty: number, rows = ROWS): Item | null {
  const w = Math.min(it.w, cols);
  let best: Item | null = null;
  let bd = Infinity;
  for (let y = 0; y + it.h <= rows; y++) {
    for (let x = 0; x + w <= cols; x++) {
      const d = Math.abs(y - ty) * 2.5 + Math.abs(x - tx) + (y < ty ? 0.25 : 0);
      if (d >= bd) continue;
      const cand = { id: it.id, w, h: it.h, x, y };
      if (fits(placed, cand, cols, rows)) { bd = d; best = cand; }
    }
  }
  return best;
}

/**
 * `moved` takes its cells; every other item it covers slides to the nearest free spot (top to bottom), the rest keep
 * their cells. Returns the whole new arrangement (`moved` first), or null when `moved` leaves the grid or a covered
 * item finds no room. The input is not changed.
 */
export function makeRoom(moved: Item, others: Item[], cols: number, rows = ROWS): Item[] | null {
  if (!fits([], moved, cols, rows)) return null;
  const placed: Item[] = [moved];
  const bumped: Item[] = [];
  for (const o of others) {
    if (o.id === moved.id) continue;
    (overlaps(o, moved) ? bumped : placed).push({ ...o });
  }
  bumped.sort((a, b) => a.y - b.y || a.x - b.x);
  for (const o of bumped) {
    const spot = nearest(o, placed, cols, o.x, o.y, rows);
    if (!spot) return null;
    placed.push(spot);
  }
  return placed;
}

/**
 * A stored arrangement drawn on `cols` columns: items that fit keep their cells; the others (sticking out on a
 * narrower grid, or overlapping) go to the nearest free spot, top to bottom. Same order as the input.
 */
export function fitTo(items: Item[], cols: number, rows = ROWS): Item[] {
  const placed: Item[] = [];
  const out = new Map<string, Item>();
  const order = [...items].sort((a, b) => a.y - b.y || a.x - b.x);
  for (const o of order) {
    const it = { ...o, w: Math.min(o.w, cols) };
    // A drawn layout may run past `rows` (it is never saved like this), so there is always a spot below the rest.
    const room = Math.max(rows, rowsUsed(placed) + it.h);
    const spot = fits(placed, it, cols, rows) ? it : nearest(it, placed, cols, it.x, it.y, room);
    placed.push(spot!);
    out.set(o.id, spot!);
  }
  return items.map((i) => out.get(i.id)!);
}

/** The first free spot in reading order for a new item, or null when the grid is full. */
export function firstFree(it: Size, placed: Item[], cols: number, rows = ROWS): Item | null {
  for (let y = 0; y + it.h <= rows; y++) {
    for (let x = 0; x + it.w <= cols; x++) {
      const cand = { ...it, x, y };
      if (fits(placed, cand, cols, rows)) return cand;
    }
  }
  return null;
}

/** How many columns a grid `width` px wide gets: as many `minCol` px columns as fit, from 8 up to 16. */
export function colsFor(width: number, gap: number, minCol = 120): number {
  return Math.max(COLS, Math.min(MAX_COLS, Math.floor((width + gap) / (minCol + gap))));
}

/** Clamp a size to an item's limits [w, h]. */
export function clampSize(w: number, h: number, min: number[], max: number[]): { w: number; h: number } {
  return { w: Math.min(max[0], Math.max(min[0], w)), h: Math.min(max[1], Math.max(min[1], h)) };
}

/** An item's cell as the CSS custom properties the grid stylesheets place it by (set through the CSSOM). */
export const cellVars = (i: Item) => ({ '--x': i.x + 1, '--y': i.y + 1, '--w': i.w, '--h': i.h });

/** Every 1 x 1 cell of a `cols` x `rows` grid (the editors draw them as empty wells). */
export function emptyCells(cols: number, rows: number): Item[] {
  const out: Item[] = [];
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) out.push({ id: `${x}:${y}`, x, y, w: 1, h: 1 });
  return out;
}

/** Rows a grid needs to show `items`, plus `spare` empty rows (the editors show two to drop into). */
export const rowsUsed = (items: Item[], spare = 0) => Math.max(0, ...items.map((i) => i.y + i.h)) + spare;
