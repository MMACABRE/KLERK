// Where a dragged item lands in a list of laid-out items (from the legacy public/js/layout-state.js, the only part
// of it the new app uses; tools/layout-drop.test.mjs checks it).
export type Rect = { left: number; top: number; width: number; height: number };

// The index (in the list) to insert a dragged item at: rects in list order, the pointer at (x, y). The item is
// inserted before the nearest rect when the pointer is before its centre in reading order (above its row, or on its
// row and before its centre: to its right in right-to-left), otherwise after it.
export function dropIndex(rects: Rect[], x: number, y: number, rtl: boolean): number {
  if (!rects.length) return 0;
  // The cell under the pointer wins; the nearest centre decides only outside every cell (BUG-1 root cause 2: over a
  // wide cell a narrow neighbour's centre is often nearer, so the drop went next to the wrong cell).
  let best = rects.findIndex((r) => x >= r.left && x <= r.left + r.width && y >= r.top && y <= r.top + r.height);
  if (best < 0) {
    best = 0;
    let bestDist = Infinity;
    rects.forEach((r, i) => {
      const dx = x - (r.left + r.width / 2);
      const dy = y - (r.top + r.height / 2);
      const d = dx * dx + dy * dy;
      if (d < bestDist) { bestDist = d; best = i; }
    });
  }
  const r = rects[best];
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  let before;
  if (y < cy - r.height / 2) before = true;
  else if (y > cy + r.height / 2) before = false;
  else before = rtl ? x > cx : x < cx;
  return before ? best : best + 1;
}
