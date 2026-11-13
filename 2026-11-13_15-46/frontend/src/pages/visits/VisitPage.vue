<script setup lang="ts">
// Visit page = the bill (legacy views/visits/show.ejs, D27-D28): doctor's note, lines, discounts, totals, payments,
// payment edit, refund and credit move.
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import Icon from '../../components/Icon.vue';
import MoneyInput from '../../components/MoneyInput.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import { api } from '../../api/client';
import { can, has, session, setTitle } from '../../lib/session';
import { fa, moneyInput, visitState } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const id = String(route.params.id);
const cur = session.me?.currency ?? 'T';
const curName = cur === 'R' ? 'ریال' : 'تومان';
const KIND: Record<string, string> = { payment: 'پرداخت', refund: 'بازپرداخت', move_out: 'انتقال به ویزیت دیگر', move_in: 'انتقال از ویزیت دیگر' };
const notice = ref('');
const note = ref('');
const add = ref({ entry: '', qty: '1' });
const lineEdit = ref<Record<number, { discKind: string; discValue: string; price: string }>>({});
const billDisc = ref({ discKind: 'amount', discValue: '' });
const pay = ref({ amount: '', paidOn: '', methodId: '', accountId: '', note: '' });
const refund = ref({ amount: '', methodId: '', accountId: '', paidOn: '' });
const move = ref({ to: '', amount: '' });
const editing = ref<any>(null);
const act = useAction();

const { data, error, load } = useLoad(async () => {
  const d = await api.get(`/visits/${id}`);
  setTitle(`ویزیت ${d.patient.firstName} ${d.patient.lastName}`);
  note.value = d.visit.doctorNote ?? '';
  billDisc.value = { discKind: d.visit.discKind === 'percent' ? 'percent' : 'amount', discValue: d.visit.discKind === 'percent' ? String(d.visit.discValue || '') : moneyInput(d.visit.discValue, cur) };
  if (d.bill) {
    for (const l of d.bill.lines) {
      lineEdit.value[l.id] = { discKind: l.discKind === 'percent' ? 'percent' : 'amount', discValue: l.discKind === 'percent' ? String(l.discValue || '') : moneyInput(l.discValue, cur), price: l.overridePrice ? l.overridePrice.input : '' };
    }
    pay.value = { amount: d.bill.remaining.rial ? d.bill.remaining.input : '', paidOn: d.today, methodId: String(d.methods[0]?.id ?? ''), accountId: '', note: '' };
    refund.value = { amount: d.bill.credit.input, methodId: String(d.methods[0]?.id ?? ''), accountId: '', paidOn: d.today };
    move.value = { to: String(d.targets[0]?.id ?? ''), amount: d.bill.credit.input };
  }
  return d;
});
const state = computed(() => (data.value ? visitState(data.value.visit) : null));
const prepay = computed(() => data.value?.visit.status === 'scheduled');

async function doing(fn: () => Promise<unknown>, okText: string) {
  notice.value = '';
  const out = await act.run(fn);
  if (out !== undefined) { notice.value = okText; editing.value = null; add.value = { entry: '', qty: '1' }; await load(); }
}
const saveNote = () => doing(() => api.put(`/visits/${id}/note`, { doctorNote: note.value }), 'ذخیره شد.');
const addLine = () => doing(() => api.post(`/visits/${id}/lines`, add.value), 'به صورتحساب اضافه شد.');
const delLine = (lid: number) => doing(() => api.del(`/visits/${id}/lines/${lid}`), 'حذف شد.');
const lineDisc = (lid: number) => doing(() => api.put(`/visits/${id}/lines/${lid}/discount`, { discKind: lineEdit.value[lid].discKind, discValue: lineEdit.value[lid].discValue }), 'ذخیره شد.');
const linePrice = (lid: number) => doing(() => api.put(`/visits/${id}/lines/${lid}/price`, { price: lineEdit.value[lid].price }), 'ذخیره شد.');
const saveBillDisc = () => doing(() => api.put(`/visits/${id}/discount`, billDisc.value), 'ذخیره شد.');
const addPay = (full = false) => doing(() => api.post(`/visits/${id}/payments`, { ...pay.value, full: full ? '1' : '' }), 'پرداخت ثبت شد.');
const doRefund = () => doing(() => api.post(`/visits/${id}/refund`, refund.value), 'بازپرداخت ثبت شد.');
const doMove = () => doing(() => api.post(`/visits/${id}/move-credit`, move.value), 'اعتبار منتقل شد.');
const delPay = (pid: number) => doing(() => api.del(`/visits/${id}/payments/${pid}`), 'حذف شد.');
async function startEdit(pid: number) {
  const out = await act.run(() => api.get(`/visits/${id}/payments/${pid}`));
  if (out) {
    const p = out.payment;
    editing.value = { id: p.id, kind: p.kind, amount: p.amount.input, paidOn: p.paidOn.input, methodId: String(p.methodId ?? ''), accountId: String(p.accountId ?? ''), note: p.note ?? '' };
  }
}
const saveEdit = () => doing(() => api.patch(`/visits/${id}/payments/${editing.value.id}`, editing.value), 'ذخیره شد.');
const fieldErr = (k: string) => act.fields.value[k];
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="breadcrumb"><RouterLink to="/visits">ویزیت‌ها</RouterLink> / <RouterLink :to="`/patients/${data.patient.code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink></div>
    <div class="page-head visit-head">
      <div>
        <h1>{{ data.number ? 'ویزیت ' + fa(data.number) : 'ویزیت' }} — <RouterLink :to="`/patients/${data.patient.code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink></h1>
        <div class="meta">
          <span><span class="mono">{{ data.patient.code }}</span></span>
          <span>{{ data.visit.date.long }} · ساعت <span class="mono">{{ fa(data.visit.time) }}</span> تا <span class="mono">{{ fa(data.visit.until) }}</span></span>
          <span class="chip" :class="state!.chip">{{ state!.label }}</span>
        </div>
        <p v-if="data.visit.reason">{{ data.visit.reason }}</p>
      </div>
      <div class="head-actions">
        <RouterLink v-if="can('visits', 2)" class="btn btn-sm" :to="{ path: `/visits/${id}/edit`, query: { back: `/visits/${id}` } }">ویرایش ویزیت</RouterLink>
        <a v-if="data.bill && can('pdf')" class="btn btn-sm" :href="`/print/visits/${id}/bill`"><Icon name="print" />چاپ صورتحساب</a>
        <RouterLink v-if="can('finance')" class="btn btn-sm btn-ghost" :to="`/patients/${data.patient.code}/history`">سوابق درمان و مالی</RouterLink>
      </div>
    </div>
    <div v-if="notice" class="callout callout-info" role="status"><Icon name="check" /><span>{{ notice }}</span></div>
    <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>

    <section id="note" class="card" aria-labelledby="note-h">
      <div class="card-head"><div><h2 id="note-h">شرح پزشک</h2><p>آنچه پزشک درباره‌ی این ویزیت می‌نویسد.</p></div></div>
      <form v-if="can('visits', 2)" class="card-body stack" @submit.prevent="saveNote">
        <label class="sr-only" for="doc-note">شرح پزشک</label>
        <textarea id="doc-note" v-model="note" class="textarea" rows="5" maxlength="5000" placeholder="شرح معاینه، تشخیص و دستورها"></textarea>
        <div><button class="btn btn-primary" type="submit" :disabled="act.busy.value">ذخیره‌ی شرح</button></div>
      </form>
      <div v-else class="card-body"><div class="notes-box">{{ data.visit.doctorNote || 'شرحی ثبت نشده است.' }}</div></div>
    </section>

    <template v-if="data.bill">
      <section id="bill" class="card mt-6" aria-labelledby="bill-h">
        <div class="card-head">
          <div><h2 id="bill-h">صورتحساب</h2><p>{{ data.bill.cancelled ? 'ویزیت لغو شده است و صورتحساب بدهی ندارد.' : 'خدمات و کالاهای این ویزیت، با قیمت روز افزودن.' }}</p></div>
        </div>
        <div v-if="data.bill.lines.length" class="table-wrap">
          <table class="table bill-table">
            <thead><tr><th scope="col">شرح</th><th scope="col">تعداد</th><th scope="col">قیمت واحد</th><th scope="col">تخفیف</th><th scope="col">مبلغ</th><th v-if="can('finance', 2)" scope="col"><span class="sr-only">ویرایش</span></th></tr></thead>
            <tbody>
              <tr v-for="l in data.bill.lines" :key="l.id">
                <td data-label="شرح"><b>{{ l.name }}</b> <span class="chip chip-plain chip-mute">{{ l.kind === 'item' ? 'کالا' : 'خدمت' }}</span></td>
                <td data-label="تعداد">{{ l.qty.display }}</td>
                <td data-label="قیمت واحد"><span v-if="l.overridePrice" class="money money-strike">{{ l.unitPrice.display }}</span><span class="money">{{ (l.overridePrice ?? l.unitPrice).display }}</span></td>
                <td data-label="تخفیف"><template v-if="l.disc.rial"><span class="money">{{ l.disc.display }}</span><span v-if="l.discKind === 'percent'" class="muted"> ({{ fa(l.discValue) }}٪)</span></template><template v-else>—</template></td>
                <td data-label="مبلغ"><b><span class="money">{{ l.net.display }}</span></b></td>
                <td v-if="can('finance', 2)" data-label="ویرایش">
                  <details class="line-edit" :open="Boolean(fieldErr(`line${l.id}`))">
                    <summary class="btn btn-sm btn-ghost">ویرایش</summary>
                    <div v-if="lineEdit[l.id]" class="line-edit-body">
                      <p v-if="fieldErr(`line${l.id}`)" class="field-error" role="alert">{{ fieldErr(`line${l.id}`) }}</p>
                      <form class="inline-form" @submit.prevent="lineDisc(l.id)">
                        <select v-model="lineEdit[l.id].discKind" class="select select-sm" aria-label="نوع تخفیف"><option value="amount">مبلغ ({{ curName }})</option><option value="percent">درصد</option></select>
                        <MoneyInput v-model="lineEdit[l.id].discValue" placeholder="تخفیف" />
                        <button class="btn btn-sm" type="submit">ثبت تخفیف</button>
                      </form>
                      <template v-if="has('price_override')">
                        <form class="inline-form" @submit.prevent="linePrice(l.id)">
                          <MoneyInput v-model="lineEdit[l.id].price" :placeholder="`قیمت تازه (${curName})`" />
                          <button class="btn btn-sm" type="submit">تغییر قیمت</button>
                        </form>
                        <p class="hint">خالی گذاشتن قیمت، قیمت فهرست را برمی‌گرداند. تغییر قیمت فقط روی همین صورتحساب است و ثبت می‌شود.</p>
                      </template>
                      <button class="btn btn-sm btn-danger" type="button" @click="delLine(l.id)">حذف ردیف</button>
                    </div>
                  </details>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="card-body"><p class="muted">هنوز خدمت یا کالایی به این ویزیت اضافه نشده است.</p></div>
        <form v-if="can('finance', 2) && !data.bill.cancelled" class="card-body add-line" @submit.prevent="addLine">
          <div class="field grow">
            <label for="add-entry">خدمت یا کالا</label>
            <input id="add-entry" v-model="add.entry" class="input" type="search" list="entry-list" maxlength="120" autocomplete="off" placeholder="نام خدمت یا کالا را بنویسید…" required>
            <datalist id="entry-list">
              <option v-for="c in data.catalog" :key="c.id" :value="c.name" :label="`${c.kind === 'item' ? 'کالا' : 'خدمت'} · ${c.price.display}${c.kind === 'item' ? ' · موجود: ' + c.usable.display : ''}`"></option>
            </datalist>
          </div>
          <div class="field qty-field">
            <label for="add-qty">تعداد</label>
            <input id="add-qty" v-model="add.qty" class="input" type="text" inputmode="decimal" dir="ltr" required>
          </div>
          <button class="btn btn-add" type="submit" :disabled="act.busy.value"><Icon name="plus" />افزودن</button>
          <div v-if="fieldErr('line')" class="add-line-error info-box" role="alert">{{ fieldErr('line') }}</div>
        </form>
        <div class="card-body bill-foot">
          <form v-if="can('finance', 2) && !data.bill.cancelled" class="inline-form" @submit.prevent="saveBillDisc">
            <label for="bd-v">تخفیف کل صورتحساب</label>
            <select v-model="billDisc.discKind" class="select select-sm" aria-label="نوع تخفیف"><option value="amount">مبلغ ({{ curName }})</option><option value="percent">درصد</option></select>
            <MoneyInput id="bd-v" v-model="billDisc.discValue" placeholder="۰" />
            <button class="btn btn-sm" type="submit">ثبت</button>
            <p v-if="fieldErr('billDisc')" class="field-error" role="alert">{{ fieldErr('billDisc') }}</p>
          </form>
          <dl class="totals" aria-label="جمع صورتحساب">
            <div><dt>جمع کل</dt><dd><span class="money">{{ data.bill.gross.display }}</span></dd></div>
            <div><dt>تخفیف<span v-if="data.visit.discKind" class="muted"> (کل: {{ data.visit.discText }})</span></dt><dd><span class="money">{{ data.bill.discount.display }}</span></dd></div>
            <div class="totals-strong"><dt>قابل پرداخت</dt><dd><span class="money">{{ data.bill.owed.display }}</span></dd></div>
            <div><dt>پرداخت‌شده</dt><dd><span class="money">{{ data.bill.paid.display }}</span></dd></div>
            <div v-if="data.bill.credit.rial" class="totals-credit"><dt>بستانکار</dt><dd><span class="money">{{ data.bill.credit.display }}</span></dd></div>
            <div v-else class="totals-remaining" :class="{ 'is-zero': !data.bill.remaining.rial }"><dt>مانده</dt><dd><span class="money">{{ data.bill.remaining.display }}</span></dd></div>
          </dl>
        </div>
      </section>

      <section id="pay" class="card mt-6" aria-labelledby="pay-h">
        <div class="card-head"><div><h2 id="pay-h">پرداخت‌ها</h2><p>هر پرداخت در روز خودش درآمد حساب می‌شود.<template v-if="prepay"> پرداخت پیش از ویزیت، پیش‌پرداخت است.</template></p></div></div>
        <div v-if="data.bill.payments.length" class="table-wrap">
          <table class="table">
            <thead><tr><th scope="col">تاریخ</th><th scope="col">نوع</th><th scope="col">مبلغ</th><th scope="col">روش</th><th scope="col">حساب</th><th scope="col">ثبت‌کننده</th><th v-if="can('finance', 2)" scope="col"><span class="sr-only">اقدام</span></th></tr></thead>
            <tbody>
              <tr v-for="p in data.bill.payments" :key="p.id">
                <td data-label="تاریخ">{{ p.paidOn.short }}</td>
                <td data-label="نوع">{{ KIND[p.kind] }}<span v-if="p.kind === 'payment' && p.paidOn.iso < data.visit.date.iso" class="chip chip-info chip-plain"> پیش‌پرداخت</span><span v-if="p.otherDate" class="muted"> ({{ p.otherDate.short }})</span></td>
                <td data-label="مبلغ"><b :class="{ 'qty-out': p.amount.rial < 0 }"><span class="money">{{ p.amount.display }}</span></b></td>
                <td data-label="روش">{{ p.method || '—' }}</td>
                <td data-label="حساب">{{ p.account || '—' }}</td>
                <td data-label="ثبت‌کننده">{{ p.who || '—' }}</td>
                <td v-if="can('finance', 2)" data-label="اقدام"><div class="user-actions">
                  <button v-if="!p.moveId" class="btn btn-sm btn-ghost" type="button" @click="startEdit(p.id)">ویرایش</button>
                  <ConfirmDelete :question="p.moveId ? 'این انتقال (هر دو طرف) حذف شود؟' : 'این پرداخت حذف شود؟'" @confirm="delPay(p.id)" />
                </div></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="card-body"><p class="muted">هنوز پرداختی ثبت نشده است.</p></div>

        <form v-if="can('finance', 2) && editing" class="card-body form-grid form-grid-3 pay-form pay-edit" @submit.prevent="saveEdit">
          <h3 class="span-all">ویرایش {{ KIND[editing.kind] }}</h3>
          <div v-if="fieldErr('edit')" class="info-box span-all" role="alert">{{ fieldErr('edit') }}</div>
          <div class="field"><label for="pe-amount">مبلغ ({{ curName }})</label><MoneyInput id="pe-amount" v-model="editing.amount" required /></div>
          <div class="field"><label for="pe-date">تاریخ</label><JalaliInput id="pe-date" v-model="editing.paidOn" /></div>
          <div class="field"><label for="pe-method">روش پرداخت</label><select id="pe-method" v-model="editing.methodId" class="select"><option v-for="m in data.methods" :key="m.id" :value="String(m.id)">{{ m.name }}</option></select></div>
          <div class="field"><label for="pe-account">حساب</label><select id="pe-account" v-model="editing.accountId" class="select"><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select></div>
          <div class="field span-2"><label for="pe-note">یادداشت</label><input id="pe-note" v-model="editing.note" class="input" type="text" maxlength="200"></div>
          <div class="form-actions span-all"><button class="btn btn-primary" type="submit">ذخیره‌ی تغییر</button><button class="btn btn-ghost" type="button" @click="editing = null">انصراف</button></div>
        </form>
        <form v-else-if="can('finance', 2) && !data.bill.cancelled" class="card-body form-grid form-grid-3 pay-form" @submit.prevent="addPay(false)">
          <h3 class="span-all">ثبت پرداخت <span v-if="prepay" class="chip chip-info chip-plain">پیش‌پرداخت</span></h3>
          <div v-if="fieldErr('pay')" class="info-box span-all" role="alert">{{ fieldErr('pay') }}</div>
          <div class="field"><label for="p-amount">مبلغ ({{ curName }})</label><MoneyInput id="p-amount" v-model="pay.amount" required /></div>
          <div class="field"><label for="p-date">تاریخ</label><JalaliInput id="p-date" v-model="pay.paidOn" /></div>
          <div class="field"><label for="p-method">روش پرداخت</label><select id="p-method" v-model="pay.methodId" class="select" required><option v-for="m in data.methods" :key="m.id" :value="String(m.id)">{{ m.name }}</option></select></div>
          <div class="field"><label for="p-account">حساب</label><select id="p-account" v-model="pay.accountId" class="select"><option value="">حساب پیش‌فرض روش پرداخت</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select></div>
          <div class="field span-2"><label for="p-note">یادداشت (اختیاری)</label><input id="p-note" v-model="pay.note" class="input" type="text" maxlength="200"></div>
          <div class="form-actions span-all">
            <button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="check" />ثبت پرداخت</button>
            <button v-if="data.bill.remaining.rial" class="btn" type="button" :disabled="act.busy.value" @click="addPay(true)">پرداخت کامل ({{ data.bill.remaining.display }})</button>
          </div>
        </form>

        <div v-if="can('finance', 2) && data.bill.credit.rial && !editing" class="card-body credit-box">
          <div class="callout callout-info"><Icon name="alert" /><span>این ویزیت <b><span class="money">{{ data.bill.credit.display }}</span></b> بستانکار دارد. آن را به بیمار برگردانید یا به ویزیت دیگری از همین بیمار منتقل کنید.</span></div>
          <div class="credit-forms">
            <form class="stack" @submit.prevent="doRefund">
              <h3>بازپرداخت به بیمار</h3>
              <p v-if="fieldErr('refund')" class="field-error" role="alert">{{ fieldErr('refund') }}</p>
              <div class="field"><label for="r-amount">مبلغ ({{ curName }})</label><MoneyInput id="r-amount" v-model="refund.amount" required /></div>
              <div class="field"><label for="r-method">روش</label><select id="r-method" v-model="refund.methodId" class="select"><option v-for="m in data.methods" :key="m.id" :value="String(m.id)">{{ m.name }}</option></select></div>
              <div class="field"><label for="r-account">از حساب</label><select id="r-account" v-model="refund.accountId" class="select"><option value="">حساب پیش‌فرض روش</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select></div>
              <div><button class="btn btn-danger" type="submit" :disabled="act.busy.value">ثبت بازپرداخت</button></div>
            </form>
            <form v-if="data.targets.length" class="stack" @submit.prevent="doMove">
              <h3>انتقال به ویزیت دیگر</h3>
              <p v-if="fieldErr('move')" class="field-error" role="alert">{{ fieldErr('move') }}</p>
              <div class="field"><label for="m-to">ویزیت مقصد</label><select id="m-to" v-model="move.to" class="select" required><option v-for="t in data.targets" :key="t.id" :value="String(t.id)">{{ t.date.short }} · {{ fa(t.time) }}</option></select></div>
              <div class="field"><label for="m-amount">مبلغ ({{ curName }})</label><MoneyInput id="m-amount" v-model="move.amount" required /></div>
              <div><button class="btn" type="submit" :disabled="act.busy.value">انتقال اعتبار</button></div>
            </form>
          </div>
        </div>
      </section>
    </template>
  </template>
</template>
