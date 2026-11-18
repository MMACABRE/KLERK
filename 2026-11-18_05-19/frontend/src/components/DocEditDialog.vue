<script setup lang="ts">
// «ویرایش» of one document (SPEC §14.5.3): title, category, document date, notes and folder in a native <dialog>
// (focus stays inside, Escape closes). It sends every field to classify, which replaces them; the file name on disk
// never changes. `moveOnly` shows the folder select alone («انتقال به پوشه») and uses documents/move, so a move never
// touches the other fields.
import { ref } from 'vue';
import JalaliInput from './JalaliInput.vue';
import { api, ApiError } from '../api/client';
import { CATEGORY } from '../lib/fmt';
import { vFloat } from '../lib/directives';

const props = defineProps<{ code: string; folders: { id: number; name: string }[] }>();
const emit = defineEmits<{ saved: [any] }>();
const box = ref<HTMLDialogElement | null>(null);
const files = ref<string[]>([]);
const moveOnly = ref(false);
const form = ref({ title: '', category: 'other', docDate: '', notes: '', folder: null as number | null });
const error = ref('');
const fields = ref<Record<string, string>>({});
const busy = ref(false);

function edit(d: any) {
  files.value = [d.filename];
  moveOnly.value = false;
  form.value = { title: d.title ?? '', category: d.category ?? 'other', docDate: d.docDate?.input ?? '', notes: d.notes ?? '', folder: d.folder ?? null };
  show();
}
function move(names: string[], folder: number | null = null) {
  files.value = names;
  moveOnly.value = true;
  form.value.folder = folder;
  show();
}
function show() {
  error.value = '';
  fields.value = {};
  box.value?.showModal();
}
const close = () => box.value?.close();

async function save() {
  busy.value = true;
  error.value = '';
  fields.value = {};
  try {
    const out = moveOnly.value
      ? await api.post(`/patients/${props.code}/documents/move`, { filenames: files.value, folder: form.value.folder })
      : await api.post(`/patients/${props.code}/documents/classify`, { filename: files.value[0], ...form.value, folder: form.value.folder ?? '' });
    close();
    emit('saved', out);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.';
    if (e instanceof ApiError) fields.value = e.fields;
  } finally {
    busy.value = false;
  }
}
defineExpose({ edit, move });
</script>

<template>
  <dialog ref="box" class="app-dialog" aria-labelledby="doc-edit-h">
    <form class="card" @submit.prevent="save">
      <div class="card-head"><h2 id="doc-edit-h">{{ moveOnly ? 'انتقال به پوشه' : 'ویرایش' }}</h2></div>
      <div class="card-body stack-lg">
        <p v-if="error" class="info-box" role="alert">{{ error }}</p>
        <div class="upload-fields">
          <template v-if="!moveOnly">
            <div v-float class="field span-2">
              <label for="de-title">عنوان</label>
              <input id="de-title" v-model="form.title" class="input" type="text" maxlength="200">
              <p v-if="fields.title" class="field-error">{{ fields.title }}</p>
            </div>
            <div v-float class="field">
              <label for="de-category">طبقه‌بندی</label>
              <select id="de-category" v-model="form.category" class="select"><option v-for="(l, k) in CATEGORY" :key="k" :value="k">{{ l }}</option></select>
            </div>
            <div class="field">
              <label for="de-date">تاریخ سند</label>
              <JalaliInput id="de-date" v-model="form.docDate" placeholder="۱۴۰۳/۰۵/۱۲" />
              <p v-if="fields.docDate" class="field-error">{{ fields.docDate }}</p>
            </div>
          </template>
          <div v-float class="field" :class="{ 'span-2': moveOnly }">
            <label for="de-folder">پوشه</label>
            <select id="de-folder" v-model="form.folder" class="select">
              <option :value="null">بدون پوشه</option>
              <option v-for="f in folders" :key="f.id" :value="f.id">{{ f.name }}</option>
            </select>
          </div>
          <div v-if="!moveOnly" v-float class="field span-2">
            <label for="de-notes">یادداشت</label>
            <textarea id="de-notes" v-model="form.notes" class="textarea" maxlength="2000"></textarea>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="busy">ذخیره</button>
          <button class="btn btn-ghost" type="button" @click="close">انصراف</button>
        </div>
      </div>
    </form>
  </dialog>
</template>
