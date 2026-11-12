<script setup lang="ts">
// New visit (with a patient picker first) and visit edit (legacy views/visits/form.ejs and pick.ejs). The time box
// opens the day bar dropdown (D50) and the length is a clock-face dial (D51). If the day bar cannot load, the booked
// times of the chosen day are listed under the time box instead.
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import LengthDial from '../../components/LengthDial.vue';
import TimeBarInput from '../../components/TimeBarInput.vue';
import { api } from '../../api/client';
import { session, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { qs, useAction } from '../../lib/usePage';
import * as jc from '../../lib/jalali-math.js';

const route = useRoute();
const router = useRouter();
const visitId = route.params.id ? String(route.params.id) : '';
const editing = Boolean(visitId);
const back = qs(route.query.back);
const patientCode = ref(qs(route.query.patient));
const patient = ref<any>(null);
const loadError = ref('');
const LEADS: Record<string, string> = { none: 'بدون یادآوری', now: 'همین الان', h2: '۲ ساعت قبل', d1: '۱ روز قبل', d2: '۲ روز قبل' };
const form = ref({ visitDate: qs(route.query.d) || jc.format(jc.today()), visitTime: qs(route.query.t), durationMin: '15', status: 'scheduled', reason: '', notes: '', reminderLead: '' });
const booked = ref<any[]>([]);
const barFailed = ref(false);
const { busy, error, fields, run } = useAction();
setTitle(editing ? 'ویرایش ویزیت' : 'ویزیت جدید');

// patient picker
const q = ref('');
const found = ref<any[] | null>(null);
async function find() {
  found.value = (await api.get('/visits/patient-search', { q: q.value })).found;
}

async function loadPatient() {
  loadError.value = '';
  try {
    if (editing) {
      const d = await api.get(`/visits/${visitId}`);
      patient.value = d.patient;
      const v = d.visit;
      form.value = { visitDate: v.date.input, visitTime: v.time, durationMin: String(v.durationMin), status: v.status, reason: v.reason ?? '', notes: v.notes ?? '', reminderLead: v.reminderLead ?? '' };
    } else if (patientCode.value) {
      const d = await api.get(`/patients/${patientCode.value}`);
      patient.value = d.patient;
      if (d.patient.status === 'archived') loadError.value = 'پرونده بایگانی‌شده است. برای ثبت ویزیت جدید، نخست آن را از بایگانی خارج کنید.';
    }
  } catch (e: any) {
    loadError.value = e.message;
  }
}
loadPatient();

async function loadBooked() {
  const d = jc.parse(form.value.visitDate);
  if (!d) { booked.value = []; return; }
  try {
    booked.value = (await api.get('/visits/day', { d: form.value.visitDate, exclude: visitId })).bookings;
  } catch { booked.value = []; }
}
watch([() => form.value.visitDate, barFailed], () => { if (barFailed.value) loadBooked(); });
const bookedText = computed(() => booked.value.map((b) => `${fa(b.time)} تا ${fa(b.until)}`).join('، '));

const cancelTo = computed(() => (back && back !== 'profile' ? back : `/patients/${patient.value?.code}#visits`));

async function save() {
  const body: Record<string, any> = { ...form.value };
  if (!session.me?.smsOn) delete body.reminderLead;
  if (editing) {
    if (await run(() => api.patch(`/visits/${visitId}`, body))) router.push(back || `/patients/${patient.value.code}#visits`);
  } else {
    const out = await run(() => api.post(`/patients/${patient.value.code}/visits`, body));
    if (out) router.push(back === 'profile' ? `/patients/${patient.value.code}#visits` : { path: '/visits', query: { d: out.dateInput } });
  }
}
function choose(code: string) {
  patientCode.value = code;
  router.replace({ query: { ...route.query, patient: code } });
}
</script>

<template>
  <div class="breadcrumb"><RouterLink to="/visits" lang="en">Visits</RouterLink> / {{ editing ? 'ویرایش' : 'جدید' }}</div>

  <template v-if="!editing && !patientCode">
    <div class="page-head"><div><h1>ویزیت جدید</h1><p><template v-if="form.visitTime">ساعت <span class="mono">{{ fa(form.visitTime) }}</span><template v-if="route.query.d"> روز <span class="mono">{{ fa(route.query.d) }}</span></template> · </template>نخست بیمار را پیدا کنید.</p></div></div>
    <section class="card">
      <form class="toolbar" @submit.prevent="find">
        <div class="input-group flex-1-240-420">
          <Icon name="search" />
          <input v-model="q" class="input" type="search" placeholder="نام، کد یا شماره تلفن" aria-label="جستجوی بیمار" autofocus>
        </div>
        <button class="btn btn-primary" type="submit">جستجو</button>
      </form>
      <div v-if="found && !found.length" class="card-body"><p class="muted">بیماری با این مشخصات پیدا نشد.</p></div>
      <ul v-if="found && found.length" class="visit-list pick-list">
        <li v-for="p in found" :key="p.code" class="visit"><div class="visit-body"><b>{{ p.firstName }} {{ p.lastName }}</b><span class="mono">{{ p.code }}</span></div>
          <button class="btn btn-sm btn-primary" type="button" @click="choose(p.code)">انتخاب</button></li>
      </ul>
    </section>
  </template>

  <template v-else>
    <p v-if="loadError" class="info-box" role="alert">{{ loadError }}</p>
    <template v-if="patient && !loadError">
      <div class="page-head"><div><h1>{{ editing ? 'ویرایش ویزیت' : 'ثبت ویزیت' }}</h1>
        <p><RouterLink :to="`/patients/${patient.code}`">{{ patient.firstName }} {{ patient.lastName }}</RouterLink> · <span class="mono">{{ patient.code }}</span></p></div></div>
      <section class="card">
        <form class="card-body form-grid" @submit.prevent="save">
          <p v-if="error && !Object.keys(fields).length" class="info-box span-2" role="alert">{{ error }}</p>
          <div class="field">
            <label for="f-date">تاریخ</label>
            <JalaliInput id="f-date" v-model="form.visitDate" placeholder="۱۴۰۳/۰۵/۱۲" />
            <p v-if="fields.visitDate" id="f-date-err" class="field-error" role="alert">{{ fields.visitDate }}</p>
          </div>
          <div class="field">
            <label for="f-time">ساعت</label>
            <TimeBarInput id="f-time" v-model="form.visitTime" :date="form.visitDate" :duration="Number(form.durationMin)" :exclude="visitId"
              :describedby="barFailed ? 'f-time-booked' : undefined" :invalid="Boolean(fields.visitTime)" @failed="barFailed = $event" />
            <p v-if="barFailed" id="f-time-booked" class="hint day-booked">{{ booked.length ? 'ساعت‌های رزروشده‌ی این روز: ' + bookedText : 'در این روز هنوز ساعتی رزرو نشده است.' }}</p>
            <p v-if="fields.visitTime" id="f-time-err" class="field-error" role="alert">{{ fields.visitTime }}</p>
          </div>
          <div class="field">
            <label id="f-duration-label" for="f-duration">مدت ویزیت</label>
            <LengthDial id="f-duration" v-model="form.durationMin" label-id="f-duration-label" />
            <p v-if="fields.durationMin" class="field-error" role="alert">{{ fields.durationMin }}</p>
          </div>
          <div class="field">
            <label for="f-status">وضعیت</label>
            <select id="f-status" v-model="form.status" class="select">
              <option value="scheduled">برنامه‌ریزی‌شده</option>
              <option value="done">انجام‌شده</option>
              <option value="cancelled">لغو‌شده</option>
            </select>
          </div>
          <div class="field">
            <label for="f-reason">شرح ویزیت</label>
            <input id="f-reason" v-model="form.reason" class="input" type="text" maxlength="200" placeholder="مثلاً: کنترل فشار خون">
          </div>
          <div v-if="session.me?.smsOn" class="field">
            <label for="f-lead">یادآوری پیامکی</label>
            <select id="f-lead" v-model="form.reminderLead" class="select">
              <option value="">پیش‌فرض کلینیک ({{ LEADS[session.me?.smsDefaultLead ?? 'd1'] }})</option>
              <option v-for="(l, k) in LEADS" :key="k" :value="k">{{ l }}</option>
            </select>
          </div>
          <div class="field span-2">
            <label for="f-notes">یادداشت</label>
            <textarea id="f-notes" v-model="form.notes" class="textarea" rows="3" maxlength="1000"></textarea>
          </div>
          <div class="form-actions span-2">
            <button class="btn btn-primary" type="submit" :disabled="busy">ذخیره</button>
            <RouterLink class="btn btn-ghost" :to="cancelTo">انصراف</RouterLink>
          </div>
        </form>
      </section>
    </template>
  </template>
</template>
