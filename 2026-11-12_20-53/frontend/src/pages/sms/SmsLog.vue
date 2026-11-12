<script setup lang="ts">
// SMS log (legacy views/sms/log.ejs).
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import SmsNav from '../../components/SmsNav.vue';
import { api } from '../../api/client';
import { can, setTitle } from '../../lib/session';
import { fa, faCount } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('پیامک');
const route = useRoute();
const router = useRouter();
const f = ref({ status: qs(route.query.status), kind: qs(route.query.kind) });
const page = Number(qs(route.query.page)) || 1;
const { data, error, load } = useLoad(() => api.get('/sms', { ...f.value, page }));
function query(p = 1) {
  const q: Record<string, string> = {};
  if (f.value.status) q.status = f.value.status;
  if (f.value.kind) q.kind = f.value.kind;
  if (p > 1) q.page = String(p);
  return { path: '/sms', query: q };
}
async function retry(id: number) {
  await api.post(`/sms/${id}/retry`);
  load();
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb">پیامک / گزارش ارسال</div><h1>پیامک</h1></div></div>
  <SmsNav here="log" />
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div v-if="!data.ready.on" class="callout callout-info mb-4" role="status"><Icon name="alert" /><span>پیامک غیرفعال است. برای شروع، از بخش «تنظیمات» آن را روشن کنید.</span></div>
    <div v-else-if="!data.ready.hasKey" class="callout mb-4" role="status"><Icon name="key" /><span>کلید پیامک ثبت نشده است. پیامکی ارسال نمی‌شود.</span></div>
    <p v-if="data.ready.balance !== ''" class="sms-balance muted">اعتبار: <b>{{ fa(Math.floor(Number(data.ready.balance))) }} پیام</b><template v-if="data.ready.balanceAt"> · خوانده‌شده در {{ data.ready.balanceAt }}</template></p>
    <section class="card">
      <form class="card-body filter-bar" @submit.prevent="router.push(query())">
        <div class="field"><label for="f-status">وضعیت</label><select id="f-status" v-model="f.status" class="select"><option value="">همه</option><option v-for="(l, k) in data.statuses" :key="k" :value="k">{{ l }}</option></select></div>
        <div class="field"><label for="f-kind">نوع</label><select id="f-kind" v-model="f.kind" class="select"><option value="">همه</option><option v-for="(l, k) in data.kinds" :key="k" :value="k">{{ l }}</option></select></div>
        <div class="field filter-go"><button class="btn btn-primary" type="submit"><Icon name="filter" />نمایش</button></div>
      </form>
      <div class="card-foot"><span>{{ faCount(data.pagination.total) }} پیام</span></div>
      <div v-if="!data.data.length" class="card-body"><p class="muted">هنوز پیامکی ثبت نشده است.</p></div>
      <template v-else>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th scope="col">زمان</th><th scope="col">بیمار</th><th scope="col">نوع</th><th scope="col">متن</th><th scope="col">وضعیت</th></tr></thead>
            <tbody>
              <tr v-for="m in data.data" :key="m.id">
                <td data-label="زمان">{{ (m.sentAt || m.createdAt).text }}</td>
                <td data-label="بیمار"><template v-if="m.patient"><RouterLink :to="`/patients/${m.patient.code}`">{{ m.patient.firstName }} {{ m.patient.lastName }}</RouterLink><br></template><span class="mono text-xs-muted">{{ m.phone || '' }}</span></td>
                <td data-label="نوع">{{ m.kindLabel }}</td>
                <td data-label="متن" class="sms-text">{{ m.body || '—' }}</td>
                <td data-label="وضعیت">
                  <span class="chip" :class="m.statusChip">{{ m.statusLabel }}</span>
                  <span v-if="m.reason" class="text-xs-muted sms-reason">{{ m.reason }}</span>
                  <button v-if="m.status === 'failed' && can('sms', 2)" class="btn btn-sm" type="button" @click="retry(m.id)">ارسال دوباره</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="data.pagination.pages > 1" class="card-foot"><span>صفحه‌ی {{ fa(data.pagination.page) }} از {{ fa(data.pagination.pages) }}</span><div class="user-actions">
          <RouterLink v-if="data.pagination.page > 1" class="btn btn-sm" :to="query(data.pagination.page - 1)">قبلی</RouterLink>
          <RouterLink v-if="data.pagination.page < data.pagination.pages" class="btn btn-sm" :to="query(data.pagination.page + 1)">بعدی</RouterLink>
        </div></div>
      </template>
    </section>
  </template>
</template>
