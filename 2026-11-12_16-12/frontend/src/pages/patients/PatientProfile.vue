<script setup lang="ts">
// Patient profile (legacy views/patients/show.ejs): head with photo, balance strip, personal/medical tabs,
// visit timeline, documents gallery.
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import Icon from '../../components/Icon.vue';
import VisitItem from '../../components/VisitItem.vue';
import DocTile from '../../components/DocTile.vue';
import UploadForm from '../../components/UploadForm.vue';
import { api, ApiError } from '../../api/client';
import { can, has, setTitle, refreshMe } from '../../lib/session';
import { fa, initialsOf, SEX, STATUS } from '../../lib/fmt';
import { prepareFiles } from '../../lib/shrink';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const code = String(route.params.code);
const { data, error, loading, load } = useLoad(async () => {
  const d = await api.get(`/patients/${code}`);
  setTitle(`${d.patient.firstName} ${d.patient.lastName}`);
  return d;
});
const p = computed(() => data.value?.patient);
const tab = ref(1);
const actionError = ref('');
const med = ref({ name: '', dosage: '', frequency: '' });
const medAct = useAction();
const photoError = ref('');
const dash = '—';
const chips = (s: string | null) => (s ? s.split(',').map((x) => x.trim()).filter(Boolean) : []);
const bmi = computed(() => {
  const h = Number(p.value?.heightCm);
  const w = Number(p.value?.weightKg);
  return h && w ? w / ((h / 100) ** 2) : null;
});
const allVisits = computed(() => (data.value?.visits ? [...data.value.visits.upcoming, ...data.value.visits.rest] : []));

async function act(fn: () => Promise<unknown>) {
  actionError.value = '';
  try { await fn(); await load(); refreshMe(); } catch (e) { actionError.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.'; }
}
const archive = () => act(() => api.post(`/patients/${code}/archive`));
const unarchive = () => act(() => api.post(`/patients/${code}/unarchive`));

async function addMed() {
  const ok = await medAct.run(() => api.post(`/patients/${code}/medications`, med.value));
  if (ok) { med.value = { name: '', dosage: '', frequency: '' }; load(); }
}
const removeMed = (id: number) => act(() => api.del(`/patients/${code}/medications/${id}`));

async function onPhoto(e: Event) {
  const input = e.target as HTMLInputElement;
  const [file] = await prepareFiles([...(input.files ?? [])]);
  input.value = '';
  if (!file) return;
  photoError.value = '';
  const form = new FormData();
  form.append('file', file);
  try { await api.post(`/patients/${code}/photo`, form); await load(); } catch (err) { photoError.value = err instanceof ApiError ? err.message : 'خطایی رخ داد.'; }
}
const removePhoto = () => act(() => api.del(`/patients/${code}/photo`));
const photoUrl = computed(() => `/api/v1/patients/${code}/photo?t=${data.value?.patient?.updatedAt?.iso ?? ''}`);
</script>

<template>
  <p v-if="loading && !data" class="muted">در حال بارگذاری…</p>
  <div v-else-if="error" class="card"><div class="card-body"><p class="info-box" role="alert">{{ error }}</p></div></div>
  <template v-else-if="data && p">
    <div class="breadcrumb"><RouterLink to="/patients" lang="en">Patients</RouterLink> / {{ p.firstName }} {{ p.lastName }}</div>
    <p v-if="actionError" class="info-box" role="alert">{{ actionError }}</p>

    <section class="card">
      <div class="patient-head">
        <div class="photo-box">
          <img v-if="data.hasPhoto && can('documents')" class="avatar avatar-lg avatar-photo" :src="photoUrl" :alt="`عکس ${p.firstName} ${p.lastName}`" width="96" height="96">
          <span v-else class="avatar avatar-lg avatar-warm">{{ initialsOf(p.firstName, p.lastName) }}</span>
          <template v-if="can('documents', 2)">
            <form class="photo-form" @submit.prevent>
              <label class="btn btn-sm" for="photo-file"><Icon name="upload" />{{ data.hasPhoto ? 'تغییر عکس' : 'افزودن عکس' }}</label>
              <input id="photo-file" class="photo-input" type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" @change="onPhoto">
            </form>
            <button v-if="data.hasPhoto" class="btn btn-sm btn-ghost" type="button" @click="removePhoto">برداشتن عکس</button>
          </template>
          <p v-if="photoError" class="field-error" role="alert">{{ photoError }}</p>
        </div>
        <div class="grow">
          <h1>{{ p.firstName }} {{ p.lastName }}</h1>
          <div class="meta">
            <span><b>کد بیمار:</b> <span class="mono">{{ p.code }}</span><span v-if="route.query.code === 'changed'" class="chip chip-ok chip-sm" role="status">کد تغییر کرد</span></span>
            <span><b>تاریخ تولد:</b> {{ p.birthDate?.short ?? dash }}</span>
            <span><b>تاریخ ثبت پرونده:</b> {{ p.createdDay?.short ?? dash }}</span>
            <span v-if="p.age !== null"><b>سن:</b> {{ fa(p.age) }} سال</span>
            <span v-if="p.sex"><b>جنسیت:</b> {{ SEX[p.sex] }}</span>
            <span v-if="p.phone"><b>تلفن:</b> <span class="mono">{{ p.phone }}</span></span>
            <span v-if="data.lastSms"><b>پیامک:</b> {{ data.lastSms.kindText }} <span class="chip chip-sm" :class="data.lastSms.chip">{{ data.lastSms.statusText }}</span></span>
          </div>
          <div class="chips">
            <span class="chip" :class="STATUS[p.status].chip">{{ STATUS[p.status].label }}</span>
            <span v-if="p.smsOptout" class="chip chip-mute">بدون پیامک</span>
            <span v-for="a in chips(p.allergies)" :key="a" class="chip chip-crit">حساسیت: {{ a }}</span>
          </div>
        </div>
        <div class="patient-actions">
          <a v-if="can('documents', 2)" class="btn btn-sm btn-primary" href="#docs"><Icon name="upload" />بارگذاری سند و تصویر</a>
          <template v-if="can('patients', 2)">
            <RouterLink class="btn btn-sm" :to="`/patients/${p.code}/edit`">ویرایش</RouterLink>
            <button v-if="p.status === 'archived'" class="btn btn-sm" type="button" @click="unarchive">خروج از بایگانی</button>
            <button v-else class="btn btn-sm" type="button" @click="archive">بایگانی</button>
          </template>
          <RouterLink v-if="can('sms', 2) && can('patients')" class="btn btn-sm" :to="`/patients/${p.code}/sms`"><Icon name="mail" />ارسال پیامک</RouterLink>
          <RouterLink v-if="has('patient_delete')" class="btn btn-sm btn-danger" :to="`/patients/${p.code}/delete`">حذف</RouterLink>
        </div>
      </div>

      <div v-if="data.balance" class="balance-strip">
        <span v-if="data.balance.credit.rial" class="chip chip-info">بستانکار <span class="money">{{ data.balance.credit.display }}</span></span>
        <span v-else-if="data.balance.remaining.rial" class="chip chip-warn">مانده <span class="money">{{ data.balance.remaining.display }}</span></span>
        <span v-else class="chip chip-ok">بدون بدهی</span>
        <span v-if="p.discKind" class="chip chip-plain chip-mute">تخفیف دائمی {{ p.discText }}</span>
        <RouterLink class="btn btn-sm btn-ghost" :to="`/patients/${p.code}/history`"><Icon name="wallet" />سوابق درمان و مالی</RouterLink>
        <a v-if="can('pdf')" class="btn btn-sm btn-ghost" :href="`/print/patients/${p.code}`"><Icon name="print" />چاپ پرونده</a>
      </div>
      <div v-else-if="can('pdf')" class="balance-strip"><a class="btn btn-sm btn-ghost" :href="`/print/patients/${p.code}`"><Icon name="print" />چاپ پرونده</a></div>

      <div class="tabs">
        <input id="tab-1" v-model="tab" type="radio" name="ptab" :value="1">
        <input id="tab-2" v-model="tab" type="radio" name="ptab" :value="2">
        <div class="tab-list">
          <label for="tab-1">شخصی</label>
          <label for="tab-2">پزشکی</label>
        </div>
        <div class="tab-panels">
          <div class="tab-panel panel-1">
            <div class="grid grid-2">
              <section>
                <h2 class="mb-4">هویت</h2>
                <dl class="kv">
                  <dt>نام کامل</dt><dd>{{ p.firstName }} {{ p.lastName }}</dd>
                  <dt>نام پدر</dt><dd>{{ p.fatherName || dash }}</dd>
                  <dt>تاریخ تولد</dt><dd>{{ p.birthDate?.short ?? dash }}</dd>
                  <dt>جنسیت</dt><dd>{{ SEX[p.sex] || dash }}</dd>
                  <dt>تاریخ ثبت پرونده</dt><dd>{{ p.createdDay?.short ?? dash }}</dd>
                  <dt>کد ملی</dt><dd><span v-if="p.nationalId" class="mono">{{ p.nationalId }}</span><template v-else>{{ dash }}</template></dd>
                </dl>
              </section>
              <section>
                <h2 class="mb-4">تماس</h2>
                <dl class="kv">
                  <dt>تلفن همراه</dt><dd><span v-if="p.phone" class="mono">{{ p.phone }}</span><template v-else>{{ dash }}</template></dd>
                  <dt>ایمیل</dt><dd><span v-if="p.email" class="mono">{{ p.email }}</span><template v-else>{{ dash }}</template></dd>
                </dl>
              </section>
              <section>
                <h2 class="mb-4">نشانی</h2>
                <dl class="kv"><dt>شهر</dt><dd>{{ p.city || dash }}</dd><dt>نشانی</dt><dd>{{ p.address || dash }}</dd></dl>
              </section>
              <section>
                <h2 class="mb-4">تماس اضطراری</h2>
                <dl class="kv">
                  <dt>نام</dt><dd>{{ p.emergencyName || dash }}</dd>
                  <dt>تلفن</dt><dd><span v-if="p.emergencyPhone" class="mono">{{ p.emergencyPhone }}</span><template v-else>{{ dash }}</template></dd>
                  <dt>نسبت</dt><dd>{{ p.emergencyRelation || dash }}</dd>
                </dl>
              </section>
              <section class="span-2">
                <h2 class="mb-4">مراجعه</h2>
                <dl class="kv"><dt>علت مراجعه</dt><dd>{{ p.visitReason || dash }}</dd><dt>معرف</dt><dd>{{ p.referral || dash }}</dd></dl>
              </section>
              <section class="span-2">
                <h2 class="mb-4">بیمه</h2>
                <dl class="kv">
                  <dt>نوع بیمه</dt><dd>{{ p.insuranceName || dash }}</dd>
                  <dt>شماره بیمه</dt><dd><span v-if="p.insuranceNumber" class="mono">{{ p.insuranceNumber }}</span><template v-else>{{ dash }}</template></dd>
                </dl>
              </section>
              <section v-if="data.customInfo.length" class="span-2">
                <h2 class="mb-4">سایر اطلاعات</h2>
                <dl class="kv"><template v-for="row in data.customInfo" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.text }}</dd></template></dl>
              </section>
            </div>
          </div>
          <div class="tab-panel panel-2">
            <div class="grid grid-2">
              <section>
                <h2 class="mb-4">حساسیت‌ها</h2>
                <div class="chips">
                  <span v-for="a in chips(p.allergies)" :key="a" class="chip chip-crit">{{ a }}</span>
                  <span v-if="!chips(p.allergies).length" class="muted">ثبت نشده</span>
                </div>
              </section>
              <section>
                <h2 class="mb-4">بیماری‌های زمینه‌ای</h2>
                <div class="chips">
                  <span v-for="c in chips(p.conditions)" :key="c" class="chip chip-outline">{{ c }}</span>
                  <span v-if="!chips(p.conditions).length" class="muted">ثبت نشده</span>
                </div>
              </section>
              <section class="span-2">
                <h2 class="mb-4">داروهای مصرفی</h2>
                <div v-if="data.medications.length" class="table-wrap table-card">
                  <table class="table mb-0">
                    <thead><tr><th scope="col">دارو</th><th scope="col">دوز</th><th scope="col">تواتر مصرف</th><th v-if="can('patients', 2)" scope="col"><span class="sr-only">حذف</span></th></tr></thead>
                    <tbody>
                      <tr v-for="m in data.medications" :key="m.id">
                        <td data-label="دارو">{{ m.name }}</td>
                        <td data-label="دوز">{{ m.dosage || dash }}</td>
                        <td data-label="تواتر مصرف">{{ m.frequency || dash }}</td>
                        <td v-if="can('patients', 2)"><button class="btn btn-sm" type="button" @click="removeMed(m.id)">حذف</button></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="muted">دارویی ثبت نشده است.</p>
                <form v-if="can('patients', 2)" class="toolbar toolbar-gap" @submit.prevent="addMed">
                  <input v-model="med.name" class="input" type="text" placeholder="نام دارو" aria-label="نام دارو" maxlength="100" required>
                  <input v-model="med.dosage" class="input" type="text" placeholder="دوز" aria-label="دوز" maxlength="60">
                  <input v-model="med.frequency" class="input" type="text" placeholder="تواتر مصرف" aria-label="تواتر مصرف" maxlength="60">
                  <button class="btn" type="submit" :disabled="medAct.busy.value"><Icon name="plus" />افزودن دارو</button>
                </form>
                <p v-if="medAct.error.value" class="field-error" role="alert">{{ medAct.error.value }}</p>
              </section>
              <section class="span-2">
                <h2 class="mb-4">علائم و اندازه‌گیری‌ها</h2>
                <div class="grid grid-4">
                  <article class="card stat"><div class="stat-label">فشار خون</div><div class="stat-value text-xl"><span v-if="p.bloodPressure" class="mono">{{ p.bloodPressure }}</span><template v-else>{{ dash }}</template></div></article>
                  <article class="card stat"><div class="stat-label">قد</div><div class="stat-value text-xl">{{ p.heightCm ? fa(p.heightCm) + ' سانتی‌متر' : dash }}</div></article>
                  <article class="card stat"><div class="stat-label">وزن</div><div class="stat-value text-xl">{{ p.weightKg ? fa(p.weightKg) + ' کیلوگرم' : dash }}</div></article>
                  <article class="card stat"><div class="stat-label">شاخص توده‌ی بدنی</div><div class="stat-value text-xl">{{ bmi ? fa(bmi.toFixed(1)) : dash }}</div></article>
                </div>
                <p v-if="p.bloodType" class="muted">گروه خونی: <span class="mono">{{ p.bloodType }}</span></p>
              </section>
              <section class="span-2">
                <h2 class="mb-4">یادداشت‌های بالینی</h2>
                <div class="notes-box">{{ p.medicalNotes || 'یادداشتی ثبت نشده است.' }}</div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="data.visits" id="visits" class="card visits-section" aria-labelledby="visits-h">
      <div class="card-head">
        <div><h2 id="visits-h">ویزیت‌ها</h2>
          <p v-if="data.visits.next">ویزیت بعدی: <b>{{ data.visits.next.date.long }}</b> ساعت <b class="mono">{{ fa(data.visits.next.time) }}</b></p>
          <p v-else>ویزیت برنامه‌ریزی‌شده‌ای ندارد</p></div>
        <span v-if="p.status === 'archived'" class="text-xs-muted">پرونده بایگانی‌شده است؛ ویزیت تازه ثبت نمی‌شود.</span>
        <RouterLink v-else-if="can('visits', 2)" class="btn btn-sm btn-primary" :to="{ path: '/visits/new', query: { patient: p.code } }"><Icon name="plus" />ویزیت جدید</RouterLink>
      </div>
      <div v-if="!allVisits.length" class="card-body"><p class="muted">هنوز ویزیتی ثبت نشده است. ویزیت‌های گذشته و بعدی بیمار اینجا روی یک خط زمان دیده می‌شوند.</p></div>
      <template v-else>
        <div v-if="data.visits.next" class="visit-next">
          <div class="visit-next-date"><small>{{ data.visits.next.date.parts.weekday }}</small><b>{{ data.visits.next.date.parts.day }}</b><span>{{ data.visits.next.date.parts.month }}</span></div>
          <div class="visit-next-body">
            <span class="eyebrow">ویزیت بعدی</span>
            <b class="mono visit-next-time">{{ fa(data.visits.next.time) }} <small>تا {{ fa(data.visits.next.until) }}</small></b>
            <span>{{ data.visits.next.reason || 'بدون شرح' }}</span>
          </div>
        </div>
        <ol class="visit-list visit-timeline rail">
          <VisitItem v-for="v in allVisits" :key="v.id" :v="v" :archived="p.status === 'archived'" :back="`/patients/${p.code}#visits`"
            @changed="load" @error="actionError = $event" />
        </ol>
      </template>
    </section>

    <section v-if="data.files" id="docs" class="card docs-section" aria-labelledby="docs-h">
      <div class="card-head">
        <div><h2 id="docs-h">مدارک پزشکی</h2><p>{{ fa(data.files.length) }} فایل</p></div>
        <RouterLink class="btn btn-sm btn-ghost" :to="`/patients/${p.code}/documents`">جستجو و طبقه‌بندی اسناد</RouterLink>
      </div>
      <UploadForm v-if="can('documents', 2)" :code="p.code" compact id-prefix="pf" @done="load" />
      <div v-if="data.files.length" class="doc-gallery card-body">
        <DocTile v-for="d in data.files" :key="d.filename" :d="d" :code="p.code" @changed="load" @error="actionError = $event" />
      </div>
      <div v-else class="card-body"><p class="muted">هنوز مدرکی بارگذاری نشده است.</p></div>
    </section>
  </template>
</template>
