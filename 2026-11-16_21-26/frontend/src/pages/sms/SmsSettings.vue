<script setup lang="ts">
// SMS settings (legacy views/sms/settings.ejs): switch on with the planned-reminder count confirmed, sender line,
// lead, hour, wording; the key, alert number and test message with the key flag.
import { ref } from 'vue';
import Icon from '../../components/Icon.vue';
import SmsNav from '../../components/SmsNav.vue';
import SmsEditor from '../../components/SmsEditor.vue';
import { api } from '../../api/client';
import { can, refreshMe, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('تنظیمات پیامک');
const form = ref<any>({});
const confirmOn = ref(false);
const apiKey = ref('');
const act = useAction();
const keyAct = useAction();
const { data, load } = useLoad(async () => {
  const d = await api.get('/sms/settings');
  form.value = { ...d.settings };
  return d;
});
async function save() {
  const body = { ...form.value, confirmCount: confirmOn.value ? String(data.value.planned) : '' };
  if (await act.run(() => api.put('/sms/settings', body), 'تنظیمات ذخیره شد.')) { await load(); refreshMe(); }
}
async function setKey() {
  if (await keyAct.run(() => api.put('/sms/key', { apiKey: apiKey.value }), 'کلید ذخیره شد.')) { apiKey.value = ''; load(); }
}
async function delKey() {
  if (await keyAct.run(() => api.del('/sms/key'), 'کلید پاک شد.')) load();
}
async function test() {
  const out = await keyAct.run(() => api.post('/sms/test'));
  if (out) keyAct.notice.value = out.notice;
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><RouterLink to="/sms">پیامک</RouterLink> / تنظیمات</div><h1>تنظیمات پیامک</h1>
    <p>یادآوری ویزیت‌ها خودکار و در بازه‌ی ۸ صبح تا ۹ شب ارسال می‌شود. متن پیامک فقط نام، تاریخ و ساعت را دارد و اطلاعات پزشکی در آن نیست.</p></div></div>
  <SmsNav here="settings" />
  <div v-if="act.notice.value || keyAct.notice.value" class="callout callout-info mb-4" role="status"><Icon name="check" /><span>{{ act.notice.value || keyAct.notice.value }}</span></div>
  <div v-if="act.error.value && !Object.keys(act.fields.value).length" class="info-box" role="alert">{{ act.error.value }}</div>
  <template v-if="data">
    <section class="card" aria-labelledby="gen-h">
      <div class="card-head"><h2 id="gen-h">ارسال و زمان‌بندی</h2></div>
      <form class="card-body form-grid" @submit.prevent="save">
        <div class="field span-2">
          <label class="check"><input v-model="form.smsEnabled" type="checkbox" :disabled="!can('sms', 2)"><span>ارسال پیامک فعال باشد</span></label>
          <label v-if="!data.ready.on" class="check"><input v-model="confirmOn" type="checkbox"><span>می‌دانم که روشن کردن پیامک برای <b>{{ fa(data.planned) }}</b> ویزیتِ برنامه‌ریزی‌شده یادآوری می‌فرستد.</span></label>
          <p v-if="act.fields.value.smsEnabled" class="field-error" role="alert">{{ act.fields.value.smsEnabled }}</p>
        </div>
        <div class="field"><label for="s-line">شماره‌ی خط فرستنده</label><input id="s-line" v-model="form.smsLine" class="input" type="text" maxlength="20" dir="ltr" autocomplete="off" required><span class="hint">برای وب‌سرویس معمولاً ۹۰۰۰۸۳۶۱</span><p v-if="act.fields.value.smsLine" class="field-error" role="alert">{{ act.fields.value.smsLine }}</p></div>
        <div class="field"><label for="s-lead">زمان پیش‌فرض یادآوری</label>
          <select id="s-lead" v-model="form.smsLead" class="select"><option v-for="(l, k) in data.leads" :key="k" :value="k">{{ l }}</option></select>
          <span class="hint">منشی می‌تواند برای هر ویزیت آن را عوض کند.</span><p v-if="act.fields.value.smsLead" class="field-error" role="alert">{{ act.fields.value.smsLead }}</p></div>
        <div class="field"><label for="s-hour">ساعت ارسال یادآوری «روز قبل»</label><input id="s-hour" v-model="form.smsHour" class="input" type="text" inputmode="numeric" dir="ltr" maxlength="2" required><span class="hint">عددی از ۸ تا ۲۱</span><p v-if="act.fields.value.smsHour" class="field-error" role="alert">{{ act.fields.value.smsHour }}</p></div>
        <div></div>
        <div class="field span-2 sms-editor">
          <label for="s-tpl">متن یادآوری</label>
          <SmsEditor id="s-tpl" v-model="form.smsTemplate" :maxlength="300" tokens :sample="data.tokensSample">
            <span class="hint">{نام}، {تاریخ} و {ساعت} را می‌توانید تایپ هم بکنید. {تاریخ} و {ساعت} الزامی‌اند.</span>
          </SmsEditor>
          <p v-if="act.fields.value.smsTemplate" class="field-error" role="alert">{{ act.fields.value.smsTemplate }}</p>
        </div>
        <template v-if="data.canKey">
          <div class="field"><label for="s-alert">شماره‌ی موبایل هشدار کمبود اعتبار</label><input id="s-alert" v-model="form.smsAlertPhone" class="input" type="text" inputmode="tel" dir="ltr" maxlength="20" autocomplete="off"><span class="hint">وقتی اعتبار به حد پایین برسد، یک پیامک به این شماره می‌رود. خالی یعنی بدون پیامک هشدار.</span><p v-if="act.fields.value.smsAlertPhone" class="field-error" role="alert">{{ act.fields.value.smsAlertPhone }}</p></div>
          <div class="field"><label for="s-low">حد هشدار (تعداد پیام باقی‌مانده)</label><input id="s-low" v-model="form.smsLowThreshold" class="input" type="text" inputmode="numeric" dir="ltr" maxlength="4"><span class="hint">عددی از ۱ تا ۱۰۰۰</span><p v-if="act.fields.value.smsLowThreshold" class="field-error" role="alert">{{ act.fields.value.smsLowThreshold }}</p></div>
        </template>
        <div v-if="can('sms', 2)" class="form-actions span-2"><button class="btn btn-primary" type="submit" :disabled="act.busy.value">ذخیره‌ی تنظیمات</button></div>
      </form>
    </section>
    <section v-if="data.canKey" class="card mt-6" aria-labelledby="key-h">
      <div class="card-head"><div><h2 id="key-h">کلید پیامک</h2><p>کلید حساب کلینیک در ایران‌پیامک (پنل ← وب‌سرویس ← لیست کلیدهای دسترسی). کلید رمزنگاری‌شده ذخیره می‌شود و دوباره نشان داده نمی‌شود.</p></div></div>
      <div class="card-body stack">
        <p v-if="data.key">کلید ثبت‌شده: <span class="mono">••••{{ data.key.hint }}</span> <span v-if="!data.key.usable" class="chip chip-crit">قابل خواندن نیست؛ کلید را دوباره وارد کنید</span><span v-else class="chip chip-ok">فعال</span></p>
        <p v-else class="muted">کلیدی ثبت نشده است.</p>
        <form class="inline-form" @submit.prevent="setKey">
          <label class="sr-only" for="k-key">کلید جدید</label>
          <input id="k-key" v-model="apiKey" class="input" type="password" autocomplete="off" dir="ltr" placeholder="کلید را بچسبانید" required>
          <button class="btn btn-primary" type="submit" :disabled="keyAct.busy.value">{{ data.key ? 'تغییر کلید' : 'ثبت کلید' }}</button>
        </form>
        <p v-if="keyAct.error.value" class="field-error" role="alert">{{ keyAct.error.value }}</p>
        <template v-if="data.key">
          <div class="user-actions">
            <button class="btn" type="button" :disabled="keyAct.busy.value" @click="test">پیامک آزمایشی</button>
            <button class="btn btn-danger" type="button" :disabled="keyAct.busy.value" @click="delKey">حذف کلید</button>
          </div>
          <p class="hint">پیامک آزمایشی به شماره‌ی هشدار می‌رود؛ نخست آن شماره را بالا ذخیره کنید.</p>
        </template>
      </div>
    </section>
  </template>
</template>
