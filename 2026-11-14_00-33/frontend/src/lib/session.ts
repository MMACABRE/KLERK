// The signed-in user (SPEC §9.1 session store). Permissions here only hide what the user may not open; the server
// decides every request.
import { reactive } from 'vue';
import { api, ApiError } from '../api/client';

export interface Me {
  id: number;
  username: string;
  displayName: string;
  owner: boolean;
  roleLabel: string;
  perms: { areas: Record<string, number>; flags: string[] };
  siteName: string;
  currency: 'T' | 'R';
  smsOn: boolean;
  smsDefaultLead: string;
  patientCount: number;
  theme: string;
  systemProblems?: string[];
  diagOn?: boolean;
}

export const session = reactive<{ me: Me | null; loaded: boolean; siteName: string; theme: string }>({
  me: null,
  loaded: false,
  siteName: 'KLERK | کلرک',
  theme: '',
});

export function can(area: string, level = 1): boolean {
  return Boolean(session.me && (session.me.perms.areas[area] ?? 0) >= level);
}

export function has(flag: string): boolean {
  return Boolean(session.me && session.me.perms.flags.includes(flag));
}

export async function loadSession(): Promise<Me | null> {
  try {
    const boot = await api.get<{ siteName: string; signedIn: boolean; theme: string }>('/auth/csrf');
    session.siteName = boot.siteName;
    session.theme = boot.theme;
    session.me = boot.signedIn ? await api.get<Me>('/me') : null;
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    session.me = null;
  }
  if (session.me) session.siteName = session.me.siteName;
  session.loaded = true;
  return session.me;
}

export async function refreshMe() {
  try {
    session.me = await api.get<Me>('/me');
    session.siteName = session.me.siteName;
  } catch {
    /* the 401 handler takes care of a lost session */
  }
}

export function setTitle(title: string) {
  document.title = title ? `${title} · ${session.siteName}` : session.siteName;
}
