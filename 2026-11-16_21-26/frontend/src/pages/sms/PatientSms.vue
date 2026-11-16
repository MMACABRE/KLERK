<script setup lang="ts">
// One custom message to a patient (legacy views/sms/patient.ejs).
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import SmsEditor from '../../components/SmsEditor.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('ارسال پیامک');
const route = useRoute();
const router = useRouter();
const code = String(route.params.code);
const text = ref('');
const act = useAction();
const { data, error } = useLoad(() => api.get(`/patients/${code}/sms`));
async function send() {
  if (await act.run(() => api.post(`/patients/${code}/sms`, { text: text.value }))) router.push({ path: '/sms', query: { kind: 'custom' } });
}
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="page-head"><div><div class="breadcrumb"><RouterLink :to="`/patients/${code}`">{{ data.patient.firstName }} {{ data.patient.lastName }}</RouterLink> / پیامک</div><h1>ارسال پیامک</h1>
      <p>گیرنده: <b>{{ data.patient.firstName }} {{ data.patient.lastName }}</b> · <span class="mono">{{ data.phone || '—' }}</span></p></div></div>
    <div v-if="data.blocked" class="callout mb-4" role="alert"><Icon name="alert" /><span>{{ data.blocked }}</span></div>
    <div v-if="act.error.value && act.error.value !== data.blocked" class="callout callout-crit mb-4" role="alert"><Icon name="alert" /><span>{{ act.error.value }}</span></div>
    <section class="card">
      <form class="card-body form-grid" @submit.prevent="send">
        <div class="field span-2 sms-editor">
          <label for="m-text">متن پیام</label>
          <SmsEditor id="m-text" v-model="text" :rows="4" :maxlength="500" :disabled="Boolean(data.blocked)"><span class="hint">اطلاعات پزشکی در پیام ننویسید؛ پیام از سرویس شخص ثالث می‌گذرد. پیام تا یک دقیقه‌ی دیگر ارسال می‌شود.</span></SmsEditor>
        </div>
        <div class="form-actions span-2">
          <button class="btn btn-primary" type="submit" :disabled="Boolean(data.blocked) || act.busy.value">ارسال</button>
          <RouterLink class="btn btn-ghost" :to="`/patients/${code}`">انصراف</RouterLink>
        </div>
      </form>
    </section>
  </template>
</template>
