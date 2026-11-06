// Display helpers shared by the pages.

const FA = '۰۱۲۳۴۵۶۷۸۹';

// ASCII digits to Persian; a dot between digits becomes the Persian decimal sign.
export function fa(value: unknown): string {
  return String(value ?? '')
    .replace(/(\d)\.(?=\d)/g, '$1٫')
    .replace(/\d/g, (d) => FA[Number(d)]);
}

// 12345 -> '۱۲٬۳۴۵'
export function faCount(n: number): string {
  return fa(Number(n).toLocaleString('en-US').replace(/,/g, '٬'));
}

export const STATUS: Record<string, { label: string; chip: string }> = {
  active: { label: 'فعال', chip: 'chip-ok' },
  pending: { label: 'در انتظار', chip: 'chip-warn' },
  critical: { label: 'بحرانی', chip: 'chip-crit' },
  archived: { label: 'بایگانی‌شده', chip: 'chip-mute' },
};
export const SEX: Record<string, string> = { female: 'زن', male: 'مرد' };
export const CATEGORY: Record<string, string> = {
  consent: 'رضایت‌نامه', lab: 'آزمایش', imaging: 'تصویربرداری', surgery: 'جراحی', other: 'سایر',
};
export const VISIT_STATE: Record<string, { label: string; chip: string }> = {
  scheduled: { label: 'برنامه‌ریزی‌شده', chip: 'chip-info' },
  done: { label: 'انجام‌شده', chip: 'chip-ok' },
  cancelled: { label: 'لغو‌شده', chip: 'chip-mute' },
};

export function visitState(v: { status: string; ongoing?: boolean; overdue?: boolean }) {
  if (v.ongoing) return { label: 'در جریان', chip: 'chip-ok' };
  if (v.overdue) return { label: 'زمان گذشته', chip: 'chip-warn' };
  return VISIT_STATE[v.status];
}

// Rial -> the number an amount box shows (legacy moneyInput): whole Toman, else Rial with an R suffix.
export function moneyInput(rial: number | null | undefined, cur: string): string {
  if (rial === null || rial === undefined || rial === 0) return '';
  if (cur === 'R') return String(rial);
  return rial % 10 !== 0 ? `${rial}R` : String(rial / 10);
}

export function initialsOf(first: string, last: string): string {
  return (Array.from(first ?? '')[0] ?? '') + (Array.from(last ?? '')[0] ?? '');
}

export function bytes(n: number): string {
  if (n < 1024) return `${fa(n)} بایت`;
  if (n < 1048576) return `${fa((n / 1024).toFixed(0))} کیلوبایت`;
  return `${fa((n / 1048576).toFixed(1))} مگابایت`;
}
