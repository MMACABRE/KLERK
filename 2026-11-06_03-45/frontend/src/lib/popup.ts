// Shared helpers for the visit form dropdowns (legacy app.js placePop, revealPop, openDropdown): the day bar on the
// time box, the length dial and the Jalali calendar. Only one of them is open at a time.

let openClose: (() => void) | null = null;

// Closes whichever dropdown is open and records `close` as the open one.
export function claimDropdown(close: () => void): void {
  if (openClose && openClose !== close) openClose();
  openClose = close;
}
export function releaseDropdown(close: () => void): void {
  if (openClose === close) openClose = null;
}

// On phones the bottom tab bar covers the foot of the viewport, so the room below ends above it.
function tabbarHeight(): number {
  const tab = document.querySelector<HTMLElement>('.tabbar');
  return tab && getComputedStyle(tab).display !== 'none' ? tab.offsetHeight : 0;
}

// Below the anchor, or above it when there is no room below; then shifted sideways into the viewport (16 px margin).
export function placePop(anchor: HTMLElement, pop: HTMLElement): void {
  pop.classList.remove('is-above');
  const limit = innerHeight - tabbarHeight();
  const box = anchor.getBoundingClientRect();
  if (box.bottom + pop.offsetHeight + 12 > limit && box.top > pop.offsetHeight + 12) pop.classList.add('is-above');
  pop.style.translate = '';
  // The entry transition scales the pop a little (centred), so measure its unscaled box.
  const rect = pop.getBoundingClientRect();
  const left = rect.left - (pop.offsetWidth - rect.width) / 2;
  const right = left + pop.offsetWidth;
  let dx = 0;
  if (left < 16) dx = 16 - left;
  else if (right > innerWidth - 16) dx = innerWidth - 16 - right;
  pop.style.translate = `${dx}px 0`;
}

// Scrolls the page just enough to show the whole popup above the tab bar.
export function revealPop(pop: HTMLElement): void {
  // scrollIntoView would line the pop up with the viewport bottom, under the fixed tab bar, so scroll by the overlap.
  const rect = pop.getBoundingClientRect();
  const over = rect.bottom - (innerHeight - tabbarHeight() - 8);
  const dy = rect.top - over < 8 ? rect.top - 8 : over > 0 ? over : rect.top < 8 ? rect.top - 8 : 0;
  if (dy) window.scrollBy({ top: dy, behavior: reducedMotion() ? 'auto' : 'smooth' });
}

export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

export function minutesNow(): number {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

// "9:30", "09.30" in Persian, Arabic or Latin digits, to minutes since midnight. Null when not a valid time.
export function parseMinutes(text: unknown): number | null {
  const latin = String(text ?? '')
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .trim();
  const m = /^(\d{1,2})[:.](\d{2})$/.exec(latin);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h > 23 || min > 59 ? null : h * 60 + min;
}

// The minute under clientX on a 24-hour ruler, snapped to 5 minutes and clamped to 00:00-23:55. Null while the
// ruler has no width (hidden).
export function minuteAt(track: HTMLElement, clientX: number): number | null {
  const rect = track.getBoundingClientRect();
  if (!rect.width) return null;
  const m = Math.round((((clientX - rect.left) / rect.width) * 1440) / 5) * 5;
  return Math.min(1435, Math.max(0, m));
}
