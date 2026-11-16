// Dashboard layout v2 math (ADR-0014, owner decision 2026-11-16 "packed order"). The dashboard is an ordered list of
// items, each with a size w x h in grid cells. The view and the editor place the list with the same function,
// `pack`, on the same number of columns, so what is edited is what is shown: each item, in list order, goes to the
// first free spot (row by row, then column by column) where it fits, so later small items fill the holes above.
// Wider windows get more columns (`colsFor`), so zooming out shows more items per row instead of stretching them.
// The saved layout keeps the server's v2 shape {id, x, y, w, h} on 8 x 40 (backend/apps/dashboard/grid.py): the
// positions are the list packed on 8 columns, in list order, so the server's strict check (no overlap, inside the
// grid) holds and `orderOf` reads the list order back. Node runs this file directly (tools/grid-math.test.mjs).

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
 * The list placed on `cols` columns: each item, in order, at the first free spot in reading order where it fits
 * (an item wider than the grid is narrowed to it). Same order and length as the input; the input is not changed.
 */
export function pack(list: Size[], cols: number): Item[] {
  const placed: Item[] = [];
  for (const it of list) {
    const w = Math.min(it.w, cols);
    let spot: Item | null = null;
    for (let y = 0; !spot; y++) {
      for (let x = 0; x + w <= cols; x++) {
        const cand = { id: it.id, w, h: it.h, x, y };
        if (placed.every((o) => !overlaps(o, cand))) { spot = cand; break; }
      }
    }
    placed.push(spot);
  }
  return placed;
}

/** The list packed on the saved 8 columns, or null when it would end below row 40 (the server refuses that). */
export function packSaved(list: Size[]): Item[] | null {
  const items = pack(list, COLS);
  return items.every((i) => i.y + i.h <= ROWS) ? items : null;
}

/**
 * The list order of a stored layout. A layout saved by this editor is its list packed on 8 columns, in list order,
 * so the stored order is the list. Any other stored layout (the server's default, a v1 conversion, one saved by the
 * earlier fixed-cell editor) is read in reading order, row then column.
 */
export function orderOf(items: Item[]): Item[] {
  const again = pack(items, COLS);
  if (again.every((p, i) => p.x === items[i].x && p.y === items[i].y && p.w === items[i].w)) return [...items];
  return [...items].sort((a, b) => a.y - b.y || a.x - b.x);
}

/** How many columns a grid `width` px wide gets: as many `minCol` px columns as fit, from 8 up to 16. */
export function colsFor(width: number, gap: number, minCol = 120): number {
  return Math.max(COLS, Math.min(MAX_COLS, Math.floor((width + gap) / (minCol + gap))));
}

/** Clamp a size to an item's limits [w, h]. */
export function clampSize(w: number, h: number, min: number[], max: number[]): { w: number; h: number } {
  return { w: Math.min(max[0], Math.max(min[0], w)), h: Math.min(max[1], Math.max(min[1], h)) };
}
