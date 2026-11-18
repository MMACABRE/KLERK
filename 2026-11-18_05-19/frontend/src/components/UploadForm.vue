<script setup lang="ts">
// Upload documents with their metadata (legacy profile and documents page forms; SPEC §14.5.1-14.5.2). Up to 20
// files, picked in one or several goes; each shows a preview card before upload. Category, date, notes and folder
// are shared; the title is per file. The files go up one at a time, in order, each as its own request to the
// existing upload route, so a slow line or the 1-CPU server is never flooded. A failed file stays with its message
// and a retry button; it never stops the others.
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import Icon from './Icon.vue';
import DropZone from './DropZone.vue';
import FilePreview from './FilePreview.vue';
import JalaliInput from './JalaliInput.vue';
import { api, ApiError } from '../api/client';
import { CATEGORY, fa, fileSize } from '../lib/fmt';
import { vFloat } from '../lib/directives';

type State = 'waiting' | 'uploading' | 'done' | 'failed' | 'refused';
type Item = { key: number; file: File; kind: string; title: string; state: State; message: string };

const props = defineProps<{
  code: string; compact?: boolean; idPrefix: string; withNotes?: boolean;
  folders?: { id: number; name: string }[]; folder?: number | null;
}>();
const emit = defineEmits<{ done: [] }>();
const MAX_FILES = 20;
const MAX_BYTES = 30 * 1024 * 1024;
const KINDS: Record<string, string> = { jpg: 'image', jpeg: 'image', png: 'image', pdf: 'pdf', dcm: 'dcm' };

const picked = ref<File[]>([]);
const items = ref<Item[]>([]);
const shrinking = ref(false);
const sending = ref(false);
const notice = ref('');
const meta = ref({ category: 'other', docDate: '', notes: '', folder: props.folder ?? null as number | null });
watch(() => props.folder, (f) => { meta.value.folder = f ?? null; });
const zone = ref<InstanceType<typeof DropZone> | null>(null);
let next = 0;

// Every pick adds to the list, up to 20 in all; the rest are left out with a notice.
watch(picked, (files) => {
  if (!files.length) return;
  const room = MAX_FILES - items.value.length;
  notice.value = files.length > room ? 'حداکثر ۲۰ فایل در هر بار انتخاب می‌شود.' : '';
  for (const file of files.slice(0, Math.max(0, room))) {
    const kind = KINDS[file.name.split('.').pop()?.toLowerCase() ?? ''] ?? '';
    const refused = !kind ? 'این نوع فایل پذیرفته نیست' : file.size > MAX_BYTES ? 'حجم فایل بیش از ۳۰ مگابایت است.' : '';
    items.value.push({ key: next++, file, kind, title: '', state: refused ? 'refused' : 'waiting', message: refused });
  }
  zone.value?.reset();
});

const sendable = computed(() => items.value.filter((i) => i.state === 'waiting' || i.state === 'failed'));
const buttonText = computed(() => (sendable.value.length > 1 ? `بارگذاری ${fa(sendable.value.length)} فایل` : 'بارگذاری'));
const STATE_TEXT: Record<State, string> = { waiting: 'در انتظار', uploading: 'در حال بارگذاری', done: 'بارگذاری شد', failed: 'خطا', refused: 'خطا' };
const remove = (key: number) => { items.value = items.value.filter((i) => i.key !== key); };
// One polite summary for screen readers instead of twenty status lines.
const summary = computed(() => {
  const n = (s: State) => items.value.filter((i) => i.state === s).length;
  if (sending.value) return `در حال بارگذاری · ${fa(n('done'))} از ${fa(items.value.length)}`;
  return n('failed') ? `${fa(n('failed'))} فایل: خطا` : '';
});

// Closing or reloading the tab mid-upload asks first (the browser's own warning). Leaving the page inside the app
// stops the files not yet sent; the ones already sent stay saved.
const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
let stopped = false;
onBeforeUnmount(() => { stopped = true; window.removeEventListener('beforeunload', warn); });

async function sendOne(it: Item, m: typeof meta.value): Promise<boolean> {
  it.state = 'uploading';
  it.message = '';
  const form = new FormData();
  form.append('file', it.file);
  form.append('title', it.title);
  form.append('category', m.category);
  form.append('docDate', m.docDate);
  form.append('notes', props.withNotes ? m.notes : '');
  if (m.folder) form.append('folder', String(m.folder));
  try {
    await api.post(`/patients/${props.code}/documents`, form);
    it.state = 'done';
    return true;
  } catch (e) {
    it.state = 'failed';
    it.message = e instanceof ApiError ? e.message : 'خطایی رخ داد.';
    return false;
  }
}

async function send(only?: Item) {
  if (shrinking.value || sending.value) return;
  sending.value = true;
  window.addEventListener('beforeunload', warn);
  let sent = 0;
  const m = { ...meta.value };  // the shared fields as they were when the run started
  try {
    for (const it of only ? [only] : [...sendable.value]) {
      if (stopped) return;
      if (!items.value.includes(it)) continue;  // removed from the list while waiting
      if (await sendOne(it, m)) sent++;
    }
  } finally {
    sending.value = false;
    window.removeEventListener('beforeunload', warn);
  }
  if (stopped) return;
  // When nothing is left to send, the sent files leave the list and the gallery reloads once; failed ones stay.
  if (!items.value.some((i) => i.state === 'waiting' || i.state === 'uploading')) {
    items.value = items.value.filter((i) => i.state !== 'done');
    if (!items.value.length) meta.value = { category: 'other', docDate: '', notes: '', folder: props.folder ?? null };
    if (sent) emit('done');
  }
}
</script>

<template>
  <form class="card-body upload-form" :class="{ 'upload-form-compact': compact }" @submit.prevent="send()">
    <p v-if="notice" class="info-box upload-note" role="status">{{ notice }}</p>
    <DropZone :id="`${idPrefix}-file`" ref="zone" v-model="picked" multiple quiet :disabled="sending" @busy="shrinking = $event" />
    <div class="upload-fields">
      <div v-float class="field">
        <label :for="`${idPrefix}-category`">طبقه‌بندی</label>
        <select :id="`${idPrefix}-category`" v-model="meta.category" class="select" :disabled="sending">
          <option v-for="(l, k) in CATEGORY" :key="k" :value="k">{{ l }}</option>
        </select>
      </div>
      <div class="field">
        <label :for="`${idPrefix}-date`">تاریخ سند</label>
        <JalaliInput :id="`${idPrefix}-date`" v-model="meta.docDate" placeholder="۱۴۰۳/۰۵/۱۲" :disabled="sending" />
      </div>
      <div v-if="folders" v-float class="field">
        <label :for="`${idPrefix}-folder`">پوشه</label>
        <select :id="`${idPrefix}-folder`" v-model="meta.folder" class="select" :disabled="sending">
          <option :value="null">بدون پوشه</option>
          <option v-for="f in folders" :key="f.id" :value="f.id">{{ f.name }}</option>
        </select>
      </div>
      <div v-if="withNotes" v-float class="field span-2">
        <label :for="`${idPrefix}-notes`">یادداشت</label>
        <textarea :id="`${idPrefix}-notes`" v-model="meta.notes" class="textarea" maxlength="2000"></textarea>
      </div>
      <div class="form-actions span-2">
        <button class="btn btn-primary" type="submit" :disabled="shrinking || sending || !sendable.length"><Icon name="upload" />{{ buttonText }}</button>
      </div>
    </div>
    <p class="sr-only" aria-live="polite">{{ summary }}</p>
    <ul v-if="items.length" class="up-list" :aria-label="`${fa(items.length)} فایل`">
      <li v-for="it in items" :key="it.key" class="up-card" :class="`up-${it.state}`">
        <div class="up-media"><FilePreview v-if="it.kind" :file="it.file" :kind="it.kind" /><span v-else class="doc-type up-badge"><Icon name="file" /><b>?</b></span></div>
        <div class="up-body">
          <div class="up-head">
            <b class="up-name" dir="auto">{{ it.file.name }}</b>
            <button type="button" class="btn btn-sm btn-ghost up-x" :disabled="it.state === 'uploading'" :aria-label="`حذف از فهرست: ${it.file.name}`" title="حذف از فهرست" @click="remove(it.key)"><Icon name="x" /></button>
          </div>
          <span class="up-size">{{ fileSize(it.file.size) }}</span>
          <div v-if="it.state !== 'refused'" v-float class="field">
            <label :for="`${idPrefix}-t-${it.key}`">عنوان</label>
            <input :id="`${idPrefix}-t-${it.key}`" v-model="it.title" class="input" type="text" maxlength="200" :disabled="it.state === 'uploading' || it.state === 'done'">
          </div>
          <p class="up-state"><span class="chip" :class="{ 'chip-ok': it.state === 'done', 'chip-crit': it.state === 'failed' || it.state === 'refused', 'chip-warn': it.state === 'uploading' }">{{ STATE_TEXT[it.state] }}</span><span v-if="it.message" class="field-error">{{ it.message }}</span></p>
          <button v-if="it.state === 'failed'" type="button" class="btn btn-sm up-retry" :disabled="sending" :aria-label="`تلاش دوباره: ${it.file.name}`" @click="send(it)">تلاش دوباره</button>
        </div>
      </li>
    </ul>
  </form>
</template>
