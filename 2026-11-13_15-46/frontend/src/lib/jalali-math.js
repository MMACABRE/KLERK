// Jalali calendar arithmetic for the browser date picker.
// Ported from jalaali-js (MIT, Copyright (c) 2020 Behrang Norouzinia), the same library the server uses;
// test/jalali-math.test.js checks this copy against it.

const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
const div = (a, b) => ~~(a / b);
const mod = (a, b) => a - ~~(a / b) * b;

function jalCal(jy) {
  const gy = jy + 621;
  let leapJ = -14;
  let jp = BREAKS[0];
  let jm = 0;
  let jump = 0;
  for (let i = 1; i < BREAKS.length; i += 1) {
    jm = BREAKS[i];
    jump = jm - jp;
    if (jy < jm) break;
    leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }
  let n = jy - jp;
  leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;
  return { leap, gy, march };
}

function g2d(gy, gm, gd) {
  const d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
  return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
}

function d2g(jdn) {
  let j = 4 * jdn + 139361631;
  j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
  const i = div(mod(j, 1461), 4) * 5 + 308;
  const gd = div(mod(i, 153), 5) + 1;
  const gm = mod(div(i, 153), 12) + 1;
  return { gy: div(j, 1461) - 100100 + div(8 - gm, 6), gm, gd };
}

export function j2d(jy, jm, jd) {
  const r = jalCal(jy);
  return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
}

export function d2j(jdn) {
  let jy = d2g(jdn).gy - 621;
  const r = jalCal(jy);
  let k = jdn - g2d(r.gy, 3, r.march);
  if (k >= 0) {
    if (k <= 185) return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
    k -= 186;
  } else {
    jy -= 1;
    k += 179;
    if (r.leap === 1) k += 1;
  }
  return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
}

export function monthLength(jy, jm) {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return jalCal(jy).leap === 0 ? 30 : 29;
}

// Column of a day in a Saturday-first week: 0 = Saturday ... 6 = Friday.
export function weekColumn(jy, jm, jd) {
  return mod(j2d(jy, jm, jd) + 2, 7);
}

export function today(now = new Date()) {
  return d2j(g2d(now.getFullYear(), now.getMonth() + 1, now.getDate()));
}

// '1403/05/12' or '۱۴۰۳/۵/۱۲' -> { jy, jm, jd }, or null when it is not a real date.
export function parse(text) {
  const s = String(text ?? '').replace(/[۰-۹]/g, (d) => d.charCodeAt(0) - 0x6f0).replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 0x660).trim();
  const m = /^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})$/.exec(s);
  if (!m) return null;
  const [jy, jm, jd] = m.slice(1).map(Number);
  if (jy < 1200 || jy > 1600 || jm < 1 || jm > 12 || jd < 1 || jd > monthLength(jy, jm)) return null;
  return { jy, jm, jd };
}

export function format({ jy, jm, jd }) {
  return `${jy}/${String(jm).padStart(2, '0')}/${String(jd).padStart(2, '0')}`;
}

// The same five operations for the Gregorian calendar, with the day as { jy, jm, jd } so the picker treats both alike
// (the names stay jy/jm/jd; here they hold the Gregorian year, month and day).
const gLeap = (gy) => (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
export const gregorian = {
  monthLength: (gy, gm) => (gm === 2 ? (gLeap(gy) ? 29 : 28) : [4, 6, 9, 11].includes(gm) ? 30 : 31),
  weekColumn: (gy, gm, gd) => mod(g2d(gy, gm, gd) + 2, 7),
  today: (now = new Date()) => ({ jy: now.getFullYear(), jm: now.getMonth() + 1, jd: now.getDate() }),
  // '2026/11/15' or '۲۰۲۶-۱۱-۱۵' -> { jy, jm, jd } (Gregorian), or null; the year range matches Jalali 1200..1600.
  parse(text) {
    const s = String(text ?? '').replace(/[۰-۹]/g, (d) => d.charCodeAt(0) - 0x6f0).replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 0x660).trim();
    const m = /^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})$/.exec(s);
    if (!m) return null;
    const [gy, gm, gd] = m.slice(1).map(Number);
    if (gy < 1821 || gy > 2221 || gm < 1 || gm > 12 || gd < 1 || gd > gregorian.monthLength(gy, gm)) return null;
    return { jy: gy, jm: gm, jd: gd };
  },
  format,
};
export const jalali = { monthLength, weekColumn, today, parse, format };

// Convert a day between the calendars ('jalali' or 'gregorian' names the calendar of the input).
export function convert(day, from) {
  if (from === 'jalali') {
    const g = d2g(j2d(day.jy, day.jm, day.jd));
    return { jy: g.gy, jm: g.gm, jd: g.gd };
  }
  return d2j(g2d(day.jy, day.jm, day.jd));
}
