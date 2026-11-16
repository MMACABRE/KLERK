<script setup lang="ts">
// Folder bar of a patient's documents, Windows style (owner, 2026-11-16; one level, folders are labels in the
// database): at the top level it offers «پوشه‌ی جدید» (the folders themselves are FolderTile cards in the gallery);
// inside a folder it shows the path «اسناد › <folder>» (the «اسناد» button goes back up and takes dropped cards out
// of the folder, data-drop="none") with «تغییر نام» (in place) and «حذف پوشه».
import { computed, nextTick, ref } from 'vue';
import Icon from './Icon.vue';
import ConfirmDelete from './ConfirmDelete.vue';
import { api, ApiError } from '../api/client';
import { fa } from '../lib/fmt';

export type Folder = { id: number; name: string; count: number };
export type Bar = { folders: Folder[]; unfiledCount: number };

const props = defineProps<{ code: string; folders: Folder[]; unfiled: number; current: string; edit: boolean; dropOn?: string | null }>();
const emit = defineEmits<{ pick: [string]; bar: [Bar]; error: [string] }>();
const open = computed(() => props.folders.find((f) => String(f.id) === props.current) ?? null);

const adding = ref(false);
const renaming = ref(false);
const name = ref('');
const fieldError = ref('');
const busy = ref(false);
const input = ref<HTMLInputElement | null>(null);

function start(kind: 'add' | 'rename') {
  adding.value = kind === 'add';
  renaming.value = kind === 'rename';
  name.value = kind === 'rename' && open.value ? open.value.name : '';
  fieldError.value = '';
  nextTick(() => input.value?.focus());
}
const stop = () => { adding.value = false; renaming.value = false; fieldError.value = ''; };

async function call(fn: () => Promise<any>, after?: (out: any) => void) {
  busy.value = true;
  fieldError.value = '';
  try {
    const out = await fn();
    emit('bar', { folders: out.folders, unfiledCount: out.unfiledCount });
    after?.(out);
    stop();
  } catch (e) {
    if (e instanceof ApiError && e.fields.name) fieldError.value = e.fields.name;
    else emit('error', e instanceof ApiError ? e.message : 'خطایی رخ داد.');
  } finally {
    busy.value = false;
  }
}
const save = () => (renaming.value && open.value
  ? call(() => api.post(`/patients/${props.code}/folders/${open.value!.id}`, { name: name.value }))
  : call(() => api.post(`/patients/${props.code}/folders`, { name: name.value }), (out) => emit('pick', String(out.id))));
const remove = () => open.value && call(() => api.del(`/patients/${props.code}/folders/${open.value!.id}`), () => emit('pick', ''));
</script>

<template>
  <div v-if="open || edit" class="folder-bar">
    <nav v-if="open" class="folder-path" aria-label="مسیر">
      <button type="button" class="btn btn-sm btn-ghost" data-drop="none" :class="{ 'is-drop': dropOn === 'none' }" @click="emit('pick', '')"><Icon name="folder" />اسناد</button>
      <span class="folder-sep" aria-hidden="true">/</span>
      <b class="folder-name" :title="open.name" aria-current="location">{{ open.name }}</b>
      <span class="muted">{{ fa(open.count) }} فایل</span>
    </nav>
    <form v-if="adding || renaming" class="folder-form" @submit.prevent="save" @keydown.esc="stop">
      <label class="sr-only" for="folder-name">نام پوشه</label>
      <input id="folder-name" ref="input" v-model="name" class="input" type="text" maxlength="60" :aria-invalid="Boolean(fieldError)" aria-describedby="folder-name-err">
      <button class="btn btn-sm btn-primary" type="submit" :disabled="busy">ذخیره</button>
      <button class="btn btn-sm btn-ghost" type="button" @click="stop">انصراف</button>
      <p v-if="fieldError" id="folder-name-err" class="field-error" role="alert">{{ fieldError }}</p>
    </form>
    <div v-else-if="edit" class="folder-open">
      <template v-if="open">
        <button type="button" class="btn btn-sm btn-ghost" @click="start('rename')"><Icon name="edit" />تغییر نام</button>
        <ConfirmDelete label="حذف پوشه" question="پوشه حذف می‌شود و اسناد آن به «بدون پوشه» منتقل می‌شوند." :busy="busy" @confirm="remove" />
      </template>
      <button v-else type="button" class="btn btn-sm folder-new" @click="start('add')"><Icon name="plus" />پوشه‌ی جدید</button>
    </div>
  </div>
</template>
