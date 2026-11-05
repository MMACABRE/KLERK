<script setup lang="ts">
// Activity log (legacy views/admin/audit.ejs).
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { fa, faCount } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('گزارش فعالیت');
const route = useRoute();
const router = useRouter();
const f = ref({ user: qs(route.query.user), action: qs(route.query.action), patient: qs(route.query.patient) });
const page = Number(qs(route.query.page)) || 1;
const { data, error } = useLoad(() => api.get('/audit', { ...f.value, page }));
function query(p = 1) {
  const q: Record<string, string> = {};
  if (f.value.user) q.user = f.value.user;
  if (f.value.action) q.action = f.value.action;
  if (f.value.patient) q.patient = f.value.patient;
  if (p > 1) q.page = String(p);
  return { path: '/admin/audit', query: q };
}
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Activity Log</span></div>
      <h1>گزارش فعالیت</h1>
      <p>هر ورود، ویرایش، بارگذاری، دریافت فایل و خروجی اینجا ثبت می‌شود.<template v-if="data"> {{ faCount(data.pagination.total) }} مورد پیدا شد.</template></p>
    </div>
  </div>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <section v-if="data" class="card">
    <form class="toolbar" @submit.prevent="router.push(query())">
      <select v-model="f.user" class="select" aria-label="فیلتر بر اساس کاربر">
        <option value="">همه‌ی کاربران</option>
        <option v-for="u in data.users" :key="u.id" :value="String(u.id)">{{ u.displayName }} ({{ u.username }})</option>
      </select>
      <select v-model="f.action" class="select" aria-label="فیلتر بر اساس رویداد">
        <option value="">همه‌ی رویدادها</option>
        <option v-for="(l, k) in data.actions" :key="k" :value="k">{{ l }}</option>
      </select>
      <input v-model="f.patient" class="input" type="text" placeholder="کد بیمار (P-000123)" aria-label="فیلتر بر اساس کد بیمار" dir="ltr" maxlength="20">
      <button class="btn btn-primary" type="submit">اعمال</button>
      <RouterLink class="link-secondary" to="/admin/audit">پاک‌کردن فیلترها</RouterLink>
    </form>
    <div v-if="data.patientNote" class="info-box" role="alert">{{ data.patientNote }}</div>
    <div v-if="!data.data.length" class="card-body"><p class="muted">موردی پیدا نشد.</p></div>
    <template v-else>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">زمان</th><th scope="col">کاربر</th><th scope="col">رویداد</th><th scope="col">بیمار</th><th scope="col">جزئیات</th></tr></thead>
          <tbody>
            <tr v-for="r in data.data" :key="r.id">
              <td data-label="زمان"><span class="text-sm">{{ r.tsJalali }}</span></td>
              <td data-label="کاربر">{{ r.displayName || '—' }}<span v-if="r.username" class="mono text-xs-subtle"> {{ r.username }}</span></td>
              <td data-label="رویداد">{{ r.actionLabel }}</td>
              <td data-label="بیمار"><RouterLink v-if="r.code" class="mono" :to="`/patients/${r.code}`">{{ r.code }}</RouterLink><template v-else>—</template></td>
              <td data-label="جزئیات"><span class="mono">{{ r.detail || '—' }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-foot">
        <span>نمایش {{ faCount((data.pagination.page - 1) * data.pagination.pageSize + 1) }} تا {{ faCount(Math.min(data.pagination.total, data.pagination.page * data.pagination.pageSize)) }} از {{ faCount(data.pagination.total) }} مورد</span>
        <div v-if="data.pagination.pages > 1" class="pagination">
          <RouterLink class="page-btn" :to="query(Math.max(1, data.pagination.page - 1))" :aria-disabled="data.pagination.page === 1 ? 'true' : undefined">قبلی</RouterLink>
          <span class="page-btn" aria-current="page">{{ fa(data.pagination.page) }} از {{ fa(data.pagination.pages) }}</span>
          <RouterLink class="page-btn" :to="query(Math.min(data.pagination.pages, data.pagination.page + 1))" :aria-disabled="data.pagination.page === data.pagination.pages ? 'true' : undefined">بعدی</RouterLink>
        </div>
      </div>
    </template>
  </section>
</template>
