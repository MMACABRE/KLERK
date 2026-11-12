<script setup lang="ts">
// Record a payment from the Finance tab (legacy views/finance/pay.ejs): patient, then visit, then the payment form.
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import FinanceNav from '../../components/FinanceNav.vue';
import MoneyInput from '../../components/MoneyInput.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import { api } from '../../api/client';
import { can, session, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { qs, useAction, useLoad } from '../../lib/usePage';

setTitle('ثبت پرداخت');
const route = useRoute();
const router = useRouter();
const q = ref(qs(route.query.q));
const curName = session.me?.currency === 'R' ? 'ریال' : 'تومان';
const forms = ref<Record<number, any>>({});
const act = useAction();
const notice = ref(route.query.ok === '1' ? 'پرداخت ثبت شد.' : '');
const { data, error, load } = useLoad(async () => {
  const d = await api.get('/finance/pay', { q: q.value, patient: qs(route.query.patient), visit: qs(route.query.visit) });
  for (const v of d.visits) {
    forms.value[v.id] = { amount: v.bill.remaining.rial ? v.bill.remaining.input : '', paidOn: d.today, methodId: String(d.methods[0]?.id ?? ''), accountId: '', note: '' };
  }
  return d;
});
async function payFor(vid: number, full = false) {
  const out = await act.run(() => api.post(`/visits/${vid}/payments`, { ...forms.value[vid], full: full ? '1' : '' }));
  if (out) { notice.value = 'پرداخت ثبت شد.'; await load(); }
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/finance">امور مالی</RouterLink> / ثبت پرداخت</div><h1>ثبت پرداخت</h1><p>بیمار را پیدا کنید، ویزیت را انتخاب کنید و پرداخت را ثبت کنید. پیش‌پرداخت برای ویزیت‌های برنامه‌ریزی‌شده هم ممکن است.</p></div></div>
  <FinanceNav here="pay" />
  <div v-if="notice" class="callout callout-info" role="status"><Icon name="check" /><span>{{ notice }}</span></div>
  <p v-if="error || act.error.value" class="info-box" role="alert">{{ error || act.error.value }}</p>
  <template v-if="data">
    <section v-if="!data.patient" class="card">
      <form class="card-body toolbar" role="search" @submit.prevent="router.push({ path: '/finance/pay', query: { q } })">
        <label class="sr-only" for="pay-q">جستجوی بیمار</label>
        <input id="pay-q" v-model="q" class="input" type="search" placeholder="نام، کد بیمار یا تلفن" autofocus>
        <button class="btn btn-primary" type="submit"><Icon name="search" />جستجو</button>
      </form>
      <div v-if="data.q && !data.found.length" class="card-body"><p class="muted">بیماری پیدا نشد.</p></div>
      <ul v-if="data.found.length" class="pick-list">
        <li v-for="p in data.found" :key="p.code"><RouterLink :to="{ path: '/finance/pay', query: { patient: p.code } }"><b>{{ p.firstName }} {{ p.lastName }}</b><span class="mono">{{ p.code }}</span><span v-if="p.phone" class="mono">{{ p.phone }}</span></RouterLink></li>
      </ul>
    </section>
    <template v-else>
      <div class="pay-patient mb-4">
        <b><RouterLink :to="`/patients/${data.patient.code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink></b> <span class="mono">{{ data.patient.code }}</span>
        <RouterLink class="btn btn-sm btn-ghost" to="/finance/pay">بیمار دیگر</RouterLink>
      </div>
      <section v-if="!data.visits.length" class="card"><div class="card-body"><p class="muted">این بیمار ویزیت پرداخت‌نشده یا برنامه‌ریزی‌شده‌ای ندارد. <RouterLink v-if="can('visits', 2)" :to="{ path: '/visits/new', query: { patient: data.patient.code } }">ثبت ویزیت تازه</RouterLink></p></div></section>
      <section v-for="v in data.visits" :key="v.id" class="card pay-visit" :class="{ 'is-chosen': v.id === data.chosen }" :aria-labelledby="`pv-${v.id}`">
        <div class="card-head">
          <div><h2 :id="`pv-${v.id}`"><RouterLink :to="`/visits/${v.id}`">{{ v.number ? 'ویزیت ' + fa(v.number) : 'ویزیت' }} — {{ v.date.long }}</RouterLink></h2>
            <p>قابل پرداخت <span class="money">{{ v.bill.owed.display }}</span> · پرداخت‌شده <span class="money">{{ v.bill.paid.display }}</span></p></div>
          <span v-if="v.bill.credit.rial" class="chip chip-info">بستانکار {{ v.bill.credit.display }}</span>
          <span v-else-if="v.bill.remaining.rial" class="chip chip-warn">مانده {{ v.bill.remaining.display }}</span>
          <span v-else class="chip chip-mute">{{ v.status === 'scheduled' ? 'پیش‌پرداخت' : 'تسویه' }}</span>
        </div>
        <form class="card-body form-grid form-grid-3" @submit.prevent="payFor(v.id)">
          <div class="field"><label :for="`a-${v.id}`">مبلغ ({{ curName }})</label><MoneyInput :id="`a-${v.id}`" v-model="forms[v.id].amount" required /></div>
          <div class="field"><label :for="`d-${v.id}`">تاریخ</label><JalaliInput :id="`d-${v.id}`" v-model="forms[v.id].paidOn" /></div>
          <div class="field"><label :for="`m-${v.id}`">روش پرداخت</label><select :id="`m-${v.id}`" v-model="forms[v.id].methodId" class="select" required><option v-for="m in data.methods" :key="m.id" :value="String(m.id)">{{ m.name }}</option></select></div>
          <div class="field"><label :for="`ac-${v.id}`">حساب</label><select :id="`ac-${v.id}`" v-model="forms[v.id].accountId" class="select"><option value="">حساب پیش‌فرض روش پرداخت</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select></div>
          <div class="field span-2"><label :for="`n-${v.id}`">یادداشت (اختیاری)</label><input :id="`n-${v.id}`" v-model="forms[v.id].note" class="input" type="text" maxlength="200"></div>
          <div class="form-actions span-all">
            <button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="check" />ثبت پرداخت</button>
            <button v-if="v.bill.remaining.rial" class="btn" type="button" :disabled="act.busy.value" @click="payFor(v.id, true)">پرداخت کامل ({{ v.bill.remaining.display }})</button>
          </div>
        </form>
      </section>
    </template>
  </template>
</template>
