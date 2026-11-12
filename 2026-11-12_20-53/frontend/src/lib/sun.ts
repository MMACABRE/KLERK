// The sign-in sun (legacy app.js enhanceSun): it leans toward the mouse, can be grabbed and pulled on a rubber band,
// and springs back when let go. Its highlight follows the pointer. Skipped under reduced motion. Positions are set
// through the CSSOM (style.translate, custom properties), which the CSP allows; no style attribute is written.
// Returns a function that removes every listener (the page calls it when it unmounts).
export function enhanceSun(sun: HTMLElement): () => void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => {};
  const panel = sun.closest<HTMLElement>('.auth-side');
  if (!panel) return () => {};
  const off = new AbortController();
  const opts = { signal: off.signal };
  const pos = { x: 0, y: 0 };
  const vel = { x: 0, y: 0 };
  const target = { x: 0, y: 0 };
  let grab: { x: number; y: number } | null = null;
  let frame = 0;
  const clamp = (v: number, max: number) => Math.max(-max, Math.min(max, v));
  // Rubber band: the further it is pulled, the less it follows (approaches `max`, never passes it).
  const band = (d: number, max: number) => Math.sign(d) * max * (1 - 1 / (Math.abs(d) / max + 1));
  const center = () => {
    const r = sun.getBoundingClientRect();
    return { x: r.left + r.width / 2 - pos.x, y: r.top + r.height / 2 - pos.y };
  };
  const light = (dx: number, dy: number) => {
    const d = Math.hypot(dx, dy) || 1;
    sun.style.setProperty('--hx', `${50 + (dx / d) * 24}%`);
    sun.style.setProperty('--hy', `${50 + (dy / d) * 24}%`);
  };
  const step = () => {
    const k = grab ? 0.35 : 0.09;
    const damping = grab ? 0.55 : 0.82;
    for (const axis of ['x', 'y'] as const) {
      vel[axis] = (vel[axis] + (target[axis] - pos[axis]) * k) * damping;
      pos[axis] += vel[axis];
    }
    sun.style.translate = `${pos.x.toFixed(2)}px ${pos.y.toFixed(2)}px`;
    const settled = Math.abs(vel.x) + Math.abs(vel.y) < 0.02 && Math.abs(target.x - pos.x) + Math.abs(target.y - pos.y) < 0.05;
    frame = settled ? 0 : requestAnimationFrame(step);
  };
  const run = () => { if (!frame) frame = requestAnimationFrame(step); };
  const reach = () => Math.min(220, panel.clientWidth * 0.4); // the phone band gives a shorter pull

  panel.addEventListener('pointermove', (e) => {
    const c = center();
    const dx = e.clientX - c.x;
    const dy = e.clientY - c.y;
    light(dx, dy);
    if (grab) {
      target.x = band(e.clientX - grab.x, reach());
      target.y = band(e.clientY - grab.y, reach());
    } else if (e.pointerType === 'mouse') {
      target.x = clamp(dx * 0.06, 22);
      target.y = clamp(dy * 0.06, 22);
    }
    run();
  }, opts);
  panel.addEventListener('pointerleave', () => {
    if (grab) return;
    target.x = 0; target.y = 0;
    sun.style.removeProperty('--hx'); sun.style.removeProperty('--hy');
    run();
  }, opts);
  sun.addEventListener('pointerdown', (e) => {
    grab = { x: e.clientX, y: e.clientY };
    sun.setPointerCapture(e.pointerId);
    sun.classList.add('is-held');
    if (e.pointerType === 'touch') navigator.vibrate?.(8); // a tiny tick on phones that support it
  }, opts);
  const release = () => {
    if (!grab) return;
    grab = null;
    target.x = 0; target.y = 0;
    sun.classList.remove('is-held');
    run();
  };
  sun.addEventListener('pointerup', release, opts);
  sun.addEventListener('pointercancel', release, opts);
  sun.classList.add('is-live');
  return () => {
    off.abort();
    if (frame) cancelAnimationFrame(frame);
  };
}
