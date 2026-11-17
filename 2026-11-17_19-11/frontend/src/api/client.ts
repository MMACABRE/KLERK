// The one API client (SPEC §9.1). Same-origin cookies, X-CSRFToken from the csrftoken cookie, one error shape.
// A 401 sends the user to the sign-in page with `next`. Components never call fetch directly.

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  data: Record<string, any>;
  constructor(status: number, message: string, code = '', fields: Record<string, string> = {}, data: Record<string, any> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.data = data;
  }
}

function csrfToken(): string {
  const m = /(?:^|;\s*)csrftoken=([^;]+)/.exec(document.cookie);
  return m ? decodeURIComponent(m[1]) : '';
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

type Body = Record<string, unknown> | FormData | undefined;

async function request<T = any>(method: string, path: string, body?: Body, query?: Record<string, unknown>): Promise<T> {
  let url = `/api/v1${path}`;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)));
      else qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const headers: Record<string, string> = { Accept: 'application/json' };
  let payload: BodyInit | undefined;
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken();
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, 'ارتباط با سرور برقرار نشد. اتصال شبکه را بررسی کنید.');
  }
  const type = res.headers.get('content-type') ?? '';
  const json = type.includes('application/json') ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    const e = json?.error ?? {};
    const message = e.message ?? (res.status === 403 ? 'شما اجازه‌ی دسترسی به این بخش را ندارید.' : 'خطایی در سرور رخ داد. لطفاً دوباره تلاش کنید.');
    const { code, message: _m, fields, ...rest } = e;
    if (res.status === 401 && path !== '/auth/login' && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, message, code ?? '', fields ?? {}, rest);
  }
  return json as T;
}

export const api = {
  get: <T = any>(path: string, query?: Record<string, unknown>) => request<T>('GET', path, undefined, query),
  post: <T = any>(path: string, body?: Body) => request<T>('POST', path, body ?? {}),
  put: <T = any>(path: string, body?: Body) => request<T>('PUT', path, body ?? {}),
  patch: <T = any>(path: string, body?: Body) => request<T>('PATCH', path, body ?? {}),
  del: <T = any>(path: string, body?: Body) => request<T>('DELETE', path, body),
};

// Downloads a file the server makes (CSV, XLSX, zip). A POST goes through a hidden form, so the browser saves the
// streamed answer itself (no blob in memory for a large zip). The form carries the CSRF token.
export function downloadPost(path: string, fields: Record<string, string> = {}) {
  const form = document.createElement('form');
  form.method = 'post';
  form.action = `/api/v1${path}`;
  form.hidden = true;
  const all = { csrfmiddlewaretoken: csrfToken(), ...fields };
  for (const [k, v] of Object.entries(all)) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = k;
    input.value = v;
    form.append(input);
  }
  document.body.append(form);
  form.submit();
  form.remove();
}

export function downloadGet(path: string, query: Record<string, string> = {}) {
  const qs = new URLSearchParams(query).toString();
  window.location.href = `/api/v1${path}${qs ? `?${qs}` : ''}`;
}
