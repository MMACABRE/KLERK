<script setup lang="ts">
// Drag-and-drop file box (legacy partial dropzone + enhanceDropzone). The real file input covers the box. Large
// photos are shrunk to 3 MB before they are handed to the page (`files` model).
import { ref } from 'vue';
import Icon from './Icon.vue';
import { fa } from '../lib/fmt';
import { MULTI_LIMIT, SHRINK_LIMIT, isShrinkable, mbText, prepareFiles } from '../lib/shrink';

const props = withDefaults(defineProps<{ id: string; accept?: string; multiple?: boolean; hint?: string; required?: boolean }>(), {
  accept: '.pdf,.jpg,.jpeg,.png,.dcm,application/pdf,image/jpeg,image/png',
  hint: 'PDF، JPG، PNG یا DICOM · عکس‌های بزرگ خودکار کوچک می‌شوند',
});
const files = defineModel<File[]>({ default: () => [] });
const emit = defineEmits<{ busy: [boolean] }>();
const over = ref(false);
const busy = ref(false);
const label = ref('');
const input = ref<HTMLInputElement | null>(null);
let depth = 0;

async function onChange() {
  const chosen = [...(input.value?.files ?? [])];
  if (!chosen.length) { files.value = []; label.value = ''; return; }
  const big = chosen.some((f) => f.size > SHRINK_LIMIT && isShrinkable(f));
  if (big) {
    busy.value = true;
    emit('busy', true);
    label.value = chosen.length === 1 ? `در حال کوچک‌سازی ${chosen[0].name}…` : 'در حال کوچک‌سازی عکس‌ها…';
  }
  const out = await prepareFiles(chosen);
  busy.value = false;
  emit('busy', false);
  files.value = out;
  if (out.length === 1) {
    const [file, done] = [chosen[0], out[0]];
    label.value = done !== file ? `${done.name} · از ${mbText(file.size)} به ${mbText(done.size)} کوچک شد` : `${done.name} · ${mbText(done.size)}`;
    return;
  }
  const total = out.reduce((n, f) => n + f.size, 0);
  label.value = `${fa(out.length)} فایل · ${mbText(total)}`
    + (total > MULTI_LIMIT ? ' · بیش از ۳۰ مگابایت است؛ چند فایل را بعداً از صفحه‌ی بیمار بارگذاری کنید' : '');
}

function reset() {
  if (input.value) input.value.value = '';
  files.value = [];
  label.value = '';
}
defineExpose({ reset });
</script>

<template>
  <label class="dropzone" :class="{ 'is-over': over, 'is-busy': busy, 'has-file': files.length > 0 }" :for="id"
    @dragenter="depth++; over = true" @dragleave="if (--depth <= 0) { depth = 0; over = false; }" @drop="depth = 0; over = false">
    <input :id="id" ref="input" class="dropzone-input" type="file" :accept="props.accept" :multiple="multiple"
      :required="required && !multiple" @change="onChange">
    <span class="dropzone-plus" aria-hidden="true"><Icon name="plus" /></span>
    <span class="dropzone-title">{{ multiple ? 'فایل‌ها را اینجا رها کنید یا برای انتخاب بزنید' : 'فایل را اینجا رها کنید یا برای انتخاب بزنید' }}</span>
    <span class="dropzone-hint">{{ hint }}</span>
    <span class="dropzone-file" aria-live="polite">{{ label }}</span>
  </label>
</template>
