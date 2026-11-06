<script setup lang="ts">
// One document in a gallery (legacy partial doc-tile). Files are served only by the authenticated API route.
import { computed, ref } from 'vue';
import Icon from './Icon.vue';
import ConfirmDelete from './ConfirmDelete.vue';
import { api, ApiError } from '../api/client';
import { can, has } from '../lib/session';
import { CATEGORY, fa } from '../lib/fmt';

const props = defineProps<{ d: any; code: string; classify?: boolean }>();
const emit = defineEmits<{ changed: []; error: [string] }>();
const type = computed(() => (props.d.ext === 'jpeg' ? 'jpg' : props.d.ext));
const isImage = computed(() => type.value === 'jpg' || type.value === 'png');
const canOpen = computed(() => isImage.value || type.value === 'pdf');
const url = computed(() => `/api/v1/patients/${props.code}/files/${encodeURIComponent(props.d.filename)}`);
const title = computed(() => props.d.title || props.d.filename);
const day = computed(() => props.d.docDate?.short ?? props.d.modified?.text?.split(' ')[0] ?? '');
const size = computed(() => (props.d.size < 1048576
  ? `${fa(Math.max(1, Math.round(props.d.size / 1024)))} کیلوبایت`
  : `${fa((props.d.size / 1048576).toFixed(1)).replace('.', '٫')} مگابایت`));
const label = computed(() => ({ pdf: 'PDF', dcm: 'DICOM', jpg: 'JPG', png: 'PNG' } as Record<string, string>)[type.value] || String(props.d.ext).toUpperCase());
const category = ref('other');

async function act(fn: () => Promise<unknown>) {
  try { await fn(); emit('changed'); } catch (e) { emit('error', e instanceof ApiError ? e.message : 'خطایی رخ داد.'); }
}
const remove = () => act(() => api.del(`/patients/${props.code}/files/${encodeURIComponent(props.d.filename)}`));
const save = () => act(() => api.post(`/patients/${props.code}/documents/classify`, { filename: props.d.filename, category: category.value }));
</script>

<template>
  <article class="doc-tile">
    <a class="doc-media" :class="{ 'doc-media-file': !isImage }" :href="canOpen ? `${url}?inline=1` : url" :target="canOpen ? '_blank' : undefined" :rel="canOpen ? 'noopener' : undefined">
      <img v-if="isImage" :src="`${url}?inline=1`" :alt="title" loading="lazy" decoding="async">
      <span v-else class="doc-type"><Icon name="file" /><b>{{ label }}</b></span>
      <span class="sr-only">{{ canOpen ? 'باز کردن' : 'دانلود' }} {{ title }}</span>
    </a>
    <div class="doc-body">
      <div class="doc-head">
        <h3 class="doc-name">{{ title }}</h3>
        <span class="chip chip-plain" :class="d.category ? 'chip-mute' : 'chip-warn'">{{ d.category ? CATEGORY[d.category] : 'طبقه‌بندی نشده' }}</span>
      </div>
      <p class="doc-sub">{{ day }} · {{ size }}<template v-if="d.title"> · <span class="doc-file">{{ d.filename }}</span></template></p>
      <div class="doc-actions">
        <a v-if="canOpen" class="btn btn-sm" :href="`${url}?inline=1`" target="_blank" rel="noopener"><Icon name="eye" />مشاهده</a>
        <a class="btn btn-sm btn-ghost" :href="url"><Icon name="download" />دانلود</a>
        <ConfirmDelete v-if="has('document_delete')" question="این فایل از پرونده حذف شود؟" @confirm="remove" />
      </div>
      <form v-if="classify && !d.category && can('documents', 2)" class="doc-classify" @submit.prevent="save">
        <label class="sr-only" :for="`cl-${d.filename}`">طبقه‌بندی</label>
        <select :id="`cl-${d.filename}`" v-model="category" class="select">
          <option v-for="(l, k) in CATEGORY" :key="k" :value="k">{{ l }}</option>
        </select>
        <button class="btn btn-sm" type="submit">ثبت طبقه‌بندی</button>
      </form>
    </div>
  </article>
</template>
