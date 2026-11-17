// Light/dark choice (SPEC §9.2): empty follows the system; the button sets data-theme on <html> and the cookie.
import { ref } from 'vue';
import { api } from '../api/client';

export const theme = ref<string>('');

export function applyTheme(value: string) {
  theme.value = value === 'light' || value === 'dark' ? value : '';
  if (theme.value) document.documentElement.dataset.theme = theme.value;
  else delete document.documentElement.dataset.theme;
}

export async function setTheme(value: 'light' | 'dark') {
  applyTheme(value);
  try {
    await api.put('/me/theme', { theme: value });
  } catch {
    /* the page keeps the choice even when the cookie could not be written */
  }
}
