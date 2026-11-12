<script setup lang="ts">
// Import & export (legacy views/data/index.ejs): CSV import with a staged preview and confirm, patient list
// exports, and the full zip. Downloads go through a plain form POST so the browser saves the streamed file.
// The confirm queues an import job that the worker runs (BUG-2); this page polls it and shows the final report.
import { computed, onUnmounted, ref, watch } from 'vue';
import Icon from '../components/Icon.vue';
import DropZone from '../components/DropZone.vue';
import { api, downloadGet, downloadPost } from '../api/client';
import { can, has, refreshMe, setTitle } from '../lib/session';
import { fa, faCount, STATUS } from '../lib/fmt';
import { useAction, useLoad } from '../lib/usePage';

setTitle('ورود و خروج داده');
const { data } = useLoad(() => api.get('/data'));
const files = ref<File[]>([]);
const preview = ref<any>(null);
const job = ref<any>(null);
const exportStatus = ref('');
const act = useAction();
const stateChip: Record<string, [string, string]> = { valid: ['chip-ok', 'معتبر'], invalid: ['chip-crit', 'نامعتبر'], duplicate: ['chip-warn', 'تکراری'] };
const kb = (n: number) => (n < 1024 ? 'کمتر از ۱ کیلوبایت' : `${faCount(Math.round(n / 1024))} کیلوبایت`);
const POLL_MS = 2000;
let timer: ReturnType<typeof setTimeout> | undefined;

const running = computed(() => job.value && (job.value.status === 'queued' || job.value.status === 'running'));
const percent = computed(() => (job.value?.total ? Math.floor((100 * job.value.done) / job.value.total) : 0));
const leftOut = computed(() => {
  if (!job.value) return [];
  const rows = [
    ...job.value.skippedRows.map((r: any) => ({ ...r, kind: 'skipped' })),
    ...job.value.failed.map((r: any) => ({ ...r, kind: 'failed' })),
  ];
  return rows.sort((a: any, b: any) => a.line - b.line);
});

const leftOutText = computed(() => {
  const parts = [];
  if (job.value?.skipped) parts.push(`${faCount(job.value.skipped)} ردیف به‌دلیل تکراری بودن رد شد.`);
  if (job.value?.failed.length) parts.push(`${faCount(job.value.failed.length)} ردیف خطا داشت و ثبت نشد.`);
  return parts.length ? ` ${parts.join(' ')}` : '';
});

function poll() {
  clearTimeout(timer);
  if (!running.value) return;
  timer = setTimeout(async () => {
    try {
      job.value = await api.get(`/data/imports/jobs/${job.value.id}`);
      if (job.value.status === 'done') refreshMe();
    } catch {
      // A dropped connection is retried on the next turn; the job keeps running on the server.
    }
    poll();
  }, POLL_MS);
}
watch(data, (d) => { if (d?.lastImport && !job.value) { job.value = d.lastImport; poll(); } });
onUnmounted(() => clearTimeout(timer));

async function upload() {
  const form = new FormData();
  if (files.value[0]) form.append('file', files.value[0]);
  const out = await act.run(() => api.post('/data/imports', form));
  if (out) { preview.value = out; job.value = null; }
}
async function confirm() {
  const out = await act.run(() => api.post(`/data/imports/${preview.value.token}/confirm`));
  if (out) { job.value = out; preview.value = null; files.value = []; poll(); }
}
async function resume() {
  const out = await act.run(() => api.post(`/data/imports/jobs/${job.value.id}/resume`));
  if (out) { job.value = out; poll(); }
}
async function cancel() {
  await act.run(() => api.del(`/data/imports/${preview.value.token}`));
  preview.value = null;
  files.value = [];
}
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Import &amp; Export</span></div>
      <h1>ورود و خروج داده</h1>
      <p>بیماران را از فایل CSV وارد کنید، فهرست بیماران را خروجی بگیرید یا یک نسخه‌ی کامل از همه‌ی اطلاعات دریافت کنید. هر بخش این صفحه فقط برای کاربرانی دیده می‌شود که دسترسی آن را دارند.</p>
    </div>
  </div>
  <section v-if="has('csv_import') && can('patients', 2)" aria-labelledby="import-h">
    <h2 id="import-h" class="h2-lg">ورود بیماران از فایل CSV</h2>
    <section v-if="job" class="card mb-6" aria-labelledby="job-h" aria-live="polite">
      <div class="card-head"><div><h3 id="job-h">ثبت بیماران از فایل <span class="mono">{{ job.fileName }}</span></h3><p>{{ faCount(job.total) }} ردیف · شروع {{ job.createdAt?.text }}</p></div></div>
      <div class="card-body stack-lg">
        <template v-if="running">
          <div class="progress" role="progressbar" aria-label="پیشرفت ثبت بیماران" aria-valuemin="0" :aria-valuemax="job.total" :aria-valuenow="job.done"><i :style="{ width: `${percent}%` }"></i></div>
          <p><b>در حال ثبت: {{ faCount(job.done) }} از {{ faCount(job.total) }} ردیف بررسی شد ({{ fa(percent) }}٪).</b> ثبت در پس‌زمینه انجام می‌شود؛ می‌توانید این صفحه را ببندید و بعداً برگردید.</p>
          <div v-if="!job.workerAlive" class="callout callout-crit" role="alert"><Icon name="alert" /><span><b>سرویس پس‌زمینه‌ی سامانه در حال اجرا نیست.</b> ثبت بیماران تا راه‌اندازی دوباره‌ی آن متوقف می‌ماند. به پشتیبان سامانه خبر دهید.</span></div>
        </template>
        <div v-else-if="job.status === 'failed'" class="callout callout-crit" role="alert">
          <Icon name="alert" />
          <span><b>ورود داده کامل نشد.</b> {{ faCount(job.inserted) }} بیمار ثبت شد و {{ faCount(job.pending) }} ردیف هنوز ثبت نشده است. ردیف‌های ثبت‌شده دوباره ثبت نمی‌شوند؛ با «ادامه‌ی ثبت» فقط ردیف‌های باقی‌مانده ثبت می‌شوند.</span>
        </div>
        <div v-else class="callout" :class="{ 'callout-info': !leftOut.length }" role="status">
          <Icon :name="leftOut.length ? 'alert' : 'check'" />
          <span><b>{{ faCount(job.inserted) }} بیمار از {{ faCount(job.total) }} ردیف فایل ثبت شد.</b>{{ leftOutText }} <RouterLink to="/patients">مشاهده‌ی فهرست بیماران</RouterLink></span>
        </div>
        <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
        <div v-if="job.status === 'failed'"><button class="btn btn-primary" type="button" :disabled="act.busy.value" @click="resume"><Icon name="upload" />ادامه‌ی ثبت</button></div>
      </div>
      <details v-if="!running && leftOut.length" class="card-body">
        <summary>ردیف‌هایی که ثبت نشدند ({{ faCount(leftOut.length) }})</summary>
        <div class="table-wrap mt-3">
          <table class="table">
            <thead><tr><th scope="col">ردیف فایل</th><th scope="col">وضعیت</th><th scope="col">دلیل</th></tr></thead>
            <tbody>
              <tr v-for="r in leftOut" :key="r.line">
                <td data-label="ردیف فایل" class="num">{{ fa(r.line) }}</td>
                <td data-label="وضعیت"><span class="chip chip-plain" :class="r.kind === 'failed' ? 'chip-crit' : 'chip-warn'">{{ r.kind === 'failed' ? 'خطا' : 'تکراری' }}</span></td>
                <td data-label="دلیل">{{ r.message }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </section>
    <template v-if="preview">
      <ul class="steps mb-6">
        <li class="is-done"><span>بارگذاری فایل</span></li>
        <li class="is-active"><span>بررسی ردیف‌ها</span></li>
        <li><span>تأیید و ثبت</span></li>
      </ul>
      <section class="card" aria-labelledby="preview-h">
        <div class="card-head"><div><h3 id="preview-h">پیش‌نمایش و بررسی ردیف‌ها</h3><p>هر ردیف پیش از ثبت بررسی می‌شود. فقط ردیف‌های معتبر ثبت می‌شوند.</p></div></div>
        <div class="card-body stack-lg">
          <div class="file-row">
            <Icon name="file" />
            <div class="grow"><b class="block-sm"><span class="mono">{{ preview.fileName }}</span></b><span class="text-xs-muted">{{ kb(preview.size) }} · {{ faCount(preview.total) }} ردیف</span></div>
          </div>
          <section class="grid grid-3" aria-label="آمار بررسی فایل">
            <article class="card stat"><div class="stat-label">ردیف معتبر</div><div class="stat-value">{{ faCount(preview.counts.valid) }}</div></article>
            <article class="card stat"><div class="stat-label">ردیف نامعتبر</div><div class="stat-value">{{ faCount(preview.counts.invalid) }}</div></article>
            <article class="card stat"><div class="stat-label">ردیف تکراری</div><div class="stat-value">{{ faCount(preview.counts.duplicate) }}</div></article>
          </section>
          <div v-if="preview.counts.duplicate" class="callout callout-info"><Icon name="alert" /><span><b>{{ faCount(preview.counts.duplicate) }} ردیف تکراری رد می‌شوند.</b> کد بیمار یا کد ملی این ردیف‌ها پیش‌تر در سامانه ثبت شده یا در همین فایل تکرار شده است.</span></div>
        </div>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th scope="col">ردیف</th><th scope="col">کد بیمار</th><th scope="col">کد ملی</th><th scope="col">نام و نام خانوادگی</th><th scope="col">تاریخ تولد</th><th scope="col">تلفن</th><th scope="col">وضعیت</th><th scope="col">توضیح</th></tr></thead>
            <tbody>
              <tr v-for="r in preview.rows" :key="r.line">
                <td data-label="ردیف" class="num">{{ fa(r.line) }}</td>
                <td data-label="کد بیمار"><span v-if="r.code" class="mono">{{ r.code }}</span><template v-else>خودکار</template></td>
                <td data-label="کد ملی"><span class="mono">{{ r.nationalId || '—' }}</span></td>
                <td data-label="نام و نام خانوادگی">{{ r.firstName }} {{ r.lastName }}</td>
                <td data-label="تاریخ تولد">{{ r.birthDate?.short ?? '—' }}</td>
                <td data-label="تلفن"><span class="mono">{{ r.phone || '—' }}</span></td>
                <td data-label="وضعیت"><span class="chip chip-plain" :class="stateChip[r.state][0]">{{ stateChip[r.state][1] }}</span></td>
                <td data-label="توضیح">{{ r.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="card-foot"><span>نمایش {{ faCount(preview.rows.length) }} ردیف از {{ faCount(preview.total) }} ردیف</span></div>
      </section>
      <div v-if="act.error.value" class="info-box mt-3" role="alert">{{ act.error.value }}</div>
      <form class="confirm-bar mt-6" @submit.prevent="confirm">
        <p><b>{{ faCount(preview.counts.valid) }} ردیف معتبر ثبت می‌شود.</b> ردیف‌های نامعتبر و تکراری ثبت نمی‌شوند.</p>
        <div class="confirm-actions">
          <button class="btn" type="button" @click="cancel">انصراف</button>
          <button v-if="preview.counts.valid > 0" class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="check" />تأیید و ثبت ردیف‌های معتبر</button>
        </div>
      </form>
    </template>
    <section v-else-if="!running" class="card" aria-labelledby="upload-h">
      <div class="card-head"><div><h3 id="upload-h">بارگذاری فایل</h3><p>فایل را با الگوی ثابت سامانه تهیه کنید تا ستون‌ها بدون تنظیم اضافی شناخته شوند.</p></div></div>
      <div class="card-body stack-lg">
        <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
        <div>
          <button class="btn" type="button" @click="downloadGet('/data/template.csv')"><Icon name="download" />دانلود الگوی CSV</button>
          <p v-if="data" class="text-xs-muted mt-3">ستون‌های الگو: {{ data.templateColumns.join('، ') }}. فقط «نام» و «نام خانوادگی» اجباری است. «کد بیمار» را به شکل P-000301 بنویسید یا خالی بگذارید تا خودکار داده شود. تاریخ تولد را به شکل ۱۳۶۸/۰۴/۱۲ بنویسید. حداکثر {{ faCount(data.maxRows) }} ردیف و ۵ مگابایت در هر بار.</p>
        </div>
        <form class="stack" @submit.prevent="upload">
          <DropZone id="csv-file" v-model="files" accept=".csv,text/csv" hint="فایل CSV بیماران · حداکثر ۵ مگابایت" required />
          <div><button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="upload" />بارگذاری و بررسی</button></div>
        </form>
      </div>
    </section>
  </section>

  <section v-if="can('patients')" aria-labelledby="export-h" class="mt-6">
    <h2 id="export-h" class="h2-lg">خروجی گرفتن از فهرست بیماران</h2>
    <section class="card" aria-labelledby="export-form-h">
      <div class="card-head"><div><h3 id="export-form-h">تنظیمات خروجی</h3><p>فهرست بیماران به صورت فایل Excel (راست‌به‌چپ) یا CSV دریافت می‌شود. خروجی نتیجه‌ی یک جستجو را از صفحه‌ی <RouterLink to="/search">جستجوی پیشرفته</RouterLink> بگیرید.</p></div></div>
      <div class="card-body">
        <form class="stack-lg" @submit.prevent="downloadPost('/data/exports/patients.xlsx', { status: exportStatus })">
          <div class="field"><label for="export-status">وضعیت بیمار</label>
            <select id="export-status" v-model="exportStatus" class="select"><option value="">همه‌ی بیماران</option><option v-for="(s, k) in STATUS" :key="k" :value="k">{{ s.label }}</option></select></div>
          <div class="flex-row">
            <button class="btn btn-primary" type="submit"><Icon name="download" />دانلود Excel (راست‌به‌چپ)</button>
            <button class="btn" type="button" @click="downloadPost('/data/exports/patients.csv', { status: exportStatus })">دانلود CSV</button>
          </div>
        </form>
      </div>
      <div class="callout callout-info"><Icon name="shield" /><span><b>همه‌ی خروجی‌ها در گزارش فعالیت ثبت می‌شوند.</b> فایل Excel با برگه‌ی راست‌به‌چپ باز می‌شود. فایل CSV جهت ندارد و Excel آن را چپ‌به‌راست نشان می‌دهد؛ برای ورود دوباره‌ی داده یا برنامه‌های دیگر مناسب است.</span></div>
    </section>
  </section>

  <section v-if="has('full_zip') && can('patients') && can('documents')" class="card zip-card mt-6" aria-labelledby="zip-h">
    <div class="zip-body">
      <h2 id="zip-h" class="zip-title">دریافت همه‌ی اطلاعات</h2>
      <p>یک فایل ZIP شامل این موارد دریافت می‌شود:</p>
      <ul class="zip-list">
        <li>یک نسخه‌ی کامل از پایگاه داده</li>
        <li>فایل <span class="mono">patients.csv</span> با فهرست همه‌ی بیماران</li>
        <li>پوشه‌ی هر بیمار همراه با فایل <span class="mono">info.csv</span> و پرونده‌های او</li>
      </ul>
      <p class="text-xs-muted">این فایل اطلاعات محرمانه‌ی بیماران را دارد. آن را در جای امن نگه دارید. آماده‌شدن آن ممکن است چند دقیقه طول بکشد.</p>
    </div>
    <form class="zip-action" @submit.prevent="downloadPost('/data/exports/full.zip')">
      <button class="btn btn-primary" type="submit"><Icon name="download" />دانلود فایل ZIP</button>
    </form>
  </section>
</template>
