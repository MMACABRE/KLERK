<script setup lang="ts">
// Payments list (legacy views/finance/payments.ejs).
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import FinanceNav from '../../components/FinanceNav.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('پرداخت‌ها');
const route = useRoute();
const router = useRouter();
const KIND: Record<string, string> = { payment: 'پرداخت', refund: 'بازپرداخت', move_out: 'انتقال (خروج)', move_in: 'انتقال (ورود)' };
const f = ref({ from: qs(route.query.from), to: qs(route.query.to), method: qs(route.query.method), account: qs(route.query.account), kind: qs(route.query.kind) });
const page = Number(qs(route.query.page)) || 1;
const { data, error } = useLoad(async () => {
  const d = await api.get('/finance/payments', { ...f.value, page });
  f.value = { from: d.filters.from, to: d.filters.to, method: String(d.filters.method), account: String(d.filters.account), kind: d.filters.kind };
  return d;
});
function query(p = 1) {
  const q: Record<string, string> = { from: f.value.from, to: f.value.to };
  if (f.value.method) q.method = f.value.method;
  if (f.value.account) q.account = f.value.account;
  if (f.value.kind) q.kind = f.value.kind;
  if (p > 1) q.page = String(p);
  return { path: '/finance/payments', query: q };
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/finance">امور مالی</RouterLink> / پرداخت‌ها</div><h1>پرداخت‌ها</h1></div></div>
  <FinanceNav here="payments" />
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <section v-if="data" class="card">
    <form class="card-body filter-bar" @submit.prevent="router.push(query())">
      <div class="field"><label for="f-from">از تاریخ</label><JalaliInput id="f-from" v-model="f.from" /></div>
      <div class="field"><label for="f-to">تا تاریخ</label><JalaliInput id="f-to" v-model="f.to" /></div>
      <div class="field"><label for="f-method">روش</label><select id="f-method" v-model="f.method" class="select"><option value="">همه</option><option v-for="m in data.methods" :key="m.id" :value="String(m.id)">{{ m.name }}</option></select></div>
      <div class="field"><label for="f-account">حساب</label><select id="f-account" v-model="f.account" class="select"><option value="">همه</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select></div>
      <div class="field"><label for="f-kind">نوع</label><select id="f-kind" v-model="f.kind" class="select"><option value="">همه</option><option v-for="(l, k) in KIND" :key="k" :value="k">{{ l }}</option></select></div>
      <div class="field filter-go"><button class="btn btn-primary" type="submit"><Icon name="filter" />نمایش</button></div>
    </form>
    <div class="card-foot"><span>{{ fa(data.sum.n) }} ردیف · جمع <span class="money">{{ data.sum.total.display }}</span> · درآمد (پرداخت منهای بازپرداخت) <span class="money">{{ data.sum.income.display }}</span></span></div>
    <div v-if="!data.data.length" class="card-body"><p class="muted">در این بازه پرداختی نیست.</p></div>
    <template v-else>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">تاریخ</th><th scope="col">بیمار</th><th scope="col">ویزیت</th><th scope="col">نوع</th><th scope="col">مبلغ</th><th scope="col">روش</th><th scope="col">حساب</th></tr></thead>
          <tbody>
            <tr v-for="r in data.data" :key="r.id">
              <td data-label="تاریخ">{{ r.paidOn.short }}</td>
              <td data-label="بیمار"><RouterLink :to="`/patients/${r.patient.code}`">{{ r.patient.firstName }} {{ r.patient.lastName }}</RouterLink> <span class="mono text-xs-muted">{{ r.patient.code }}</span></td>
              <td data-label="ویزیت"><RouterLink :to="`/visits/${r.visitId}`">{{ r.visitDate.short }}</RouterLink><span v-if="r.kind === 'payment' && r.paidOn.iso < r.visitDate.iso" class="chip chip-info chip-plain"> پیش‌پرداخت</span></td>
              <td data-label="نوع">{{ KIND[r.kind] }}</td>
              <td data-label="مبلغ"><b :class="{ 'qty-out': r.amount.rial < 0 }"><span class="money">{{ r.amount.display }}</span></b></td>
              <td data-label="روش">{{ r.method || '—' }}</td>
              <td data-label="حساب">{{ r.account || '—' }}</td>
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
