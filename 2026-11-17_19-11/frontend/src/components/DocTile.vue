<script setup lang="ts">
// One document in a gallery (legacy partial doc-tile). Files are served only by the authenticated API route.
// Editors get «ویرایش» and «انتقال به پوشه» (SPEC §14.5.3-14.5.4); the page owns the dialog. In selection mode a
// checkbox picks the card. A pointer press on the card (not on a control) may start a drag to a folder chip; the
// page decides whether dragging is on (pointer devices from 900 px).
import { computed } from 'vue';
import Icon from './Icon.vue';
import ConfirmDelete from './ConfirmDelete.vue';
import { api, ApiError } from '../api/client';
import { can, has } from '../lib/session';
import { CATEGORY, fileSize } from '../lib/fmt';

const props = defineProps<{ d: any; code: string; selectable?: boolean; selected?: boolean; folderName?: string }>();
const emit = defineEmits<{ changed: []; error: [string]; edit: [any]; move: [any]; select: [boolean]; grab: [PointerEvent] }>();
const type = computed(() => (props.d.ext === 'jpeg' ? 'jpg' : props.d.ext));
const isImage = computed(() => type.value === 'jpg' || type.value === 'png');
const canOpen = computed(() => isImage.value || type.value === 'pdf');
const url = computed(() => `/api/v1/patients/${props.code}/files/${encodeURIComponent(props.d.filename)}`);
const title = computed(() => props.d.title || props.d.filename);
const day = computed(() => props.d.docDate?.short ?? props.d.modified?.text?.split(' ')[0] ?? '');
const size = computed(() => fileSize(props.d.size));
const label = computed(() => ({ pdf: 'PDF', dcm: 'DICOM', jpg: 'JPG', png: 'PNG' } as Record<string, string>)[type.value] || String(props.d.ext).toUpperCase());

async function act(fn: () => Promise<unknown>) {
  try { await fn(); emit('changed'); } catch (e) { emit('error', e instanceof ApiError ? e.message : 'خطایی رخ داد.'); }
}
const remove = () => act(() => api.del(`/patients/${props.code}/files/${encodeURIComponent(props.d.filename)}`));
function press(ev: PointerEvent) {
  if (ev.button !== 0 || (ev.target as HTMLElement).closest('a, button, input, select, summary, form, details')) return;
  emit('grab', ev);
}
</script>

<template>
  <article class="doc-tile" :class="{ 'is-selected': selected }" :data-doc="d.filename" @pointerdown="press">
    <label v-if="selectable" class="check doc-pick"><input type="checkbox" :checked="selected" @change="emit('select', ($event.target as HTMLInputElement).checked)"><span class="sr-only">انتخاب {{ title }}</span></label>
    <a class="doc-media" :class="{ 'doc-media-file': !isImage }" :href="canOpen ? `${url}?inline=1` : url" :target="canOpen ? '_blank' : undefined" :rel="canOpen ? 'noopener' : undefined" draggable="false">
      <img v-if="isImage" :src="`${url}?inline=1`" :alt="title" loading="lazy" decoding="async" draggable="false">
      <span v-else class="doc-type"><Icon name="file" /><b>{{ label }}</b></span>
      <span class="sr-only">{{ canOpen ? 'باز کردن' : 'دانلود' }} {{ title }}</span>
    </a>
    <div class="doc-body">
      <div class="doc-head">
        <h3 class="doc-name">{{ title }}</h3>
        <span class="chip chip-plain" :class="d.category ? 'chip-mute' : 'chip-warn'">{{ d.category ? CATEGORY[d.category] : 'طبقه‌بندی نشده' }}</span>
      </div>
      <p class="doc-sub">{{ day }} · {{ size }}<template v-if="d.title"> · <span class="doc-file">{{ d.filename }}</span></template><template v-if="folderName"> · <Icon name="folder" />{{ folderName }}</template></p>
      <div class="doc-actions">
        <a v-if="canOpen" class="btn btn-sm" :href="`${url}?inline=1`" target="_blank" rel="noopener"><Icon name="eye" />مشاهده</a>
        <a class="btn btn-sm btn-ghost" :href="url"><Icon name="download" />دانلود</a>
        <template v-if="can('documents', 2)">
          <button type="button" class="btn btn-sm btn-ghost" @click="emit('edit', d)"><Icon name="edit" />ویرایش</button>
          <button type="button" class="btn btn-sm btn-ghost" @click="emit('move', d)"><Icon name="folder" />انتقال به پوشه</button>
        </template>
        <ConfirmDelete v-if="has('document_delete')" question="این فایل از پرونده حذف شود؟" @confirm="remove" />
      </div>
    </div>
  </article>
</template>
