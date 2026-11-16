<script setup lang="ts">
// Visits timeline (legacy views/visits/list.ejs): day bar on top, ranges, a day filter, visits grouped by day.
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import DayBar from '../../components/DayBar.vue';
import VisitItem from '../../components/VisitItem.vue';
import JalaliInput from '../../components/JalaliInput.vue';
import { api } from '../../api/client';
import { can, setTitle } from '../../lib/session';
import { fa, faCount } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('ویزیت‌ها');
const route = useRoute();
const router = useRouter();
const f = ref({ d: qs(route.query.d), status: qs(route.query.status), range: qs(route.query.range) });
const page = Number(qs(route.query.page)) || 1;
const actionError = ref('');
const { data, error, load } = useLoad(() => api.get('/visits', { ...f.value, page }));

function href(over: { range?: string; page?: number } = {}) {
  const q: Record<string, string> = {};
  if (over.range !== undefined) { if (over.range && over.range !== 'today') q.range = over.range; }
  else if (data.value?.dayInput) q.d = data.value.dayInput;
  else if (data.value?.rangeName && data.value.rangeName !== 'today') q.range = data.value.rangeName;
  if (f.value.status) q.status = f.value.status;
  if (over.page && over.page > 1) q.page = String(over.page);
  return { path: '/visits', query: q };
}
const days = computed(() => {
  const out: { date: any; items: any[] }[] = [];
  for (const v of data.value?.data ?? []) {
    const last = out[out.length - 1];
    if (last && last.date.iso === v.date.iso) last.items.push(v); else out.push({ date: v.date, items: [v] });
  }
  return out;
});
const title = computed(() => (data.value?.dayInput ? fa(data.value.dayInput) : (data.value?.ranges[data.value.rangeName] ?? '')));
function apply() {
  const q: Record<string, string> = {};
  if (f.value.d) q.d = f.value.d; else if (data.value?.rangeName) q.range = data.value.rangeName;
  if (f.value.status) q.status = f.value.status;
  router.push({ path: '/visits', query: q });
}
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Visits</span></div>
      <h1>ویزیت‌ها</h1>
      <p v-if="data">{{ faCount(data.pagination.total) }} ویزیت · {{ title }}</p>
    </div>
    <div class="page-actions">
      <RouterLink v-if="can('visits', 2)" class="btn btn-primary" to="/visits/new"><Icon name="plus" />ویزیت جدید</RouterLink>
    </div>
  </div>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <p v-if="actionError" class="info-box" role="alert">{{ actionError }}</p>
  <template v-if="data">
    <DayBar :bar="data.bar" :date-long="data.bar.long" />
    <section class="card">
      <div class="toolbar visit-toolbar">
        <div class="visit-ranges" role="group" aria-label="بازه‌ی زمانی">
          <RouterLink v-for="(label, key) in data.ranges" :key="key" class="chip chip-filter" :class="{ 'is-on': data.rangeName === key }"
            :to="href({ range: String(key) })" :aria-current="data.rangeName === key ? 'true' : undefined">{{ label }}</RouterLink>
        </div>
        <form class="visit-filters" @submit.prevent="apply">
          <div class="field-inline">
            <label for="vd">روز مشخص</label>
            <JalaliInput id="vd" v-model="f.d" placeholder="۱۴۰۳/۰۵/۱۲" />
          </div>
          <select v-model="f.status" class="select" aria-label="وضعیت">
            <option value="">همه‌ی وضعیت‌ها</option>
            <option value="scheduled">برنامه‌ریزی‌شده</option>
            <option value="done">انجام‌شده</option>
            <option value="cancelled">لغو‌شده</option>
          </select>
          <button class="btn btn-primary" type="submit">اعمال</button>
        </form>
      </div>
      <div v-if="!data.data.length" class="card-body"><p class="muted">ویزیتی در این بازه ثبت نشده است.</p></div>
      <template v-else>
        <section v-for="day in days" :key="day.date.iso" class="visit-day" :aria-label="day.date.long">
          <h2 class="day-head" :class="{ 'is-today': day.date.iso === data.today.iso }">
            <span class="day-num">{{ day.date.parts.day }}</span>
            <span class="day-meta"><small>{{ day.date.parts.weekday }}</small><b>{{ day.date.parts.month }} {{ day.date.parts.year }}</b></span>
            <span v-if="day.date.iso === data.today.iso" class="chip chip-ok chip-plain">امروز</span>
            <span class="day-count">{{ fa(day.items.length) }} ویزیت</span>
          </h2>
          <ul class="visit-list rail">
            <VisitItem v-for="v in day.items" :key="v.id" :v="v" show-patient :back="route.fullPath" @changed="load" @error="actionError = $event" />
          </ul>
        </section>
        <div v-if="data.pagination.pages > 1" class="card-foot">
          <span>صفحه‌ی {{ fa(data.pagination.page) }} از {{ fa(data.pagination.pages) }}</span>
          <div class="pagination">
            <RouterLink class="page-btn" :to="href({ page: Math.max(1, data.pagination.page - 1) })" aria-label="صفحه‌ی قبلی">&rsaquo;</RouterLink>
            <RouterLink class="page-btn" :to="href({ page: Math.min(data.pagination.pages, data.pagination.page + 1) })" aria-label="صفحه‌ی بعدی">&lsaquo;</RouterLink>
          </div>
        </div>
      </template>
    </section>
  </template>
</template>
