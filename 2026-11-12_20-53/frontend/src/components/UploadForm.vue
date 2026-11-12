<script setup lang="ts">
// Upload one document with its metadata (legacy profile and documents page forms).
import { ref } from 'vue';
import Icon from './Icon.vue';
import DropZone from './DropZone.vue';
import JalaliInput from './JalaliInput.vue';
import { api } from '../api/client';
import { CATEGORY } from '../lib/fmt';
import { useAction } from '../lib/usePage';
import { vFloat } from '../lib/directives';

const props = defineProps<{ code: string; compact?: boolean; idPrefix: string; withNotes?: boolean }>();
const emit = defineEmits<{ done: [] }>();
const files = ref<File[]>([]);
const shrinking = ref(false);
const meta = ref({ category: 'other', docDate: '', title: '', notes: '' });
const zone = ref<InstanceType<typeof DropZone> | null>(null);
const { busy, error, fields, run } = useAction();

async function submit() {
  if (shrinking.value) return;
  const form = new FormData();
  if (files.value[0]) form.append('file', files.value[0]);
  for (const [k, v] of Object.entries(meta.value)) form.append(k, v);
  const ok = await run(() => api.post(`/patients/${props.code}/documents`, form));
  if (ok) {
    meta.value = { category: 'other', docDate: '', title: '', notes: '' };
    zone.value?.reset();
    emit('done');
  }
}
</script>

<template>
  <form class="card-body upload-form" :class="{ 'upload-form-compact': compact }" @submit.prevent="submit">
    <p v-if="error" class="info-box" role="alert">{{ error }}</p>
    <DropZone :id="`${idPrefix}-file`" ref="zone" v-model="files" required @busy="shrinking = $event" />
    <div class="upload-fields">
      <div v-float class="field">
        <label :for="`${idPrefix}-category`">طبقه‌بندی</label>
        <select :id="`${idPrefix}-category`" v-model="meta.category" class="select">
          <option v-for="(l, k) in CATEGORY" :key="k" :value="k">{{ l }}</option>
        </select>
      </div>
      <div class="field">
        <label :for="`${idPrefix}-date`">تاریخ سند</label>
        <JalaliInput :id="`${idPrefix}-date`" v-model="meta.docDate" placeholder="۱۴۰۳/۰۵/۱۲" />
        <p v-if="fields.docDate" class="field-error">{{ fields.docDate }}</p>
      </div>
      <div v-float class="field span-2">
        <label :for="`${idPrefix}-title`">عنوان</label>
        <input :id="`${idPrefix}-title`" v-model="meta.title" class="input" type="text" maxlength="200" placeholder="مثلاً: عکس رادیولوژی قفسه‌ی سینه">
        <p v-if="fields.title" class="field-error">{{ fields.title }}</p>
      </div>
      <div v-if="withNotes" v-float class="field span-2">
        <label :for="`${idPrefix}-notes`">یادداشت</label>
        <textarea :id="`${idPrefix}-notes`" v-model="meta.notes" class="textarea" maxlength="2000"></textarea>
      </div>
      <div class="form-actions span-2">
        <button class="btn btn-primary" type="submit" :disabled="busy || shrinking"><Icon name="upload" />بارگذاری</button>
      </div>
    </div>
  </form>
</template>
