// Loading a page's data with loading, error and reload (every list has loading/empty/error states, SPEC §9.3).
import { ref, type Ref } from 'vue';
import { ApiError } from '../api/client';

export function useLoad<T>(fn: () => Promise<T>) {
  const data = ref<T | null>(null) as Ref<T | null>;
  const error = ref('');
  const loading = ref(true);
  async function load() {
    loading.value = true;
    error.value = '';
    try {
      data.value = await fn();
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.';
    } finally {
      loading.value = false;
    }
  }
  load();
  return { data, error, loading, load };
}

// Runs a change; errors land in `error` and `fields` (Persian, from the server).
export function useAction() {
  const busy = ref(false);
  const error = ref('');
  const fields = ref<Record<string, string>>({});
  const notice = ref('');
  async function run<T>(fn: () => Promise<T>, okText = ''): Promise<T | undefined> {
    busy.value = true;
    error.value = '';
    fields.value = {};
    notice.value = '';
    try {
      const out = await fn();
      if (okText) notice.value = okText;
      return out;
    } catch (e) {
      if (e instanceof ApiError) {
        error.value = e.message;
        fields.value = e.fields;
        return undefined;
      }
      error.value = 'خطایی رخ داد.';
      return undefined;
    } finally {
      busy.value = false;
    }
  }
  return { busy, error, fields, notice, run };
}

export function qs(v: unknown): string {
  return Array.isArray(v) ? String(v[v.length - 1] ?? '') : String(v ?? '');
}
