// Browser errors to the diagnostics feed (ADR-0013). Only names travel: the error's class name, the route pattern
// (never the URL with its codes), and each stack frame's file and function without query strings. At most 10 a
// minute; the rest are dropped. A failing report is ignored.
import type { Router } from 'vue-router';
import { api } from '../api/client';
import { session } from './session';

const LIMIT = 10;
let sent: number[] = [];

function frames(stack: string | undefined): { file: string; function: string }[] {
  const out: { file: string; function: string }[] = [];
  for (const line of (stack ?? '').split('\n').slice(0, 20)) {
    const m = line.match(/at (?:(\S+) \()?(?:\S*?\/\/[^/]+)?(\/[^\s:?#)]*)/) || line.match(/^(\S*)@(?:\S*?\/\/[^/]+)?(\/[^\s:?#]*)/);
    if (m) out.push({ function: (m[1] ?? '').slice(0, 80), file: m[2].slice(0, 120) });
  }
  return out;
}

export function installErrorReporter(app: { config: { errorHandler?: unknown } }, router: Router) {
  const send = (err: unknown) => {
    if (!session.me) return;
    const now = Date.now();
    sent = sent.filter((t) => now - t < 60_000);
    if (sent.length >= LIMIT) return;
    sent.push(now);
    const e = err instanceof Error ? err : new Error('NonError');
    const route = router.currentRoute.value.matched.at(-1)?.path ?? '';
    api.post('/diagnostics/client-errors', { name: e.name, route, version: '1', stack: frames(e.stack) }).catch(() => {});
  };
  app.config.errorHandler = (err: unknown) => { console.error(err); send(err); };
  window.addEventListener('error', (ev) => send(ev.error));
  window.addEventListener('unhandledrejection', (ev) => send(ev.reason));
}
