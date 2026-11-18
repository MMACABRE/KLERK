// Where the app may send the browser after an action that carries a return path in the URL (?next= after sign-in,
// ?back= after a visit form). Only a path on this site: one leading "/", not "//" or "/\" (both reach another
// host), not a full URL, and no control character anywhere (a browser drops tab and newline from a URL, so
// "/\t/evil" would become "//evil"). Port of legacy src/auth.js safeNext; checked by tools/safe-next.test.mjs.

export function isLocalPath(n: unknown): n is string {
  return typeof n === 'string' && /^\/(?![/\\])[^\u0000-\u001f\u007f]*$/.test(n);
}

export function safeNext(n: unknown): string {
  return isLocalPath(n) ? n : '/';
}
