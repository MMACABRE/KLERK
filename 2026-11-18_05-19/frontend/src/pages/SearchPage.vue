<script setup lang="ts">
// Advanced search (legacy views/search/index.ejs, D22): up to six rules, AND/OR, a cycling status button, saved
// searches, Excel/CSV export. The URL keeps the legacy names (join, s, f1..f6, o1..o6, v1..v6, w1..w6).
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../components/Icon.vue';
import JalaliInput from '../components/JalaliInput.vue';
import { api, ApiError, downloadGet } from '../api/client';
import { can, setTitle } from '../lib/session';
import { fa, faCount, initialsOf, STATUS } from '../lib/fmt';
import { qs, useAction } from '../lib/usePage';

setTitle('جستجوی پیشرفته');
const route = useRoute();
const router = useRouter();
const meta = ref<any>(null);
const result = ref<any>(null);
const error = ref('');
const saved = ref<any[]>([]);
const saveName = ref('');
const saveAct = useAction();
const join = ref(qs(route.query.join) === 'or' ? 'or' : 'and');
const status = ref(qs(route.query.s));
const rules = ref(Array.from({ length: 6 }, (_, i) => ({ field: qs(route.query[`f${i + 1}`]), op: qs(route.query[`o${i + 1}`]), value: qs(route.query[`v${i + 1}`]), value2: qs(route.query[`w${i + 1}`]) })));
const STATUS_COLOR: Record<string, string> = { '': 'chip-info', active: 'chip-ok', pending: 'chip-warn', critical: 'chip-crit', archived: 'chip-mute' };
const statusKeys = ['', 'active', 'pending', 'critical', 'archived'];
const statusName = (k: string) => (k ? STATUS[k].label : 'همه');

const fieldMap = computed<Record<string, any>>(() => Object.fromEntries((meta.value?.fields ?? []).map((f: any) => [f.key, f])));
const opLabels = computed<Record<string, string>>(() => Object.assign({}, ...Object.values(meta.value?.operators ?? {})));
function opsFor(r: any) {
  const f = fieldMap.value[r.field];
  if (!f) return Object.keys(opLabels.value);
  return r.op && !f.ops.includes(r.op) && opLabels.value[r.op] ? [...f.ops, r.op] : f.ops;
}
function onField(r: any) {
  const f = fieldMap.value[r.field];
  if (f && !f.ops.includes(r.op)) r.op = f.ops[0];
  if (f?.choices && !f.choices.some(([c]: [string]) => c === r.value)) r.value = '';
}

function params() {
  const p: Record<string, string> = { join: join.value };
  rules.value.forEach((r, i) => {
    for (const [k, v] of [['f', r.field], ['o', r.op], ['v', r.value], ['w', r.op === 'between' ? r.value2 : '']]) if (v) p[`${k}${i + 1}`] = v;
  });
  if (status.value) p.s = status.value;
  return p;
}
const pageNo = Number(qs(route.query.page)) || 1;

async function boot() {
  try {
    meta.value = await api.get('/search/fields');
    saved.value = (await api.get('/search/saved')).data;
    if ('join' in route.query) {
      result.value = await api.get('/search', { ...route.query, page: pageNo });
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.';
    if (e instanceof ApiError && e.data.summary) result.value = { summary: e.data.summary, results: null };
  }
}
boot();
const run = () => router.push({ path: '/search', query: params() });
const pageTo = (n: number) => ({ path: '/search', query: { ...params(), ...(n > 1 ? { page: String(n) } : {}) } });
function cycle() {
  status.value = statusKeys[(statusKeys.indexOf(status.value) + 1) % statusKeys.length];
}
async function save() {
  const out = await saveAct.run(() => api.post('/search/saved', { ...params(), name: saveName.value }));
  if (out) { saveName.value = ''; saved.value = (await api.get('/search/saved')).data; router.push({ path: '/search', query: out.params }); }
}
async function openSaved(id: number) {
  const out = await api.get(`/search/saved/${id}`);
  router.push({ path: '/search', query: out.params });
}
async function delSaved(id: number) {
  await api.del(`/search/saved/${id}`);
  saved.value = (await api.get('/search/saved')).data;
}
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Advanced Search</span></div>
      <h1>جستجوی پیشرفته</h1>
      <p>شرط‌های چندگانه بسازید تا بیماران موردنظر را پیدا کنید. جستجوهای پرکاربرد را برای استفاده‌ی دوباره ذخیره کنید.</p>
    </div>
    <div class="page-actions"><button class="btn btn-primary" type="submit" form="qb-form">اجرای جستجو</button></div>
  </div>
  <div v-if="meta" class="grid grid-main">
    <div>
      <form id="qb-form" @submit.prevent="run">
        <section class="qb-group" aria-labelledby="qb-h">
          <h2 id="qb-h" class="mb-3">شرط‌ها</h2>
          <div v-if="error" class="info-box" role="alert">{{ error }}</div>
          <div class="qb-bar">
            <div class="qb-op join-opts" role="radiogroup" aria-label="ترکیب شرط‌ها">
              <label class="join-opt"><input v-model="join" type="radio" value="and">همه‌ی شرط‌ها</label>
              <label class="join-opt"><input v-model="join" type="radio" value="or">هر یک از شرط‌ها</label>
            </div>
            <label class="qb-status-wrap"><span class="text-sm-muted">وضعیت پرونده</span>
              <button type="button" class="chip qb-status-btn" :class="STATUS_COLOR[status] ?? 'chip-info'" :aria-label="`وضعیت پرونده: ${statusName(status)}. برای تغییر بزنید.`" @click="cycle">{{ statusName(status) }}</button>
            </label>
          </div>
          <p class="text-sm-muted">فقط ردیف‌هایی که فیلد و مقدار دارند در جستجو به‌کار می‌روند. با دکمه‌ی «وضعیت پرونده» نتیجه را به یک وضعیت محدود کنید.</p>
          <div v-for="(r, i) in rules" :key="i" class="qb-rule rule-flat">
            <select v-model="r.field" class="select" :aria-label="`فیلد شرط ${fa(i + 1)}`" @change="onField(r)">
              <option value="">انتخاب فیلد</option>
              <option v-for="f in meta.fields.filter((x: any) => !x.hidden || r.field === x.key)" :key="f.key" :value="f.key">{{ f.label }}</option>
            </select>
            <select v-model="r.op" class="select" :aria-label="`عملگر شرط ${fa(i + 1)}`">
              <option v-if="!fieldMap[r.field]" value="">عملگر</option>
              <option v-for="k in opsFor(r)" :key="k" :value="k">{{ opLabels[k] }}</option>
            </select>
            <div v-if="fieldMap[r.field]?.choices" class="qb-choices" role="group" aria-label="مقدار">
              <button v-for="[val, label] in fieldMap[r.field].choices" :key="val" type="button" class="qb-choice" :aria-pressed="r.value === val ? 'true' : 'false'" @click="r.value = r.value === val ? '' : val">{{ label }}</button>
            </div>
            <template v-else-if="fieldMap[r.field]?.type === 'date'">
              <JalaliInput v-model="r.value" :placeholder="r.op === 'between' ? 'از' : '۱۴۰۳/۰۵/۱۲'" />
              <JalaliInput v-if="r.op === 'between'" v-model="r.value2" placeholder="تا" />
            </template>
            <template v-else>
              <input v-model="r.value" class="input" type="text" :placeholder="r.op === 'between' ? 'از' : 'مقدار'" :aria-label="`مقدار شرط ${fa(i + 1)}`" dir="auto" maxlength="100">
              <input v-if="r.op === 'between'" v-model="r.value2" class="input" type="text" placeholder="تا" :aria-label="`مقدار دوم شرط ${fa(i + 1)}`" dir="auto" maxlength="100">
            </template>
          </div>
        </section>
      </form>
      <section v-if="result?.results" class="card mt-6" aria-labelledby="res-h">
        <div class="toolbar">
          <span id="res-h" class="bold-text">{{ faCount(result.results.pagination.total) }} بیمار یافت شد</span>
          <template v-if="result.results.pagination.total > 0 && can('data')">
            <button class="btn btn-sm" type="button" @click="downloadGet('/search/export.xlsx', result.params)"><Icon name="download" />خروجی Excel</button>
            <button class="btn btn-sm btn-ghost" type="button" @click="downloadGet('/search/export.csv', result.params)">CSV</button>
          </template>
        </div>
        <div v-if="!result.results.data.length" class="card-body"><p class="muted">بیماری با این شرط‌ها پیدا نشد.</p></div>
        <template v-else>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th scope="col">بیمار</th><th scope="col">کد بیمار</th><th scope="col">سن</th><th scope="col">آخرین به‌روزرسانی</th><th scope="col">وضعیت</th></tr></thead>
              <tbody>
                <tr v-for="p in result.results.data" :key="p.id">
                  <td data-label="بیمار"><div class="person"><span class="avatar avatar-sm">{{ initialsOf(p.firstName, p.lastName) }}</span><RouterLink :to="`/patients/${p.code}`"><b>{{ p.firstName }} {{ p.lastName }}</b></RouterLink></div></td>
                  <td data-label="کد بیمار" class="mono">{{ p.code }}</td>
                  <td data-label="سن" class="num">{{ p.age === null ? '—' : fa(p.age) }}</td>
                  <td data-label="آخرین به‌روزرسانی"><span class="text-sm">{{ p.updatedDay?.short }}</span></td>
                  <td data-label="وضعیت"><span class="chip chip-plain" :class="STATUS[p.status].chip">{{ STATUS[p.status].label }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="card-foot">
            <span class="text-sm-muted">نمایش {{ faCount((result.results.pagination.page - 1) * result.results.pagination.pageSize + 1) }} تا {{ faCount(Math.min(result.results.pagination.total, result.results.pagination.page * result.results.pagination.pageSize)) }} از {{ faCount(result.results.pagination.total) }} نتیجه</span>
            <nav v-if="result.results.pagination.pages > 1" class="pagination" aria-label="صفحه‌بندی نتایج">
              <RouterLink class="page-btn" :to="pageTo(Math.max(1, result.results.pagination.page - 1))">قبلی</RouterLink>
              <span class="page-btn" aria-current="page">{{ fa(result.results.pagination.page) }} از {{ fa(result.results.pagination.pages) }}</span>
              <RouterLink class="page-btn" :to="pageTo(Math.min(result.results.pagination.pages, result.results.pagination.page + 1))">بعدی</RouterLink>
            </nav>
          </div>
        </template>
      </section>
    </div>
    <div class="stack-lg">
      <section id="saved-h" class="card" aria-labelledby="saved-title">
        <div class="card-head"><h2 id="saved-title">جستجوهای ذخیره‌شده</h2></div>
        <form class="saved-form" @submit.prevent="save">
          <div v-if="saveAct.error.value" class="info-box" role="alert">{{ saveAct.error.value }}</div>
          <div class="field"><label for="save-name">نام جستجو</label><input id="save-name" v-model="saveName" class="input" type="text" maxlength="80" placeholder="مثلاً: بیماران بحرانی سالمند" required></div>
          <button class="btn btn-block" type="submit" :disabled="saveAct.busy.value">ذخیره‌ی جستجوی فعلی</button>
        </form>
        <div v-if="!saved.length" class="card-body"><p class="muted">هنوز جستجویی ذخیره نشده است.</p></div>
        <ul v-else class="list list-no-pad">
          <li v-for="s in saved" :key="s.id" class="list-item-col">
            <b class="text-sm">{{ s.name }}</b>
            <span class="text-xs-muted">ذخیره‌شده توسط {{ s.owner || 'کاربر حذف‌شده' }}<template v-if="s.created">، {{ s.created.short }}</template></span>
            <div class="saved-actions">
              <button class="btn btn-sm" type="button" @click="openSaved(s.id)">اجرا</button>
              <button class="btn btn-sm btn-ghost" type="button" :aria-label="`حذف جستجوی ${s.name}`" @click="delSaved(s.id)">حذف</button>
            </div>
          </li>
        </ul>
      </section>
      <section class="card card-flat" aria-labelledby="tips-h">
        <div class="card-head"><h2 id="tips-h">نکات</h2></div>
        <ul class="list list-no-pad">
          <li class="list-item-col"><b class="text-sm">مقدارهای فهرستی</b><span class="text-xs-muted">برای جنسیت و گروه خونی بعد از انتخاب فیلد، دکمه‌های مقدار نشان داده می‌شود.</span></li>
          <li class="list-item-col"><b class="text-sm">سن و تاریخ</b><span class="text-xs-muted">برای سن از «کمتر از»، «بیشتر از» یا «بین» استفاده کنید. تاریخ را به شکل ۱۴۰۳/۰۵/۱۲ بنویسید.</span></li>
          <li class="list-item-col"><b class="text-sm">بایگانی‌شده‌ها</b><span class="text-xs-muted">در حالت «همه» نتایج شامل بیماران بایگانی‌شده هم می‌شود. دکمه‌ی «وضعیت پرونده» را بزنید تا بین همه، فعال، در انتظار، بحرانی و بایگانی‌شده بچرخد.</span></li>
        </ul>
      </section>
      <section v-if="result?.summary" class="card" aria-labelledby="sum-h">
        <div class="card-head"><h2 id="sum-h">خلاصه‌ی جستجو</h2></div>
        <div class="card-body"><div class="code-block">{{ result.summary }}</div></div>
      </section>
    </div>
  </div>
</template>
