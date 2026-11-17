<script setup lang="ts">
// «سوابق درمان و مالی» (legacy views/patients/history.ejs): every visit with its bill, newest first, and the
// patient's standing discount.
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import Icon from '../../components/Icon.vue';
import MoneyInput from '../../components/MoneyInput.vue';
import { api } from '../../api/client';
import { can, session, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const code = String(route.params.code);
const disc = ref({ discKind: 'percent', discValue: '' });
const act = useAction();
const KIND: Record<string, string> = { payment: 'پرداخت', refund: 'بازپرداخت', move_out: 'انتقال به ویزیت دیگر', move_in: 'انتقال از ویزیت دیگر' };
const STATE: Record<string, [string, string]> = { scheduled: ['chip-info', 'برنامه‌ریزی‌شده'], done: ['chip-ok', 'انجام‌شده'], cancelled: ['chip-mute', 'لغو‌شده'] };
const curName = session.me?.currency === 'R' ? 'ریال' : 'تومان';
const { data, error, load } = useLoad(async () => {
  const d = await api.get(`/patients/${code}/history`);
  setTitle(`سوابق درمان و مالی ${d.patient.firstName} ${d.patient.lastName}`);
  disc.value = { discKind: d.patient.discKind === 'amount' ? 'amount' : 'percent', discValue: d.patient.discInput };
  return d;
});
async function saveDisc() {
  if (await act.run(() => api.put(`/patients/${code}/discount`, disc.value))) load();
}
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="breadcrumb"><RouterLink to="/patients">بیماران</RouterLink> / <RouterLink :to="`/patients/${code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink> / سوابق درمان و مالی</div>
    <div class="page-head">
      <div><h1>سوابق درمان و مالی</h1><p><RouterLink :to="`/patients/${code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink> · <span class="mono">{{ code }}</span> · {{ fa(data.visits.length) }} ویزیت</p></div>
      <a v-if="can('pdf')" class="btn btn-sm" :href="`/print/patients/${code}`"><Icon name="print" />چاپ پرونده‌ی کامل</a>
    </div>
    <section class="history-strip" aria-label="جمع مالی بیمار">
      <article class="card stat"><div class="stat-label">جمع صورتحساب‌ها</div><div class="stat-value text-xl"><span class="money">{{ data.totals.owed.display }}</span></div></article>
      <article class="card stat"><div class="stat-label">پرداخت‌شده</div><div class="stat-value text-xl"><span class="money">{{ data.totals.paid.display }}</span></div></article>
      <article class="card stat"><div class="stat-label">مانده</div><div class="stat-value text-xl"><span class="money">{{ data.totals.remaining.display }}</span></div></article>
      <article class="card stat"><div class="stat-label">بستانکار</div><div class="stat-value text-xl"><span class="money">{{ data.totals.credit.display }}</span></div></article>
    </section>
    <section class="card mb-4" aria-labelledby="disc-h">
      <div class="card-head"><div><h2 id="disc-h">تخفیف دائمی بیمار</h2><p>روی صورتحساب‌های تازه‌ی این بیمار، با اولین ردیف، گذاشته می‌شود.</p></div>
        <span class="chip chip-plain" :class="data.patient.discKind ? 'chip-info' : 'chip-mute'">{{ data.patient.discKind ? data.patient.discText : 'ندارد' }}</span></div>
      <form v-if="can('finance', 2)" class="card-body inline-form" @submit.prevent="saveDisc">
        <select v-model="disc.discKind" class="select select-sm" aria-label="نوع تخفیف"><option value="percent">درصد</option><option value="amount">مبلغ ({{ curName }})</option></select>
        <MoneyInput v-model="disc.discValue" placeholder="خالی یعنی بدون تخفیف" />
        <button class="btn btn-sm" type="submit" :disabled="act.busy.value">ثبت</button>
        <p v-if="act.error.value" class="field-error" role="alert">{{ act.error.value }}</p>
      </form>
    </section>
    <section v-if="!data.visits.length" class="card"><div class="card-body empty-state"><Icon name="wallet" /><p>این بیمار هنوز ویزیتی ندارد.</p></div></section>
    <section v-for="v in data.visits" :key="v.id" class="card history-visit" :aria-labelledby="`hv-${v.id}`">
      <div class="card-head">
        <div><h2 :id="`hv-${v.id}`"><RouterLink :to="`/visits/${v.id}`">{{ v.number ? 'ویزیت ' + fa(v.number) : 'ویزیت' }} — {{ v.date.long }}</RouterLink></h2>
          <p><span class="mono">{{ fa(v.time) }}</span><template v-if="v.reason"> · {{ v.reason }}</template></p></div>
        <div class="chips"><span class="chip" :class="STATE[v.status][0]">{{ STATE[v.status][1] }}</span>
          <span v-if="v.bill.credit.rial" class="chip chip-info">بستانکار {{ v.bill.credit.display }}</span>
          <span v-else-if="v.bill.remaining.rial" class="chip chip-warn">مانده {{ v.bill.remaining.display }}</span>
          <span v-else-if="v.bill.owed.rial" class="chip chip-ok">تسویه</span></div>
      </div>
      <div v-if="v.doctorNote && can('visits')" class="card-body"><div class="notes-box">{{ v.doctorNote }}</div></div>
      <div v-if="v.bill.lines.length || v.bill.payments.length" class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">شرح</th><th scope="col">تعداد</th><th scope="col">مبلغ</th></tr></thead>
          <tbody>
            <tr v-for="l in v.bill.lines" :key="`l${l.id}`"><td data-label="شرح">{{ l.name }}</td><td data-label="تعداد">{{ l.qty.display }}</td><td data-label="مبلغ"><span class="money">{{ l.net.display }}</span></td></tr>
            <tr v-if="v.bill.billDisc.rial"><td data-label="شرح">تخفیف کل</td><td></td><td data-label="مبلغ"><span class="money">-{{ v.bill.billDisc.display }}</span></td></tr>
            <tr v-for="p in v.bill.payments" :key="`p${p.id}`" class="row-mute"><td data-label="شرح">{{ KIND[p.kind] }} · {{ p.paidOn.short }}{{ p.method ? ' · ' + p.method : '' }}</td><td></td><td data-label="مبلغ"><span class="money">{{ p.amount.display }}</span></td></tr>
          </tbody>
        </table>
      </div>
      <div class="card-foot"><span>قابل پرداخت <span class="money">{{ v.bill.owed.display }}</span> · پرداخت‌شده <span class="money">{{ v.bill.paid.display }}</span></span><RouterLink class="btn btn-sm" :to="`/visits/${v.id}`">صفحه‌ی ویزیت</RouterLink></div>
    </section>
  </template>
</template>
