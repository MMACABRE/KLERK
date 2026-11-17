<script setup lang="ts">
// New stock item (legacy views/storage/new.ejs): a catalog entry counted in pieces.
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import MoneyInput from '../../components/MoneyInput.vue';
import { api } from '../../api/client';
import { session, setTitle } from '../../lib/session';
import { useAction } from '../../lib/usePage';

setTitle('کالای جدید');
const router = useRouter();
const form = ref({ name: '', salePrice: '', purchaseCost: '', lowWarn: '', lowCrit: '' });
const { busy, error, fields, run } = useAction();
const curName = session.me?.currency === 'R' ? 'ریال' : 'تومان';
async function save() {
  const out = await run(() => api.post('/storage/items', form.value));
  if (out) router.push(`/storage/items/${out.id}`);
}
</script>

<template>
  <div class="breadcrumb"><RouterLink to="/storage">انبار</RouterLink> / کالای جدید</div>
  <div class="page-head"><div><h1>کالای جدید</h1><p>کالا به تعداد شمرده می‌شود (هر عدد، نه هر جعبه). موجودی را بعد از ساخت، با «ورود کالا» اضافه کنید.</p></div></div>
  <section class="card">
    <form class="card-body form-grid" @submit.prevent="save">
      <div v-if="error" class="info-box span-2" role="alert">{{ error }}</div>
      <div class="field span-2"><label for="n-name">نام کالا</label><input id="n-name" v-model="form.name" class="input" type="text" maxlength="120" required><p v-if="fields.name" class="field-error" role="alert">{{ fields.name }}</p></div>
      <div class="field"><label for="n-sale">قیمت فروش هر عدد ({{ curName }})</label><MoneyInput id="n-sale" v-model="form.salePrice" required /><span class="hint">مبلغی که روی صورتحساب بیمار می‌آید</span><p v-if="fields.salePrice" class="field-error" role="alert">{{ fields.salePrice }}</p></div>
      <div class="field"><label for="n-cost">قیمت خرید هر عدد (اختیاری)</label><MoneyInput id="n-cost" v-model="form.purchaseCost" /><span class="hint">فقط برای گزارش؛ هرگز از بیمار گرفته نمی‌شود</span><p v-if="fields.purchaseCost" class="field-error" role="alert">{{ fields.purchaseCost }}</p></div>
      <div class="field"><label for="n-warn">حد هشدار موجودی (اختیاری)</label><input id="n-warn" v-model="form.lowWarn" class="input" type="text" inputmode="decimal" dir="ltr"><span class="hint">خالی یعنی حد پیش‌فرض</span><p v-if="fields.lowWarn" class="field-error" role="alert">{{ fields.lowWarn }}</p></div>
      <div class="field"><label for="n-crit">حد بحرانی موجودی (اختیاری)</label><input id="n-crit" v-model="form.lowCrit" class="input" type="text" inputmode="decimal" dir="ltr"><span class="hint">خالی یعنی حد پیش‌فرض</span><p v-if="fields.lowCrit" class="field-error" role="alert">{{ fields.lowCrit }}</p></div>
      <div class="form-actions span-2">
        <button class="btn btn-primary" type="submit" :disabled="busy">ساخت کالا</button>
        <RouterLink class="btn btn-ghost" to="/storage">انصراف</RouterLink>
      </div>
    </form>
  </section>
</template>
