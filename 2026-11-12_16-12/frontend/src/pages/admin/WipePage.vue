<script setup lang="ts">
// «حذف داده‌ها» (legacy views/admin/wipe.ejs): the word «حذف», the user's password, a backup first.
import { ref } from 'vue';
import Icon from '../../components/Icon.vue';
import PasswordInput from '../../components/PasswordInput.vue';
import { api } from '../../api/client';
import { refreshMe, setTitle } from '../../lib/session';
import { faCount } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('حذف داده‌ها');
const KIND: Record<string, [string, string]> = {
  patients: ['بیماران و پرونده‌ها', 'همه‌ی بیماران با ویزیت‌ها، داروها، مدارک، عکس‌ها، پیامک‌ها و همه‌ی صورتحساب‌ها و پرداخت‌هایشان. مدارک و امور مالی هم با این گزینه حذف می‌شوند.'],
  documents: ['مدارک و تصاویر', 'همه‌ی مدارک پزشکی و عکس‌های بیماران. خود پرونده‌ها می‌مانند.'],
  finance: ['امور مالی', 'همه‌ی پرداخت‌ها، بازپرداخت‌ها و انتقال‌های اعتبار، و همه‌ی خدمات و کالاهای ثبت‌شده در صورتحساب‌ها با تخفیف‌هایشان. خود ویزیت‌ها، حساب‌ها، روش‌های پرداخت و فهرست قیمت خدمات می‌مانند.'],
  storage: ['انبار', 'همه‌ی بسته‌ها، شمارش‌ها و گردش کالا، و کالاهایی که در هیچ صورتحسابی نیامده‌اند. کالایی که در صورتحساب آمده با موجودی صفر در فهرست می‌ماند.'],
};
const COUNT: Record<string, (c: any) => string> = {
  patients: (c) => `${faCount(c.patients)} بیمار، ${faCount(c.visits)} ویزیت`,
  documents: (c) => `${faCount(c.documents)} مدرک، ${faCount(c.photos)} عکس`,
  finance: (c) => `${faCount(c.payments)} پرداخت، ${faCount(c.lines)} ردیف صورتحساب`,
  storage: (c) => `${faCount(c.lots)} بسته، ${faCount(c.moves)} ردیف گردش، از ${faCount(c.items)} کالا`,
};
const kinds = ref<string[]>([]);
const confirm = ref('');
const password = ref('');
const result = ref<any>(null);
const act = useAction();
const { data, load } = useLoad(() => api.get('/admin/wipe'));
async function wipe() {
  result.value = null;
  const out = await act.run(() => api.post('/admin/wipe', { kinds: kinds.value, confirm: confirm.value, password: password.value }));
  if (out) { result.value = out; kinds.value = []; confirm.value = ''; password.value = ''; load(); refreshMe(); }
}
</script>

<template>
  <div class="breadcrumb"><RouterLink to="/admin/users">مدیریت کاربران</RouterLink> / حذف داده‌ها</div>
  <div class="page-head"><div><h1>حذف داده‌ها</h1><p>یک یا چند دسته از داده‌های سایت را یک‌جا پاک کنید. کاربران، دسترسی‌ها، تنظیمات و گزارش فعالیت هرگز پاک نمی‌شوند.</p></div></div>
  <template v-if="result">
    <div class="callout callout-info" role="status"><Icon name="check" />
      <span>حذف شد: {{ result.kinds.map((k: string) => KIND[k][0]).join('، ') }}.
        نسخه‌ی پشتیبان پیش از حذف در پوشه‌ی <span class="mono">data/backups</span> روی سرور با نام <span class="mono">{{ result.backup }}</span> ذخیره شد<template v-if="result.trashed"> و پوشه‌ی فایل‌های بیماران به <span class="mono">data/trash/{{ result.trashed }}</span> منتقل شد</template>؛ مدیر سرور می‌تواند آن‌ها را برگرداند.</span>
    </div>
    <div v-if="result.fileError" class="callout callout-crit" role="alert"><Icon name="alert" /><span>ردیف‌ها حذف شدند، اما پوشه‌ی فایل‌های بیماران جابه‌جا نشد. از مدیر سرور بخواهید پوشه‌ی <span class="mono">data/patients</span> را بررسی کند.</span></div>
  </template>
  <div v-if="act.error.value" class="callout callout-crit" role="alert"><Icon name="alert" /><span>{{ act.error.value }}</span></div>
  <section v-if="data" class="card" aria-labelledby="wipe-h">
    <form class="card-body form-section" @submit.prevent="wipe">
      <h2 id="wipe-h">چه چیزی حذف شود؟</h2>
      <fieldset class="wipe-kinds">
        <legend class="sr-only">دسته‌های داده</legend>
        <label v-for="k in data.kinds" :key="k" class="check wipe-kind">
          <input v-model="kinds" type="checkbox" :value="k">
          <span><b>{{ KIND[k][0] }}</b> <span class="hint">({{ COUNT[k](data.counts[k]) }})</span><br><span class="muted">{{ KIND[k][1] }}</span></span>
        </label>
      </fieldset>
      <div class="callout callout-crit"><Icon name="alert" /><span>این کار از سایت برنمی‌گردد. پیش از حذف، یک نسخه‌ی کامل پشتیبان روی سرور ساخته می‌شود و فایل‌های بیماران به سطل زباله‌ی سرور می‌روند؛ برگرداندن آن‌ها فقط کار مدیر سرور است.</span></div>
      <div class="form-grid">
        <div class="field"><label for="wipe-confirm">برای تأیید، کلمه‌ی «حذف» را بنویسید</label><input id="wipe-confirm" v-model="confirm" class="input" type="text" autocomplete="off" required></div>
        <div class="field"><label for="wipe-pw">رمز عبور خودتان</label><PasswordInput id="wipe-pw" v-model="password" autocomplete="current-password" required /></div>
      </div>
      <div class="form-actions">
        <button class="btn btn-danger" type="submit" :disabled="act.busy.value"><Icon name="trash" />حذف همیشگی از سایت</button>
        <RouterLink class="btn" to="/admin/users">انصراف</RouterLink>
      </div>
    </form>
  </section>
</template>
