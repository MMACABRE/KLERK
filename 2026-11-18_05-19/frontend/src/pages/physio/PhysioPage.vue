<script setup lang="ts">
// Patients with an unfinished physiotherapy course (SPEC §15.6): longest wait first, search by name or code, and
// users with physio edit tick and untick right in the list.
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import Pager from '../../components/Pager.vue';
import PhysioBoxes from '../../components/PhysioBoxes.vue';
import PhysioDialogs from '../../components/PhysioDialogs.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { fa, faCount, initialsOf } from '../../lib/fmt';
import { qs, useLoad } from '../../lib/usePage';

setTitle('فیزیوتراپی');
const route = useRoute();
const router = useRouter();
const q = ref(qs(route.query.q));
const page = Number(qs(route.query.page)) || 1;
const { data, error, loading, load } = useLoad(() => api.get('/physio', { q: q.value, page }));
const dialogs = ref<InstanceType<typeof PhysioDialogs> | null>(null);
const notice = ref('');

function query(p = 1) {
  const out: Record<string, string> = {};
  if (q.value) out.q = q.value;
  if (p > 1) out.page = String(p);
  return { path: '/physio', query: out };
}
const ago = (r: any) => {
  const days = Math.round((Date.now() - new Date(`${r.since.iso}T00:00:00`).getTime()) / 86400000);
  return days <= 0 ? 'امروز' : `${fa(days)} روز پیش`;
};
const courseOf = (r: any) => ({ id: r.courseId, dates: r.dates });
function failed(message: string) { notice.value = message; }
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Physiotherapy</span></div>
      <h1>فیزیوتراپی</h1>
      <p v-if="data">{{ faCount(data.pagination.total) }} بیمار با دوره‌ی ناتمام</p>
    </div>
  </div>
  <p v-if="notice" class="info-box" role="alert">{{ notice }}</p>

  <section class="card">
    <form @submit.prevent="router.push(query(1))">
      <div class="toolbar">
        <div class="input-group flex-1-240-420">
          <Icon name="search" />
          <input v-model="q" class="input" type="search" placeholder="نام یا کد بیمار" aria-label="جستجو در فیزیوتراپی" autocomplete="off">
        </div>
        <button class="btn btn-primary" type="submit">جستجو</button>
      </div>
    </form>

    <div v-if="loading && !data" class="card-body"><p class="muted">در حال بارگذاری…</p></div>
    <div v-else-if="error" class="card-body"><p class="info-box" role="alert">{{ error }}</p></div>
    <div v-else-if="!data.data.length" class="card-body">
      <p class="muted">{{ data.q ? 'بیماری با این مشخصات دوره‌ی ناتمام ندارد.' : 'همه‌ی دوره‌ها تمام شده‌اند.' }}</p>
    </div>
    <template v-else>
      <div class="table-wrap">
        <table class="table ps-table">
          <thead><tr><th scope="col">بیمار</th><th scope="col">کد بیمار</th><th scope="col">جلسه‌ها</th><th scope="col">آخرین جلسه</th></tr></thead>
          <tbody>
            <tr v-for="r in data.data" :key="r.courseId">
              <td data-label="بیمار"><div class="person"><span class="avatar avatar-sm">{{ initialsOf(r.firstName, r.lastName) }}</span><div><RouterLink :to="`/patients/${r.code}#physio`"><b>{{ r.firstName }} {{ r.lastName }}</b></RouterLink><span class="ps-count">{{ fa(r.done) }} از {{ fa(r.sessions) }}</span></div></div></td>
              <td data-label="کد بیمار" class="mono">{{ r.code }}</td>
              <td data-label="جلسه‌ها"><PhysioBoxes :sessions="r.sessions" :dates="r.dates" :edit="data.canEdit" @tick="notice = ''; dialogs?.tick(courseOf(r))" @untick="notice = ''; dialogs?.untick(courseOf(r))" /></td>
              <td data-label="آخرین جلسه">
                <span class="ps-last" :class="{ 'is-old': r.idle }">{{ r.last ? `${fa(r.last.input)} · ${ago(r)}` : `بدون جلسه · دوره از ${fa(r.since.input)}` }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-foot">
        <span>نمایش {{ faCount((data.pagination.page - 1) * data.pagination.pageSize + 1) }} تا {{ faCount(Math.min(data.pagination.total, data.pagination.page * data.pagination.pageSize)) }} از {{ faCount(data.pagination.total) }} بیمار</span>
        <Pager :page="data.pagination.page" :pages="data.pagination.pages" :to="(n) => query(n)" />
      </div>
    </template>
  </section>
  <PhysioDialogs ref="dialogs" @changed="load" @error="failed" />
</template>
