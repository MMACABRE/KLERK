<script setup lang="ts">
// Dashboard (legacy views/home.ejs + views/dashboard/*, D54) with its edit mode (layout flag): move, resize, hide and
// add widgets and quick buttons, then save. Every edit action works on one draft and one save (BUG-1 fixed here).
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../components/Icon.vue';
import ClockCard from '../components/ClockCard.vue';
import GripButton from '../components/GripButton.vue';
import { useDragList } from '../lib/dragList';
import { api } from '../api/client';
import { has, setTitle } from '../lib/session';
import { fa, faCount, initialsOf, STATUS, visitState } from '../lib/fmt';
import { useAction, useLoad } from '../lib/usePage';

setTitle('');
const route = useRoute();
const router = useRouter();
const editing = computed(() => route.query.edit === '1' && has('layout'));
const draft = ref<{ widgets: { id: string; size: string }[]; quick: string[] } | null>(null);
const act = useAction();
const { data, load } = useLoad(async () => {
  const d = await api.get('/dashboard', editing.value ? { edit: '1' } : {});
  draft.value = { widgets: d.layout.widgets.map((w: any) => ({ ...w })), quick: [...d.layout.quick] };
  return d;
});
const byId = computed<Record<string, any>>(() => Object.fromEntries((data.value?.widgets ?? []).map((w: any) => [w.id, w])));
const catW = computed<Record<string, any>>(() => Object.fromEntries((data.value?.catalogue.widgets ?? []).map((w: any) => [w.id, w])));
const catQ = computed<Record<string, any>>(() => Object.fromEntries((data.value?.catalogue.quick ?? []).map((q: any) => [q.id, q])));
const shown = computed<any[]>(() => (editing.value ? draft.value?.widgets ?? [] : data.value?.widgets ?? []));
const removedW = computed(() => (data.value?.catalogue.widgets ?? []).filter((w: any) => !draft.value?.widgets.some((x) => x.id === w.id)));
const removedQ = computed(() => (data.value?.catalogue.quick ?? []).filter((q: any) => !draft.value?.quick.includes(q.id)));
const dirty = computed(() => data.value && JSON.stringify({ v: 1, ...draft.value }) !== JSON.stringify(data.value.layout));
const quickTiles = computed<any[]>(() => {
  const tiles = byId.value.quick?.data?.tiles ?? [];
  if (!editing.value) return tiles;
  const all = Object.fromEntries(tiles.map((t: any) => [t.id, t]));
  return (draft.value?.quick ?? []).map((id) => all[id] ?? { ...catQ.value[id], text: '', locked: false });
});
const sizeText = (s: string) => fa(s.replace('x', '×'));

// Drag and drop (pointer and keyboard) on the widget grid and on the quick buttons; a live region says the moves.
const live = ref('');
const say = (t: string) => { live.value = t; };
const dragW = useDragList({
  ns: 'w', groups: () => (draft.value ? [{ key: 'grid', items: draft.value.widgets }] : []),
  idOf: (w) => w.id, label: (id) => catW.value[id]?.label ?? id, say,
});
const dragQ = useDragList({
  ns: 'q', groups: () => (draft.value ? [{ key: 'quick', items: draft.value.quick }] : []),
  idOf: (id) => id, label: (id) => catQ.value[id]?.title ?? id, say,
});
function sizeW(w: { id: string; size: string }) {
  const sizes = catW.value[w.id].sizes;
  w.size = sizes[(sizes.indexOf(w.size) + 1) % sizes.length];
}
const hideW = (i: number) => draft.value!.widgets.splice(i, 1);
const addW = (id: string) => draft.value!.widgets.push({ id, size: catW.value[id].sizes[0] });
const hideQ = (i: number) => draft.value!.quick.splice(i, 1);
const addQ = (id: string) => draft.value!.quick.push(id);

async function save() {
  if (await act.run(() => api.put('/dashboard/layout', { layout: { v: 1, ...draft.value } }), 'چیدمان ذخیره شد.')) load();
}
async function undo() {
  const out = await act.run(() => api.post('/dashboard/layout/undo'));
  if (out) { act.notice.value = out.undone ? 'چیدمان قبلی برگشت.' : 'چیدمان قبلی وجود ندارد.'; load(); }
}
async function reset() {
  if (await act.run(() => api.post('/dashboard/layout/reset'), 'چیدمان به پیش‌فرض برگشت.')) load();
}
const toggleEdit = () => router.push(editing.value ? '/' : { path: '/', query: { edit: '1' } });
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">DashBoard</span></div>
      <h1>داشبورد</h1>
      <p>خلاصه‌ی وضعیت پرونده‌ها و کارهایی که نیاز به پیگیری دارند.</p>
      <div v-if="has('layout')" class="page-actions dash-actions">
        <button v-if="editing" class="btn btn-ink" type="button" aria-current="true" @click="toggleEdit"><Icon name="check" />پایان چیدمان</button>
        <button v-else class="btn" type="button" @click="toggleEdit"><Icon name="layout" />چیدمان</button>
      </div>
    </div>
    <ClockCard />
  </div>
  <div v-if="route.query.denied === '1'" class="info-box" role="alert">شما اجازه‌ی دسترسی به این بخش را ندارید.</div>
  <div v-if="act.notice.value" class="info-box" role="status">{{ act.notice.value }}</div>
  <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>

  <template v-if="editing">
    <p id="pl-help" class="sr-only">برای جابه‌جایی با صفحه‌کلید: فاصله یا Enter را بزنید، با کلیدهای جهت جابه‌جا کنید، Enter برای گذاشتن و Esc برای لغو.</p>
    <div class="sr-only" aria-live="polite">{{ live }}</div>
  </template>
  <div v-if="data" class="dash-grid" :class="{ 'is-editing': editing }" data-w-group="grid">
    <div v-for="(w, i) in shown" :key="w.id" class="dash-cell" :class="{ 'pl-ph': dragW.lifted.value === w.id, 'is-kb': dragW.carried.value === w.id }" :data-widget="w.id" :data-size="w.size" :data-w-id="editing ? w.id : undefined">
      <div v-if="editing" class="pl-w-head">
        <GripButton :label="`جابه‌جایی «${catW[w.id].label}»`" @pointerdown="dragW.down($event, w.id)" @keydown="dragW.key($event, w.id)" @blur="dragW.blur()" />
        <b>{{ catW[w.id].label }}</b>
        <span class="pl-w-tools">
          <button type="button" class="pl-size" :aria-label="`اندازه‌ی «${catW[w.id].label}»، برای اندازه‌ی بعدی بزنید`" @click="sizeW(w)">{{ sizeText(w.size) }}</button>
          <button type="button" class="pl-x" :aria-label="`برداشتن «${catW[w.id].label}»`" @click="hideW(i)"><Icon name="x" /></button>
        </span>
      </div>
      <template v-if="!byId[w.id] || byId[w.id].locked">
        <div v-if="editing" class="pl-locked">{{ byId[w.id]?.locked ? 'برای دیدن این بخش دسترسی ندارید' : 'پس از ذخیره نشان داده می‌شود.' }}</div>
      </template>
      <section v-else-if="byId[w.id].data === null" class="card"><p class="muted card-body">این بخش امروز چیزی برای نشان دادن ندارد.</p></section>
      <template v-else>
        <section v-if="w.id === 'quick'" class="quick" aria-labelledby="qa-h">
          <h2 id="qa-h">دسترسی سریع</h2>
          <div class="qa-grid" :class="{ 'qa-admin': quickTiles.length > 5 }" data-q-group="quick">
            <template v-for="(t, qi) in quickTiles" :key="t.id">
              <span v-if="t.locked || editing" class="qa-tile" :class="{ 'qa-primary': qi === 0 && !t.locked, 'pl-ph': dragQ.lifted.value === t.id, 'is-kb': dragQ.carried.value === t.id }" :aria-disabled="t.locked ? 'true' : undefined" :data-q-id="editing ? t.id : undefined">
                <span v-if="editing" class="pl-qa-tools">
                  <GripButton :label="`جابه‌جایی دکمه‌ی «${t.title}»`" @pointerdown="dragQ.down($event, t.id)" @keydown="dragQ.key($event, t.id)" @blur="dragQ.blur()" />
                  <button type="button" class="pl-x" :aria-label="`برداشتن دکمه‌ی «${t.title}»`" @click="hideQ(qi)"><Icon name="x" /></button>
                </span>
                <span class="qa-icon"><Icon :name="t.icon" /></span>
                <span class="qa-text"><b>{{ t.title }}</b><span>{{ t.locked ? 'برای دیدن این بخش دسترسی ندارید' : t.text }}</span></span>
              </span>
              <RouterLink v-else class="qa-tile" :class="{ 'qa-primary': t.primary }" :to="t.href">
                <span class="qa-icon"><Icon :name="t.icon" /></span>
                <span class="qa-text"><b>{{ t.title }}</b><span>{{ t.text }}</span></span>
              </RouterLink>
            </template>
            <div v-if="editing && removedQ.length" class="pl-qa-add">
              <ul class="pl-chips"><li v-for="q in removedQ" :key="q.id"><button type="button" class="pl-chip" @click="addQ(q.id)"><Icon name="plus" /><span>{{ q.title }}</span></button></li></ul>
            </div>
          </div>
        </section>
        <article v-else-if="w.id === 'active'" class="card stat"><div class="stat-label">بیماران فعال <span class="stat-icon"><Icon name="users" /></span></div><div class="stat-value">{{ faCount(byId[w.id].data.n) }}</div><div class="stat-delta">از {{ faCount(byId[w.id].data.total) }} پرونده</div></article>
        <article v-else-if="w.id === 'pending'" class="card stat"><div class="stat-label">در انتظار <span class="stat-icon"><Icon name="file" /></span></div><div class="stat-value">{{ faCount(byId[w.id].data.n) }}</div><div class="stat-delta">پرونده‌ی ناقص یا نیازمند بررسی</div></article>
        <article v-else-if="w.id === 'critical'" class="card stat"><div class="stat-label">بحرانی <span class="stat-icon"><Icon name="pulse" /></span></div><div class="stat-value">{{ faCount(byId[w.id].data.n) }}</div><div class="stat-delta">نیازمند توجه فوری</div></article>
        <RouterLink v-else-if="w.id === 'income_today'" class="card income-today" to="/finance">
          <span class="qa-icon"><Icon name="wallet" /></span>
          <span><span class="stat-label">درآمد امروز</span><b class="money">{{ byId[w.id].data.total.display }}</b></span>
          <span class="muted">{{ faCount(byId[w.id].data.count) }} پرداخت</span>
        </RouterLink>
        <section v-else-if="w.id === 'alerts'" class="card alerts-card" aria-labelledby="al-h">
          <div class="card-head"><div><h2 id="al-h">هشدارها</h2><p>{{ faCount(byId[w.id].data.length) }} هشدار انبار</p></div><RouterLink class="btn btn-sm" to="/storage?f=alert">همه در انبار</RouterLink></div>
          <ul class="alert-list"><li v-for="(a, ai) in byId[w.id].data.slice(0, 12)" :key="ai" class="alert-row" :class="`alert-${a.level}`"><span class="alert-dot" aria-hidden="true"></span><RouterLink :to="`/storage/items/${a.itemId}`">{{ a.name }}</RouterLink><span>{{ a.text }}</span><span class="sr-only">{{ a.level === 'crit' ? '(فوری)' : '(هشدار)' }}</span></li></ul>
        </section>
        <section v-else-if="w.id === 'sms'" class="card alerts-card" aria-labelledby="sms-h">
          <div class="card-head"><div><h2 id="sms-h">پیامک</h2><p>نیاز به توجه</p></div><RouterLink class="btn btn-sm" to="/sms">گزارش پیامک</RouterLink></div>
          <ul class="alert-list">
            <li v-if="byId[w.id].data.noKey" class="alert-row alert-crit"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms/settings">کلید پیامک ثبت نشده یا خوانده نمی‌شود</RouterLink></li>
            <li v-if="byId[w.id].data.low !== null" class="alert-row alert-crit"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms">اعتبار پیامک رو به پایان است</RouterLink><span>{{ faCount(byId[w.id].data.low) }} پیام مانده</span></li>
            <li v-if="byId[w.id].data.failed" class="alert-row alert-warn"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms?status=failed">{{ faCount(byId[w.id].data.failed) }} پیام در ۲۴ ساعت گذشته ناموفق بود</RouterLink></li>
          </ul>
        </section>
        <section v-else-if="w.id === 'today_visits'" class="card today-visits" aria-labelledby="tv-h">
          <div class="card-head">
            <div><h2 id="tv-h">ویزیت‌های امروز</h2><p>{{ faCount(byId[w.id].data.length) }} ویزیت</p></div>
            <div class="today-links">
              <RouterLink class="chip chip-filter" to="/visits?range=tomorrow">فردا</RouterLink>
              <RouterLink class="chip chip-filter" to="/visits?range=week">۷ روز آینده</RouterLink>
              <RouterLink class="chip chip-filter" to="/visits?range=month">این ماه</RouterLink>
              <RouterLink class="btn btn-sm" to="/visits">همه‌ی ویزیت‌ها</RouterLink>
            </div>
          </div>
          <div v-if="!byId[w.id].data.length" class="card-body"><p class="muted">امروز ویزیتی ثبت نشده است.</p></div>
          <ul v-else class="visit-list visit-compact rail">
            <li v-for="v in byId[w.id].data.slice(0, 30)" :key="v.id" class="visit" :class="[`visit-${v.status}`, { 'visit-overdue': v.overdue, 'visit-now': v.ongoing }]">
              <div class="visit-when"><b class="mono">{{ fa(v.time) }}</b><span>تا <span class="mono">{{ fa(v.until) }}</span></span></div>
              <div class="visit-body"><RouterLink class="visit-patient" :to="`/patients/${v.patient.code}`">{{ v.patient.firstName }} {{ v.patient.lastName }}</RouterLink><span class="visit-reason">{{ v.reason || 'بدون شرح' }}</span></div>
              <span class="chip" :class="visitState(v).chip">{{ visitState(v).label }}</span>
            </li>
          </ul>
        </section>
        <section v-else-if="w.id === 'recent'" class="card" aria-labelledby="rp-h">
          <div class="card-head"><div><h2 id="rp-h">آخرین پرونده‌های به‌روزشده</h2><p>۸ پرونده‌ی اخیر</p></div><RouterLink class="btn btn-sm" to="/patients">فهرست بیماران</RouterLink></div>
          <div v-if="!byId[w.id].data.length" class="card-body"><p class="muted">هنوز بیماری ثبت نشده است.</p></div>
          <div v-else class="table-wrap">
            <table class="table">
              <thead><tr><th scope="col">بیمار</th><th scope="col">کد</th><th scope="col">آخرین تغییر</th><th scope="col">وضعیت</th></tr></thead>
              <tbody>
                <tr v-for="p in byId[w.id].data" :key="p.id">
                  <td data-label="بیمار"><div class="person"><span class="avatar avatar-sm">{{ initialsOf(p.firstName, p.lastName) }}</span><b><RouterLink :to="`/patients/${p.code}`">{{ p.firstName }} {{ p.lastName }}</RouterLink></b></div></td>
                  <td data-label="کد" class="mono">{{ p.code }}</td>
                  <td data-label="آخرین تغییر">{{ p.updatedDay?.long }}</td>
                  <td data-label="وضعیت"><span class="chip" :class="STATUS[p.status].chip">{{ STATUS[p.status].label }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>
    <div v-if="editing && removedW.length" class="dash-cell" data-size="1x1">
      <div class="pl-w-add">
        <span class="pl-w-add-title"><Icon name="plus" />افزودن کارت</span>
        <ul class="pl-chips"><li v-for="r in removedW" :key="r.id"><button type="button" class="pl-chip" @click="addW(r.id)"><Icon name="plus" /><span>{{ r.label }}</span></button></li></ul>
      </div>
    </div>
  </div>
  <div v-if="editing && data" class="pl-draft">
    <span class="pl-draft-state">{{ dirty ? 'تغییرات ذخیره نشده' : 'بدون تغییر' }}</span>
    <span class="pl-draft-btns">
      <button class="btn btn-ghost pl-wide" type="button" :disabled="act.busy.value" @click="reset">بازگشت به پیش‌فرض</button>
      <button class="btn btn-ghost pl-wide" type="button" :disabled="!data.hasPrevious || act.busy.value" @click="undo">چیدمان قبلی</button>
      <button class="btn btn-primary" type="button" :disabled="!dirty || act.busy.value" @click="save"><Icon name="check" />ذخیره</button>
    </span>
  </div>
  <!-- Under 900 px the draft bar keeps only Save; these two move here (legacy .pl-foot). -->
  <div v-if="editing && data" class="pl-foot">
    <button class="btn" type="button" :disabled="act.busy.value" @click="reset">بازگشت به پیش‌فرض</button>
    <button class="btn" type="button" :disabled="!data.hasPrevious || act.busy.value" @click="undo">چیدمان قبلی</button>
  </div>
</template>
