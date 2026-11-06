<script setup lang="ts">
// Patients list (legacy views/patients/list.ejs).
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import Pager from '../../components/Pager.vue';
import { api } from '../../api/client';
import { can, has, setTitle } from '../../lib/session';
import { fa, faCount, initialsOf, SEX, STATUS } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('بیماران');
const route = useRoute();
const router = useRouter();
const f = ref({ q: qs(route.query.q), status: qs(route.query.status), sex: qs(route.query.sex), sort: qs(route.query.sort) || 'updated' });
const page = Number(qs(route.query.page)) || 1;
const { data, error, loading } = useLoad(() => api.get('/patients', { ...f.value, page }));

function query(p = 1, over: Record<string, string> = {}) {
  const v = { ...f.value, ...over };
  const out: Record<string, string> = {};
  if (v.q) out.q = v.q;
  if (v.status) out.status = v.status;
  if (v.sex) out.sex = v.sex;
  if (v.sort !== 'updated') out.sort = v.sort;
  if (p > 1) out.page = String(p);
  return { path: '/patients', query: out };
}
const apply = (over: Record<string, string> = {}) => router.push(query(1, over));
const SORTS = [['updated', 'آخرین به‌روزرسانی'], ['name', 'نام خانوادگی (الف تا ی)'], ['birth_desc', 'تاریخ تولد (جدیدترین)'], ['birth_asc', 'تاریخ تولد (قدیمی‌ترین)'], ['code', 'کد بیمار']];
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Patients</span></div>
      <h1>فهرست بیماران</h1>
      <p v-if="data">{{ faCount(data.pagination.total) }} بیمار پیدا شد</p>
    </div>
    <div class="page-actions">
      <RouterLink v-if="has('layout')" class="btn" to="/patients/layout"><Icon name="layout" />چیدمان فرم</RouterLink>
      <RouterLink v-if="can('patients', 2)" class="btn btn-primary" to="/patients/new"><Icon name="plus" />بیمار جدید</RouterLink>
    </div>
  </div>

  <section class="card">
    <form @submit.prevent="apply()">
      <div class="toolbar">
        <div class="input-group flex-1-240-420">
          <Icon name="search" />
          <input v-model="f.q" class="input" type="search" placeholder="نام، کد یا شماره تلفن" aria-label="جستجوی بیماران">
        </div>
        <select v-model="f.sex" class="select" aria-label="فیلتر بر اساس جنسیت">
          <option value="">همه‌ی جنسیت‌ها</option>
          <option value="male">مرد</option>
          <option value="female">زن</option>
        </select>
        <select v-model="f.sort" class="select" aria-label="مرتب‌سازی">
          <option v-for="[v, l] in SORTS" :key="v" :value="v">{{ l }}</option>
        </select>
        <button class="btn btn-primary" type="submit">اعمال</button>
        <RouterLink to="/search" class="link-secondary">جستجوی پیشرفته</RouterLink>
      </div>
      <div class="toolbar-gap">
        <button class="chip chip-filter" :class="{ 'is-on': f.status === '' }" type="button" :aria-pressed="f.status === ''" @click="apply({ status: '' })">همه</button>
        <button v-for="(s, key) in STATUS" :key="key" class="chip chip-filter" :class="{ 'is-on': f.status === key }" type="button"
          :aria-pressed="f.status === key" @click="apply({ status: String(key) })">{{ s.label }}</button>
      </div>
    </form>

    <div v-if="loading" class="card-body"><p class="muted">در حال بارگذاری…</p></div>
    <div v-else-if="error" class="card-body"><p class="info-box" role="alert">{{ error }}</p></div>
    <div v-else-if="!data.data.length" class="card-body"><p class="muted">بیماری با این مشخصات پیدا نشد.</p></div>
    <template v-else>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">بیمار</th><th scope="col">کد بیمار</th><th scope="col">سن</th><th scope="col">وضعیت</th><th scope="col">آخرین به‌روزرسانی</th></tr></thead>
          <tbody>
            <tr v-for="p in data.data" :key="p.id">
              <td data-label="بیمار"><div class="person"><span class="avatar avatar-sm">{{ initialsOf(p.firstName, p.lastName) }}</span><div><RouterLink :to="`/patients/${p.code}`"><b>{{ p.firstName }} {{ p.lastName }}</b></RouterLink><span>{{ SEX[p.sex] || '' }}</span></div></div></td>
              <td data-label="کد بیمار" class="mono">{{ p.code }}</td>
              <td data-label="سن">{{ p.age === null ? '—' : fa(p.age) }}</td>
              <td data-label="وضعیت"><span class="chip" :class="STATUS[p.status].chip">{{ STATUS[p.status].label }}</span></td>
              <td data-label="آخرین به‌روزرسانی">{{ p.updatedDay?.short }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-foot">
        <span>نمایش {{ faCount((data.pagination.page - 1) * data.pagination.pageSize + 1) }} تا {{ faCount(Math.min(data.pagination.total, data.pagination.page * data.pagination.pageSize)) }} از {{ faCount(data.pagination.total) }} بیمار</span>
        <Pager :page="data.pagination.page" :pages="data.pagination.pages" :to="(n) => query(n)" />
      </div>
    </template>
  </section>
</template>
