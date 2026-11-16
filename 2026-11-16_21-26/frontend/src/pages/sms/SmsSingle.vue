<script setup lang="ts">
// «ارسال تکی» (owner, 2026-11-16): one message to any mobile number, a patient or not, for example a visit reminder
// for someone who is not registered yet. The text starts as the visit-reminder template of the SMS settings; the
// server fills {نام}, {تاریخ} and {ساعت} from the fields below (only the ones the text uses are needed), shows the
// finished message, and queues it. The worker sends it within a minute.
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import SmsEditor from '../../components/SmsEditor.vue';
import SmsNav from '../../components/SmsNav.vue';
import { api, ApiError } from '../../api/client';
import { setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { vFloat } from '../../lib/directives';
import { useAction, useLoad } from '../../lib/usePage';
import * as jc from '../../lib/jalali-math';

setTitle('ارسال تکی');
const router = useRouter();
const form = ref({ name: '', phone: '', date: jc.format(jc.today()), time: '', text: '' });
const fields = ref<Record<string, string>>({});
const preview = ref<{ text: string; parts: number } | null>(null);
const act = useAction();
const { data, error } = useLoad(async () => {
  const d = await api.get('/sms/send');
  form.value.text = d.template;
  return d;
});
const uses = (token: string) => form.value.text.includes(`{${token}}`);

async function call(previewOnly: boolean) {
  fields.value = {};
  act.error.value = '';
  try {
    return await api.post('/sms/send', { ...form.value, preview: previewOnly });
  } catch (e) {
    if (e instanceof ApiError) { fields.value = e.fields; act.error.value = e.message; } else act.error.value = 'خطایی رخ داد.';
    return null;
  }
}
async function show() {
  preview.value = await call(true);
}
async function send() {
  act.busy.value = true;
  const out = await call(false);
  act.busy.value = false;
  if (out) router.push({ path: '/sms', query: { kind: 'custom' } });
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/sms">پیامک</RouterLink> / ارسال تکی</div><h1>ارسال تکی</h1>
    <p>یک پیامک به هر شماره‌ی موبایل، حتی کسی که هنوز بیمار ثبت‌شده نیست؛ مثلاً یادآوری نوبت.</p></div></div>
  <SmsNav here="single" />
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div v-if="data.blocked" class="callout mb-4" role="alert"><Icon name="alert" /><span>{{ data.blocked }}</span></div>
    <div v-if="act.error.value && act.error.value !== data.blocked" class="callout callout-crit mb-4" role="alert"><Icon name="alert" /><span>{{ act.error.value }}</span></div>
    <section class="card">
      <form class="card-body form-grid" @submit.prevent="send" @input="preview = null">
        <div v-float class="field">
          <label for="ss-name">نام گیرنده</label>
          <input id="ss-name" v-model="form.name" class="input" type="text" maxlength="80" autocomplete="off" :aria-invalid="Boolean(fields.name)">
          <p v-if="fields.name" class="field-error">{{ fields.name }}</p>
          <p v-else-if="!uses('نام')" class="hint">متن پیام {نام} ندارد.</p>
        </div>
        <div v-float class="field">
          <label for="ss-phone">شماره‌ی موبایل</label>
          <input id="ss-phone" v-model="form.phone" class="input mono" type="tel" dir="ltr" inputmode="tel" maxlength="20" autocomplete="off" placeholder="09121234567" :aria-invalid="Boolean(fields.phone)">
          <p v-if="fields.phone" class="field-error">{{ fields.phone }}</p>
        </div>
        <div class="field">
          <label for="ss-date">تاریخ نوبت</label>
          <JalaliInput id="ss-date" v-model="form.date" placeholder="۱۴۰۳/۰۵/۱۲" />
          <p v-if="fields.date" class="field-error">{{ fields.date }}</p>
        </div>
        <div v-float class="field">
          <label for="ss-time">ساعت نوبت</label>
          <input id="ss-time" v-model="form.time" class="input mono" type="text" dir="ltr" inputmode="numeric" maxlength="5" placeholder="16:30" :aria-invalid="Boolean(fields.time)">
          <p v-if="fields.time" class="field-error">{{ fields.time }}</p>
        </div>
        <div class="field span-2 sms-editor">
          <label for="ss-text">متن پیام</label>
          <SmsEditor id="ss-text" v-model="form.text" :rows="4" :maxlength="300" tokens><span class="hint">متن یادآوری تنظیمات پیامک؛ برای همین پیام می‌توانید آن را تغییر دهید. اطلاعات پزشکی در پیام ننویسید.</span></SmsEditor>
          <p v-if="fields.text" class="field-error">{{ fields.text }}</p>
        </div>
        <div v-if="preview" class="field span-2" role="status">
          <span class="label">پیامی که فرستاده می‌شود · {{ fa(preview.parts) }} پیامک</span>
          <p class="sms-preview">{{ preview.text }}</p>
        </div>
        <div class="form-actions span-2">
          <button class="btn" type="button" :disabled="act.busy.value" @click="show"><Icon name="eye" />پیش‌نمایش</button>
          <button class="btn btn-primary" type="submit" :disabled="Boolean(data.blocked) || act.busy.value">ارسال</button>
          <RouterLink class="btn btn-ghost" to="/sms">انصراف</RouterLink>
        </div>
      </form>
    </section>
  </template>
</template>
