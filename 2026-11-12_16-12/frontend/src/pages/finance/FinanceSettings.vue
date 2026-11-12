<script setup lang="ts">
// Finance settings (legacy views/finance/settings.ejs): currency, letterhead, stock alert defaults, catalog, payment
// methods and clinic accounts. A used row can only be deactivated.
import { ref } from 'vue';
import Icon from '../../components/Icon.vue';
import FinanceNav from '../../components/FinanceNav.vue';
import MoneyInput from '../../components/MoneyInput.vue';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import { api } from '../../api/client';
import { refreshMe, session, setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('تنظیمات مالی');
const general = ref<any>({});
const rows = ref<Record<number, any>>({});
const methods = ref<Record<number, any>>({});
const accounts = ref<Record<number, any>>({});
const entry = ref({ kind: 'service', name: '', salePrice: '', purchaseCost: '' });
const newMethod = ref({ name: '', defaultAccount: '' });
const newAccount = ref({ name: '' });
const act = useAction();
const curName = () => (session.me?.currency === 'R' ? 'ریال' : 'تومان');
const sample = (cur: string) => (cur === 'R' ? '12,500,000 R' : '1,250,000 T');

const { data, error, load } = useLoad(async () => {
  const d = await api.get('/finance/settings');
  const s = d.settings;
  general.value = { currency: s.currency, clinicName: s.clinicName, clinicPhone: s.clinicPhone, clinicAddress: s.clinicAddress, lowWarn: s.lowWarn.text, lowCrit: s.lowCrit.text };
  for (const c of d.catalog) rows.value[c.id] = { name: c.name, salePrice: c.salePrice.input === '0' ? '0' : c.salePrice.input, active: c.active };
  for (const m of d.methods) methods.value[m.id] = { name: m.name, defaultAccount: String(m.defaultAccount ?? ''), active: m.active };
  for (const a of d.accounts) accounts.value[a.id] = { name: a.name, active: a.active };
  return d;
});

async function doing(fn: () => Promise<unknown>, ok: string) {
  if ((await act.run(fn, ok)) !== undefined) { await load(); await refreshMe(); }
}
const saveGeneral = () => doing(() => api.put('/finance/settings', general.value), 'تنظیمات ذخیره شد.');
const saveRow = (id: number) => doing(() => api.patch(`/finance/catalog/${id}`, rows.value[id]), 'تنظیمات ذخیره شد.');
const delRow = (id: number) => doing(() => api.del(`/finance/catalog/${id}`), 'حذف شد.');
async function addEntry() {
  await doing(() => api.post('/finance/catalog', entry.value), 'اضافه شد.');
  if (!act.error.value) entry.value = { kind: 'service', name: '', salePrice: '', purchaseCost: '' };
}
const saveMethod = (id: number) => doing(() => api.patch(`/finance/methods/${id}`, methods.value[id]), 'تنظیمات ذخیره شد.');
const delMethod = (id: number) => doing(() => api.del(`/finance/methods/${id}`), 'حذف شد.');
async function addMethod() { await doing(() => api.post('/finance/methods', newMethod.value), 'اضافه شد.'); if (!act.error.value) newMethod.value = { name: '', defaultAccount: '' }; }
const saveAccount = (id: number) => doing(() => api.patch(`/finance/accounts/${id}`, accounts.value[id]), 'تنظیمات ذخیره شد.');
const delAccount = (id: number) => doing(() => api.del(`/finance/accounts/${id}`), 'حذف شد.');
async function addAccount() { await doing(() => api.post('/finance/accounts', newAccount.value), 'اضافه شد.'); if (!act.error.value) newAccount.value = { name: '' }; }
const ferr = (k: string) => act.fields.value[k];
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/finance">امور مالی</RouterLink> / تنظیمات</div><h1>تنظیمات و قیمت‌ها</h1>
    <p>تغییر قیمت فقط روی ردیف‌های تازه اثر دارد؛ صورتحساب‌های قبلی با قیمت روز خودشان می‌مانند. موردی که به کار رفته حذف نمی‌شود و فقط غیرفعال می‌شود.</p></div></div>
  <FinanceNav here="settings" />
  <div v-if="act.notice.value" class="callout callout-info" role="status"><Icon name="check" /><span>{{ act.notice.value }}</span></div>
  <p v-if="error || act.error.value" class="info-box" role="alert">{{ error || act.error.value }}</p>
  <template v-if="data">
    <section class="card" aria-labelledby="gen-h">
      <div class="card-head"><h2 id="gen-h">تنظیمات کلی</h2></div>
      <form class="card-body form-grid" @submit.prevent="saveGeneral">
        <fieldset class="field span-2 currency-field">
          <legend class="label">واحد نمایش مبالغ در همه‌ی سامانه</legend>
          <div class="levels">
            <label class="level"><input v-model="general.currency" type="radio" value="T"><span>تومان (T)</span></label>
            <label class="level"><input v-model="general.currency" type="radio" value="R"><span>ریال (R)</span></label>
          </div>
          <span class="hint">مبالغ همیشه به ریال ذخیره می‌شوند؛ این گزینه فقط نمایش و ورود مبلغ را عوض می‌کند. نمونه: <span class="money">{{ sample(general.currency) }}</span></span>
        </fieldset>
        <div class="field"><label for="s-name">نام کلینیک (نام سایت و سربرگ فرم‌های چاپی)</label><input id="s-name" v-model="general.clinicName" class="input" type="text" maxlength="120" required><p v-if="ferr('clinicName')" class="field-error" role="alert">{{ ferr('clinicName') }}</p></div>
        <div class="field"><label for="s-phone">تلفن</label><input id="s-phone" v-model="general.clinicPhone" class="input" type="text" maxlength="60" dir="ltr"></div>
        <div class="field span-2"><label for="s-addr">نشانی</label><input id="s-addr" v-model="general.clinicAddress" class="input" type="text" maxlength="300"></div>
        <div class="field"><label for="s-warn">حد هشدار موجودی (پیش‌فرض)</label><input id="s-warn" v-model="general.lowWarn" class="input" type="text" inputmode="decimal" dir="ltr"><p v-if="ferr('lowWarn')" class="field-error" role="alert">{{ ferr('lowWarn') }}</p></div>
        <div class="field"><label for="s-crit">حد بحرانی موجودی (پیش‌فرض)</label><input id="s-crit" v-model="general.lowCrit" class="input" type="text" inputmode="decimal" dir="ltr"><p v-if="ferr('lowCrit')" class="field-error" role="alert">{{ ferr('lowCrit') }}</p></div>
        <div class="form-actions span-2"><button class="btn btn-primary" type="submit" :disabled="act.busy.value">ذخیره‌ی تنظیمات</button></div>
      </form>
    </section>

    <section id="catalog" class="card mt-6" aria-labelledby="cat-h">
      <div class="card-head"><div><h2 id="cat-h">فهرست قیمت‌ها</h2><p>خدمات (مثل ویزیت و عمل) و کالاهای انبار با قیمت فروش. مبالغ به {{ curName() }}.</p></div></div>
      <div v-if="ferr('catalog')" class="card-body"><p class="field-error" role="alert">{{ ferr('catalog') }}</p></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">نوع</th><th scope="col">نام و قیمت فروش</th><th scope="col"><span class="sr-only">حذف</span></th></tr></thead>
          <tbody>
            <tr v-for="c in data.catalog" :key="c.id" :class="{ 'row-mute': !c.active }">
              <td data-label="نوع"><span class="chip chip-plain" :class="c.kind === 'item' ? 'chip-info' : 'chip-mute'">{{ c.kind === 'item' ? 'کالا' : 'خدمت' }}</span><span v-if="c.fixed" class="chip chip-plain chip-ok"> ثابت</span></td>
              <td data-label="نام و قیمت">
                <form class="inline-form" @submit.prevent="saveRow(c.id)">
                  <label class="sr-only" :for="`cn-${c.id}`">نام</label><input :id="`cn-${c.id}`" v-model="rows[c.id].name" class="input" type="text" maxlength="120" required>
                  <label class="sr-only" :for="`cp-${c.id}`">قیمت فروش</label><MoneyInput :id="`cp-${c.id}`" v-model="rows[c.id].salePrice" required />
                  <label class="check"><input v-model="rows[c.id].active" type="checkbox"><span>فعال</span></label>
                  <button class="btn btn-sm" type="submit">ذخیره</button>
                  <RouterLink v-if="c.kind === 'item'" class="btn btn-sm btn-ghost" :to="`/storage/items/${c.id}`">انبار</RouterLink>
                </form>
                <p v-if="ferr(`c${c.id}`)" class="field-error" role="alert">{{ ferr(`c${c.id}`) }}</p>
              </td>
              <td data-label="حذف"><ConfirmDelete v-if="!c.used" :question="`«${c.name}» از فهرست حذف شود؟`" @confirm="delRow(c.id)" /><span v-else class="text-xs-muted">به کار رفته</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <form class="card-body form-grid form-grid-3 add-entry" @submit.prevent="addEntry">
        <h3 class="span-all">افزودن به فهرست</h3>
        <div class="field"><label for="ne-kind">نوع</label><select id="ne-kind" v-model="entry.kind" class="select"><option value="service">خدمت</option><option value="item">کالای انبار</option></select></div>
        <div class="field"><label for="ne-name">نام</label><input id="ne-name" v-model="entry.name" class="input" type="text" maxlength="120" required></div>
        <div class="field"><label for="ne-price">قیمت فروش ({{ curName() }})</label><MoneyInput id="ne-price" v-model="entry.salePrice" required /></div>
        <div class="field"><label for="ne-cost">قیمت خرید (فقط کالا، اختیاری)</label><MoneyInput id="ne-cost" v-model="entry.purchaseCost" /></div>
        <div class="form-actions span-all"><button class="btn btn-primary" type="submit"><Icon name="plus" />افزودن</button></div>
      </form>
    </section>

    <div class="grid grid-2 mt-6 lists-grid">
      <section id="methods" class="card" aria-labelledby="met-h">
        <div class="card-head"><div><h2 id="met-h">روش‌های پرداخت</h2><p>هر روش می‌تواند حساب پیش‌فرض داشته باشد.</p></div></div>
        <div v-if="ferr('method')" class="card-body"><p class="field-error" role="alert">{{ ferr('method') }}</p></div>
        <ul class="edit-list">
          <li v-for="m in data.methods" :key="m.id" :class="{ 'row-mute': !m.active }">
            <form class="inline-form" @submit.prevent="saveMethod(m.id)">
              <label class="sr-only" :for="`mn-${m.id}`">نام روش</label><input :id="`mn-${m.id}`" v-model="methods[m.id].name" class="input" type="text" maxlength="80" required>
              <select v-model="methods[m.id].defaultAccount" class="select select-sm" aria-label="حساب پیش‌فرض"><option value="">بدون پیش‌فرض</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select>
              <label class="check"><input v-model="methods[m.id].active" type="checkbox"><span>فعال</span></label>
              <button class="btn btn-sm" type="submit">ذخیره</button>
            </form>
            <ConfirmDelete v-if="!m.used" :question="`روش «${m.name}» حذف شود؟`" @confirm="delMethod(m.id)" />
          </li>
        </ul>
        <form class="card-body inline-form" @submit.prevent="addMethod">
          <label class="sr-only" for="nm">نام روش تازه</label><input id="nm" v-model="newMethod.name" class="input" type="text" maxlength="80" placeholder="روش تازه، مثلاً «چک»" required>
          <select v-model="newMethod.defaultAccount" class="select select-sm" aria-label="حساب پیش‌فرض"><option value="">بدون پیش‌فرض</option><option v-for="a in data.accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option></select>
          <button class="btn btn-sm btn-primary" type="submit">افزودن</button>
        </form>
      </section>
      <section id="accounts" class="card" aria-labelledby="acc-h">
        <div class="card-head"><div><h2 id="acc-h">حساب‌های کلینیک</h2><p>جایی که پول می‌رود: صندوق یا حساب بانکی.</p></div></div>
        <div v-if="ferr('account')" class="card-body"><p class="field-error" role="alert">{{ ferr('account') }}</p></div>
        <ul class="edit-list">
          <li v-for="a in data.accounts" :key="a.id" :class="{ 'row-mute': !a.active }">
            <form class="inline-form" @submit.prevent="saveAccount(a.id)">
              <label class="sr-only" :for="`an-${a.id}`">نام حساب</label><input :id="`an-${a.id}`" v-model="accounts[a.id].name" class="input" type="text" maxlength="80" required>
              <label class="check"><input v-model="accounts[a.id].active" type="checkbox"><span>فعال</span></label>
              <button class="btn btn-sm" type="submit">ذخیره</button>
            </form>
            <ConfirmDelete v-if="!a.used" :question="`حساب «${a.name}» حذف شود؟`" @confirm="delAccount(a.id)" />
          </li>
        </ul>
        <form class="card-body inline-form" @submit.prevent="addAccount">
          <label class="sr-only" for="na">نام حساب تازه</label><input id="na" v-model="newAccount.name" class="input" type="text" maxlength="80" placeholder="حساب تازه، مثلاً «بانک ملت»" required>
          <button class="btn btn-sm btn-primary" type="submit">افزودن</button>
        </form>
      </section>
    </div>
  </template>
</template>
