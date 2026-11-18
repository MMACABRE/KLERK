<script setup lang="ts">
// Bulk SMS (legacy views/sms/bulk.ejs): saved search + text, preview, then the recipient count typed to confirm.
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import SmsNav from '../../components/SmsNav.vue';
import SmsEditor from '../../components/SmsEditor.vue';
import { api, ApiError } from '../../api/client';
import { setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useLoad } from '../../lib/usePage';

setTitle('ارسال گروهی');
const router = useRouter();
const saved = ref('');
const text = ref('');
const confirmCount = ref('');
const preview = ref<any>(null);
const error = ref('');
const busy = ref(false);
const { data } = useLoad(() => api.get('/sms/bulk'));

async function step(path: string) {
  busy.value = true;
  error.value = '';
  try {
    const out = await api.post(path, { saved: saved.value, text: text.value, confirmCount: confirmCount.value });
    if (path.endsWith('preview')) preview.value = out.preview;
    else router.push({ path: '/sms', query: { kind: 'bulk' } });
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
      if (e.data.preview) preview.value = e.data.preview;
    }
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/sms">پیامک</RouterLink> / ارسال گروهی</div><h1>ارسال گروهی</h1>
    <p>پیام برای بیمارانِ یک جستجوی ذخیره‌شده فرستاده می‌شود. نخست پیش‌نمایش را ببینید، سپس تعداد گیرندگان را تأیید کنید. حداکثر {{ fa(data?.bulkMax ?? 500) }} گیرنده در هر ارسال.</p></div></div>
  <SmsNav here="bulk" />
  <template v-if="data">
    <div v-if="data.ready.notReady" class="callout mb-4" role="status"><Icon name="alert" /><span>{{ data.ready.notReady }}</span></div>
    <div v-if="error" class="callout callout-crit mb-4" role="alert"><Icon name="alert" /><span>{{ error }}</span></div>
    <section class="card" aria-labelledby="b-h">
      <div class="card-head"><h2 id="b-h">گیرندگان و متن</h2></div>
      <div v-if="!data.saved.length" class="card-body"><p class="muted">جستجوی ذخیره‌شده‌ای نیست. نخست در <RouterLink to="/search">جستجوی پیشرفته</RouterLink> یک جستجو را ذخیره کنید.</p></div>
      <form v-else class="card-body form-grid" @submit.prevent="step('/sms/bulk/preview')">
        <div class="field span-2"><label for="b-saved">جستجوی ذخیره‌شده</label>
          <select id="b-saved" v-model="saved" class="select" required><option value="">انتخاب کنید</option><option v-for="s in data.saved" :key="s.id" :value="String(s.id)">{{ s.name }}</option></select></div>
        <div class="field span-2 sms-editor">
          <label for="b-text">متن پیام</label>
          <SmsEditor id="b-text" v-model="text" :rows="4" :maxlength="500"><span class="hint">برای گذاشتن نام هر بیمار {نام} را بنویسید. اطلاعات پزشکی در پیام ننویسید.</span></SmsEditor>
        </div>
        <div class="form-actions span-2"><button class="btn btn-primary" type="submit" :disabled="busy">پیش‌نمایش</button></div>
      </form>
    </section>
    <section v-if="preview" class="card mt-6" aria-labelledby="p-h">
      <div class="card-head"><h2 id="p-h">پیش‌نمایش</h2></div>
      <div class="card-body stack">
        <dl class="sms-facts">
          <div><dt>گیرندگان</dt><dd><b>{{ fa(preview.count) }}</b> نفر</dd></div>
          <div><dt>ردشده</dt><dd>پیامک نمی‌خواهند {{ fa(preview.skipped.optout) }} · بایگانی‌شده {{ fa(preview.skipped.archived) }} · شماره‌ی نامعتبر {{ fa(preview.skipped.phone) }} · شماره‌ی تکراری {{ fa(preview.skipped.duplicate) }}</dd></div>
          <div><dt>بخش‌های هر پیام</dt><dd>{{ fa(preview.partsEach) }} (جمع {{ fa(preview.partsTotal) }} بخش)</dd></div>
          <div v-if="preview.balance !== ''"><dt>اعتبار فعلی</dt><dd>{{ fa(Math.floor(Number(preview.balance))) }} پیام</dd></div>
        </dl>
        <p class="sms-sample">نمونه: <span>{{ preview.sample }}</span></p>
        <form class="inline-form" @submit.prevent="step('/sms/bulk/confirm')">
          <label for="b-count">برای تأیید، تعداد گیرندگان را دوباره بنویسید</label>
          <input id="b-count" v-model="confirmCount" class="input" type="text" inputmode="numeric" dir="ltr" autocomplete="off" required>
          <button class="btn btn-primary" type="submit" :disabled="busy">ارسال به صف</button>
        </form>
      </div>
    </section>
  </template>
</template>
