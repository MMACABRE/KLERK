<script setup lang="ts">
// Documents of one patient (legacy views/documents/index.ejs): upload with metadata, filter, edit, delete; folders
// (SPEC §14.5.4): a folder bar above the gallery filters by folder (kept in the URL as ?folder=), documents move by
// «انتقال به پوشه» on a card, by selection, or by dragging cards onto a folder chip (pointer devices from 900 px;
// drag is an extra, never the only way). Folders are labels in the database; the folder on disk stays flat.
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import DocTile from '../../components/DocTile.vue';
import DocEditDialog from '../../components/DocEditDialog.vue';
import FolderBar, { type Bar } from '../../components/FolderBar.vue';
import FolderTile from '../../components/FolderTile.vue';
import UploadForm from '../../components/UploadForm.vue';
import { api, ApiError } from '../../api/client';
import { can, setTitle } from '../../lib/session';
import { CATEGORY, fa } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

const route = useRoute();
const router = useRouter();
const code = String(route.params.code);
const f = ref({ q: qs(route.query.q), category: qs(route.query.category) });
const folder = computed(() => qs(route.query.folder));
const actionError = ref('');
const selecting = ref(false);
const selected = ref(new Set<string>());
// Windows-style folders (owner, 2026-11-16): the top level lists the folders and only the files in no folder; an open
// folder lists only its own files. A search or category filter at the top level looks through every file.
const searching = computed(() => Boolean(f.value.q || f.value.category));
const { data, error, load } = useLoad(async () => {
  const d = await api.get(`/patients/${code}/documents`, { ...f.value, folder: folder.value || (searching.value ? '' : 'none') });
  setTitle(`اسناد ${d.patient.firstName} ${d.patient.lastName}`);
  // a selection only ever holds documents the gallery shows
  const shown = new Set(d.docs.map((x: any) => x.filename));
  if ([...selected.value].some((n) => !shown.has(n))) selected.value = new Set([...selected.value].filter((n) => shown.has(n)));
  // ?folder= naming no folder of this patient (a deleted folder, a hand-edited link) shows «همه» instead of an empty
  // gallery with no chip lit.
  if (folder.value && !d.folders.some((x: any) => String(x.id) === folder.value)) {
    router.replace({ path: `/patients/${code}/documents`, query: query({ folder: '' }) });
  }
  return d;
});
const query = (extra: Record<string, string> = {}) => {
  const q: Record<string, string> = { ...(f.value.q ? { q: f.value.q } : {}), ...(f.value.category ? { category: f.value.category } : {}), ...(folder.value ? { folder: folder.value } : {}), ...extra };
  return Object.fromEntries(Object.entries(q).filter(([, v]) => v));
};
const apply = () => (selected.value = new Set(), router.push({ path: `/patients/${code}/documents`, query: query() }));
const pick = (key: string) => { selected.value = new Set(); router.push({ path: `/patients/${code}/documents`, query: query({ folder: key }) }); };
const setBar = (bar: Bar) => { if (data.value) Object.assign(data.value, bar); };
const folderName = (id: number | null) => data.value?.folders.find((x: any) => x.id === id)?.name ?? '';
const openFolder = computed<number | null>(() => (/^\d+$/.test(folder.value) ? Number(folder.value) : null));
const editor = can('documents', 2);

// ---- edit and move (one dialog) ----
const dialog = ref<InstanceType<typeof DocEditDialog> | null>(null);
function saved(out: any) {
  if (out?.folders) setBar(out);
  selected.value = new Set();
  load();
}
const fail = (e: unknown) => { actionError.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.'; load(); };

// ---- selection ----
function toggle(name: string, on: boolean) {
  const s = new Set(selected.value);
  if (on) s.add(name); else s.delete(name);
  selected.value = s;
}
const stopSelecting = () => { selecting.value = false; selected.value = new Set(); };

// ---- drag cards onto a folder chip ----
const dragOk = window.matchMedia('(min-width: 900px) and (pointer: fine)');
const dropOn = ref<string | null>(null);
let drag: { names: string[]; sx: number; sy: number; on: boolean; ghost: HTMLElement | null } | null = null;
function grab(ev: PointerEvent, d: any) {
  if (!editor || !dragOk.matches || ev.pointerType === 'touch') return;
  const names = selecting.value && selected.value.has(d.filename) ? [...selected.value] : [d.filename];
  drag = { names, sx: ev.clientX, sy: ev.clientY, on: false, ghost: null };
  window.addEventListener('pointermove', moveDrag);
  window.addEventListener('pointerup', endDrag);
  window.addEventListener('pointercancel', cancelDrag);
}
function moveDrag(ev: PointerEvent) {
  if (!drag) return;
  if (!drag.on) {
    if (Math.hypot(ev.clientX - drag.sx, ev.clientY - drag.sy) < 6) return;
    drag.on = true;
    drag.ghost = document.createElement('div');
    drag.ghost.className = 'doc-ghost';
    drag.ghost.textContent = drag.names.length > 1 ? `${fa(drag.names.length)} سند` : '۱ سند';
    document.body.append(drag.ghost);
    document.body.classList.add('is-dragging-doc');
  }
  ev.preventDefault();
  drag.ghost!.style.setProperty('--gx', `${ev.clientX}px`);
  drag.ghost!.style.setProperty('--gy', `${ev.clientY}px`);
  const chip = document.elementFromPoint(ev.clientX, ev.clientY)?.closest<HTMLElement>('[data-drop]');
  dropOn.value = chip?.dataset.drop ?? null;
}
async function endDrag() {
  const d = drag;
  const target = dropOn.value;
  cancelDrag();
  if (!d?.on) return;
  // The click that ends a drag must not open the card; if the browser sends none (released outside the window),
  // the swallower goes away on its own so it never eats a later real click.
  const swallow = (e: Event) => { e.preventDefault(); e.stopPropagation(); };
  window.addEventListener('click', swallow, { capture: true, once: true });
  setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 0);
  if (target === null) return;
  try {
    saved(await api.post(`/patients/${code}/documents/move`, { filenames: d.names, folder: target === 'none' ? null : Number(target) }));
  } catch (e) { fail(e); }
}
function cancelDrag() {
  drag?.ghost?.remove();
  document.body.classList.remove('is-dragging-doc');
  drag = null;
  dropOn.value = null;
  window.removeEventListener('pointermove', moveDrag);
  window.removeEventListener('pointerup', endDrag);
  window.removeEventListener('pointercancel', cancelDrag);
}
onBeforeUnmount(cancelDrag);
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="page-head">
      <div>
        <div class="breadcrumb"><RouterLink to="/patients" lang="en">Patients</RouterLink> / <RouterLink :to="`/patients/${code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink> / <span lang="en">Documents</span></div>
        <h1>اسناد و پیوست‌ها</h1>
        <p><span class="mono">{{ code }}</span> · پرونده‌ی بیمار {{ data.patient.firstName }} {{ data.patient.lastName }}</p>
      </div>
    </div>
    <p v-if="actionError" class="info-box" role="alert">{{ actionError }}</p>
    <section v-if="editor" class="card" aria-labelledby="upload-h">
      <div class="card-head"><h2 id="upload-h">بارگذاری سند</h2></div>
      <UploadForm :code="code" id-prefix="doc" with-notes :folders="data.folders" :folder="openFolder" @done="load" />
    </section>
    <section class="card" aria-labelledby="docs-h">
      <div class="card-head"><h2 id="docs-h">اسناد</h2><p>{{ fa(data.docs.length) }} فایل</p></div>
      <FolderBar :code="code" :folders="data.folders" :unfiled="data.unfiledCount" :current="folder" :edit="editor" :drop-on="dropOn" @pick="pick" @bar="setBar" @error="actionError = $event" />
      <form class="toolbar" role="search" @submit.prevent="apply">
        <div class="input-group">
          <Icon name="search" />
          <input v-model="f.q" class="input" type="search" placeholder="جستجوی اسناد" aria-label="جستجوی اسناد">
        </div>
        <select v-model="f.category" class="select" aria-label="فیلتر بر اساس طبقه‌بندی">
          <option value="">همه‌ی طبقه‌بندی‌ها</option>
          <option v-for="(l, k) in CATEGORY" :key="k" :value="k">{{ l }}</option>
          <option value="unclassified">طبقه‌بندی نشده</option>
        </select>
        <button class="btn btn-sm" type="submit">اعمال فیلتر</button>
        <button v-if="editor && data.docs.length" class="btn btn-sm btn-ghost" type="button" :aria-pressed="selecting" @click="selecting ? stopSelecting() : (selecting = true)"><Icon name="check" />انتخاب</button>
      </form>
      <div v-if="!data.docs.length && !(folder === '' && !searching && data.folders.length)" class="card-body"><p class="muted">{{ folder ? 'این پوشه خالی است.' : 'سندی پیدا نشد.' }}</p></div>
      <div v-else class="doc-gallery card-body">
        <template v-if="folder === '' && !searching">
          <FolderTile v-for="fo in data.folders" :key="fo.id" :f="fo" :drop-on="dropOn" @open="pick" />
        </template>
        <DocTile v-for="d in data.docs" :key="d.filename" :d="d" :code="code" :folder-name="folder === '' && searching ? folderName(d.folder) : ''"
          :selectable="selecting" :selected="selected.has(d.filename)" :class="{ 'is-dragged': dropOn !== null && (selected.has(d.filename) || false) }"
          @select="toggle(d.filename, $event)" @edit="dialog?.edit($event)" @move="dialog?.move([$event.filename], $event.folder)"
          @grab="grab($event, d)" @changed="load" @error="actionError = $event" />
      </div>
      <div v-if="selecting && selected.size" class="select-bar" role="region" aria-label="اسناد انتخاب‌شده">
        <span>{{ fa(selected.size) }} سند انتخاب شد</span>
        <button type="button" class="btn btn-sm btn-primary" @click="dialog?.move([...selected])"><Icon name="folder" />انتقال به پوشه</button>
        <button type="button" class="btn btn-sm btn-ghost" @click="stopSelecting">لغو</button>
      </div>
    </section>
    <DocEditDialog ref="dialog" :code="code" :folders="data.folders" @saved="saved" />
  </template>
</template>
