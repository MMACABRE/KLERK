<script setup lang="ts">
// Documents of one patient (legacy views/documents/index.ejs): upload with metadata, filter, classify, delete.
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import DocTile from '../../components/DocTile.vue';
import UploadForm from '../../components/UploadForm.vue';
import { api } from '../../api/client';
import { can, setTitle } from '../../lib/session';
import { CATEGORY, fa } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

const route = useRoute();
const router = useRouter();
const code = String(route.params.code);
const f = ref({ q: qs(route.query.q), category: qs(route.query.category) });
const actionError = ref('');
const { data, error, load } = useLoad(async () => {
  const d = await api.get(`/patients/${code}/documents`, f.value);
  setTitle(`اسناد ${d.patient.firstName} ${d.patient.lastName}`);
  return d;
});
const apply = () => router.push({ path: `/patients/${code}/documents`, query: { ...(f.value.q ? { q: f.value.q } : {}), ...(f.value.category ? { category: f.value.category } : {}) } });
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
    <section v-if="can('documents', 2)" class="card" aria-labelledby="upload-h">
      <div class="card-head"><h2 id="upload-h">بارگذاری سند</h2></div>
      <UploadForm :code="code" id-prefix="doc" with-notes @done="load" />
    </section>
    <section class="card" aria-labelledby="docs-h">
      <div class="card-head"><h2 id="docs-h">اسناد</h2><p>{{ fa(data.docs.length) }} فایل</p></div>
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
      </form>
      <div v-if="!data.docs.length" class="card-body"><p class="muted">سندی پیدا نشد.</p></div>
      <div v-else class="doc-gallery card-body">
        <DocTile v-for="d in data.docs" :key="d.filename" :d="d" :code="code" classify @changed="load" @error="actionError = $event" />
      </div>
    </section>
  </template>
</template>
