<script setup lang="ts">
// One stock item (legacy views/storage/item.ejs): stock-in, lots with count/waste, history with undo, delete item.
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import MoneyInput from '../../components/MoneyInput.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import { api, ApiError } from '../../api/client';
import { can, has, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const router = useRouter();
const id = String(route.params.id);
const EXP: Record<string, [string, string]> = { expired: ['chip-crit', 'منقضی شده'], crit: ['chip-crit', 'کمتر از ۱۰ روز'], warn: ['chip-warn', 'کمتر از ۳۰ روز'] };
const REASON: Record<string, string> = { in: 'ورود کالا', use: 'مصرف در ویزیت', return: 'برگشت از صورتحساب', count: 'اصلاح شمارش', waste: 'ضایعات' };
const stockIn = ref({ qty: '', expiresOn: '', unitCost: '' });
const lotForms = ref<Record<number, any>>({});
const rowError = ref<Record<string, string>>({});
const notice = ref('');
const act = useAction();
const { data, error, load } = useLoad(async () => {
  const d = await api.get(`/storage/items/${id}`);
  setTitle(d.item.name);
  for (const l of d.lots) {
    lotForms.value[l.id] = { counted: '', note: '', qty: l.level === 'expired' ? l.remaining.text : '', wnote: l.level === 'expired' ? 'منقضی شده' : '' };
  }
  return d;
});

async function doRow(key: string, fn: () => Promise<unknown>) {
  rowError.value = {};
  notice.value = '';
  try { await fn(); notice.value = 'ثبت شد.'; await load(); } catch (e) { rowError.value = { [key]: e instanceof ApiError ? e.message : 'خطایی رخ داد.' }; }
}
async function addIn() {
  const out = await act.run(() => api.post(`/storage/items/${id}/stock-in`, stockIn.value));
  if (out) { stockIn.value = { qty: '', expiresOn: '', unitCost: '' }; notice.value = 'ثبت شد.'; load(); }
}
const count = (lid: number) => doRow(`lot${lid}`, () => api.post(`/storage/lots/${lid}/count`, { counted: lotForms.value[lid].counted, note: lotForms.value[lid].note }));
const waste = (lid: number) => doRow(`lot${lid}`, () => api.post(`/storage/lots/${lid}/waste`, { qty: lotForms.value[lid].qty, note: lotForms.value[lid].wnote }));
const undo = (mid: number) => doRow(`move${mid}`, () => api.del(`/storage/moves/${mid}`));
async function remove() {
  if (await act.run(() => api.del(`/storage/items/${id}`))) router.push({ path: '/storage', query: { ok: 'removed' } });
}
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="breadcrumb"><RouterLink to="/storage">انبار</RouterLink> / {{ data.item.name }}</div>
    <div class="page-head">
      <div>
        <h1>{{ data.item.name }} <span v-if="!data.item.active" class="chip chip-mute">غیرفعال</span></h1>
        <p><template v-if="data.item.salePrice">قیمت فروش <span class="money">{{ data.item.salePrice.display }}</span></template><template v-if="data.item.purchaseCost"> · قیمت خرید <span class="money">{{ data.item.purchaseCost.display }}</span></template>
          · حد هشدار {{ (data.item.lowWarn ?? data.settings.lowWarn).display }} و بحرانی {{ (data.item.lowCrit ?? data.settings.lowCrit).display }} عدد</p>
      </div>
      <div class="stock-total"><span>موجود قابل مصرف</span><b>{{ data.usable.display }}</b><small>عدد</small></div>
    </div>
    <div v-if="has('stock_adjust') && has('finance_settings')" class="page-actions mb-4">
      <ConfirmDelete label="حذف کالا" :question="`«${data.item.name}» با همه‌ی بسته‌ها و گردش کالا حذف شود؟ این کار برنمی‌گردد. صورتحساب ویزیت‌هایی که این کالا را داشته‌اند تغییر نمی‌کند.`" @confirm="remove" />
    </div>
    <div v-if="notice" class="callout callout-info" role="status"><Icon name="check" /><span>{{ notice }}</span></div>
    <p v-if="act.error.value && !Object.keys(act.fields.value).length" class="info-box" role="alert">{{ act.error.value }}</p>

    <section v-if="can('storage', 2)" class="card" aria-labelledby="in-h">
      <div class="card-head"><div><h2 id="in-h">ورود کالا</h2><p>هر ورود یک بسته با تاریخ انقضای خودش می‌سازد.</p></div></div>
      <form class="card-body form-grid form-grid-3" @submit.prevent="addIn">
        <div class="field"><label for="in-qty">تعداد (عدد)</label><input id="in-qty" v-model="stockIn.qty" class="input" type="text" inputmode="decimal" dir="ltr" required><p v-if="act.fields.value.qty" class="field-error" role="alert">{{ act.fields.value.qty }}</p></div>
        <div class="field"><label for="in-exp">تاریخ انقضا (اختیاری)</label><JalaliInput id="in-exp" v-model="stockIn.expiresOn" placeholder="۱۴۰۵/۰۸/۱۵" /><p v-if="act.fields.value.expiresOn" class="field-error" role="alert">{{ act.fields.value.expiresOn }}</p></div>
        <div class="field"><label for="in-cost">قیمت خرید هر عدد (اختیاری)</label><MoneyInput id="in-cost" v-model="stockIn.unitCost" /><p v-if="act.fields.value.unitCost" class="field-error" role="alert">{{ act.fields.value.unitCost }}</p></div>
        <div class="form-actions span-all"><button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="plus" />ثبت ورود</button></div>
      </form>
    </section>

    <section class="card mt-6" aria-labelledby="lots-h">
      <div class="card-head"><div><h2 id="lots-h">بسته‌ها</h2><p>به ترتیب مصرف: زودتر منقضی‌شونده بالاتر است.</p></div></div>
      <div v-if="!data.lots.length" class="card-body"><p class="muted">هنوز ورودی ثبت نشده است.</p></div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">تاریخ ورود</th><th scope="col">انقضا</th><th scope="col">ورودی</th><th scope="col">مانده</th><th scope="col">قیمت خرید</th><th v-if="has('stock_adjust')" scope="col"><span class="sr-only">اصلاح</span></th></tr></thead>
          <tbody>
            <tr v-for="l in data.lots" :key="l.id" :class="{ 'row-mute': l.remaining.value === '0.00' }">
              <td data-label="تاریخ ورود">{{ l.receivedOn.short }}</td>
              <td data-label="انقضا">{{ l.expiresOn?.short ?? 'ندارد' }} <span v-if="l.level" class="chip" :class="EXP[l.level][0]">{{ EXP[l.level][1] }}</span></td>
              <td data-label="ورودی">{{ l.qtyIn.display }}</td>
              <td data-label="مانده"><b>{{ l.remaining.display }}</b></td>
              <td data-label="قیمت خرید"><span v-if="l.unitCost" class="money">{{ l.unitCost.display }}</span><template v-else>—</template></td>
              <td v-if="has('stock_adjust')" data-label="اصلاح">
                <details class="lot-fix" :open="Boolean(rowError[`lot${l.id}`])">
                  <summary class="btn btn-sm btn-ghost">اصلاح</summary>
                  <div class="lot-fix-body">
                    <p v-if="rowError[`lot${l.id}`]" class="field-error" role="alert">{{ rowError[`lot${l.id}`] }}</p>
                    <form class="lot-form" @submit.prevent="count(l.id)">
                      <input v-model="lotForms[l.id].counted" class="input" type="text" inputmode="decimal" dir="ltr" placeholder="شمارش واقعی" aria-label="تعداد شمارش‌شده" required>
                      <input v-model="lotForms[l.id].note" class="input" type="text" maxlength="200" placeholder="دلیل" aria-label="دلیل" required>
                      <button class="btn btn-sm" type="submit">ثبت شمارش</button>
                    </form>
                    <form v-if="l.remaining.value !== '0.00'" class="lot-form" @submit.prevent="waste(l.id)">
                      <input v-model="lotForms[l.id].qty" class="input" type="text" inputmode="decimal" dir="ltr" placeholder="تعداد" aria-label="تعداد ضایعات" required>
                      <input v-model="lotForms[l.id].wnote" class="input" type="text" maxlength="200" placeholder="دلیل" aria-label="دلیل" required>
                      <button class="btn btn-sm btn-danger" type="submit">ثبت ضایعات</button>
                    </form>
                  </div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card mt-6" aria-labelledby="moves-h">
      <div class="card-head"><div><h2 id="moves-h">گردش کالا</h2><p>۵۰ رویداد آخر</p></div></div>
      <div v-if="!data.moves.length" class="card-body"><p class="muted">گردشی ثبت نشده است.</p></div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">زمان</th><th scope="col">نوع</th><th scope="col">تعداد</th><th scope="col">توضیح</th><th scope="col">کاربر</th><th v-if="has('stock_adjust')" scope="col"><span class="sr-only">حذف</span></th></tr></thead>
          <tbody>
            <tr v-for="m in data.moves" :key="m.id">
              <td data-label="زمان">{{ m.ts.text }}</td>
              <td data-label="نوع">{{ REASON[m.reason] }}</td>
              <td data-label="تعداد"><span class="qty" :class="m.qty.value.startsWith('-') ? 'qty-out' : 'qty-in'">{{ m.qty.value.startsWith('-') ? '−' : '+' }}{{ fa(m.qty.text.replace('-', '')) }}</span></td>
              <td data-label="توضیح">{{ m.note || '—' }}</td>
              <td data-label="کاربر">{{ m.who || '—' }}</td>
              <td v-if="has('stock_adjust')" data-label="حذف">
                <span v-if="m.reason === 'use' || m.reason === 'return'" class="muted">از صورتحساب ویزیت</span>
                <details v-else class="lot-fix" :open="Boolean(rowError[`move${m.id}`])">
                  <summary class="btn btn-sm btn-ghost">حذف</summary>
                  <div class="lot-fix-body">
                    <p v-if="rowError[`move${m.id}`]" class="field-error" role="alert">{{ rowError[`move${m.id}`] }}</p>
                    <p>{{ m.reason === 'in' ? 'این ورود و بسته‌ی آن حذف شود؟' : 'این ردیف حذف شود و موجودی بسته به حالت قبل برگردد؟' }}</p>
                    <form class="lot-form" @submit.prevent="undo(m.id)"><button class="btn btn-sm btn-danger" type="submit">بله، حذف شود</button></form>
                  </div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>
</template>
