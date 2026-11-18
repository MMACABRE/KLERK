<script setup lang="ts">
// Dashboard (legacy views/home.ejs + views/dashboard/*, D54; layout v2, ADR-0014). Owner decision 2026-11-17, option
// «الف»: the dashboard works like a phone home screen. Every widget and tile keeps the cell it was put in, empty cells
// stay empty, and from 600 px the view and the editor show the same grid, whose column count grows with the window
// (8 up to 1440 px, up to 16 when zoomed out: more room to place things). Edit mode (layout flag, 600 px and wider):
// drag a card anywhere; the cards it would cover slide to the nearest free spot. Tap a card for a handle on each edge
// to resize it (neighbours slide away too); × removes it; the add list puts a card in the first free spot; then save.
// Keyboard: see lib/gridEditor.ts.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router';
import type { RouteLocationNormalized } from 'vue-router';
import Icon from '../components/Icon.vue';
import ClockCard from '../components/ClockCard.vue';
import GripButton from '../components/GripButton.vue';
import JalaliInput from '../components/JalaliInput.vue';
import PhysioBoxes from '../components/PhysioBoxes.vue';
import { api } from '../api/client';
import { has, setTitle } from '../lib/session';
import { fa, faCount, initialsOf, STATUS, visitState } from '../lib/fmt';
import { useAction, useLoad } from '../lib/usePage';
import { cellVars as place, colsFor, COLS, emptyCells, firstFree, fitTo, ROWS, rowsUsed } from '../lib/grid-math';
import type { Item } from '../lib/grid-math';
import { useGridEditor } from '../lib/gridEditor';
import type { Side } from '../lib/gridEditor';
import * as jc from '../lib/jalali-math';

setTitle('');
const route = useRoute();
const router = useRouter();
const editing = computed(() => route.query.edit === '1' && has('layout'));
const draft = ref<Item[]>([]);
const cellsKey = (items: Item[]) => [...items].sort((a, b) => a.id.localeCompare(b.id)).map((i) => `${i.id}:${i.x},${i.y},${i.w}x${i.h}`).join('|');
let initial = '';
const act = useAction();
const pick = (i: Item) => ({ id: i.id, x: i.x, y: i.y, w: i.w, h: i.h });
const { data, load } = useLoad(async () => {
  const d = await api.get('/dashboard', editing.value ? { edit: '1' } : {});
  draft.value = d.layout.items.map(pick);
  initial = cellsKey(draft.value);
  return d;
});

// Editing works from 600 px (owner, 2026-11-17: a laptop window narrower than 1200 px could not edit); phones keep
// the one-column flow and show the notice instead.
const wideQuery = window.matchMedia('(min-width: 600px)');
const wide = ref(wideQuery.matches);
const onWide = () => { wide.value = wideQuery.matches; };
onMounted(() => wideQuery.addEventListener('change', onWide));
const arranging = computed(() => editing.value && wide.value);

// The column count follows the grid's own width (zooming out widens it), the same for the view and the editor.
const gridEl = ref<HTMLElement | null>(null);
const cols = ref(COLS);
const measure = () => {
  const el = gridEl.value;
  if (el) cols.value = colsFor(el.clientWidth, parseFloat(getComputedStyle(el).columnGap) || 0);
};
const sizer = new ResizeObserver(measure);
watch(gridEl, (el, old) => { if (old) sizer.unobserve(old); if (el) { sizer.observe(el); measure(); } });
onBeforeUnmount(() => sizer.disconnect());

// data-size keeps the legacy meaning (a widget's v2 width is twice its legacy width) so the copied legacy
// page-dashboard.css content rules and the narrow-window flow still fit; from 600 px the cell comes from
// --x/--y/--w/--h instead.
const sizeOf = (i: any) => `${i.kind === 'tile' ? i.w : Math.ceil(i.w / 2)}x${i.h}`;
const byId = computed<Record<string, any>>(() => Object.fromEntries((data.value?.grid.items ?? []).map((i: any) => [i.id, i])));
const cat = computed<Record<string, any>>(() => Object.fromEntries((data.value?.catalogue ?? []).map((c: any) => [c.id, c])));
const readingOrder = (a: Item, b: Item) => a.y - b.y || a.x - b.x;
// The view shows each item at its saved cell (a grid narrower than the layout moves the items that stick out to
// the nearest free spot). An item the user may not see, or a widget with nothing to show today, leaves its cell
// empty, like a phone. The DOM follows reading order, which the narrow-window flows use.
const viewCells = computed<any[]>(() => {
  const saved: Item[] = data.value ? data.value.layout.items.map(pick) : [];
  const at = new Map(fitTo(saved, cols.value).map((i) => [i.id, i]));
  return saved.map((i) => byId.value[i.id]).filter((i: any) => i && !i.locked && (i.kind === 'tile' || i.data !== null))
    .map((i: any) => ({ ...i, ...at.get(i.id), size: sizeOf(i) })).sort(readingOrder);
});
// The editor works on the draft drawn on this grid; the first change adopts the drawn cells.
const board = computed(() => fitTo(draft.value, cols.value));
const NO_ROOM = 'جای خالی برای این مورد نیست.';
const live = ref('');
const say = (t: string) => { live.value = t; };
const grid = useGridEditor({
  items: () => board.value,
  commit: (items) => { draft.value = items.map(pick); },
  cols: () => cols.value,
  rows: ROWS,
  limits: (id) => cat.value[id],
  label: (id) => cat.value[id]?.label ?? id,
  say,
  board: () => gridEl.value,
  noRoom: NO_ROOM,
});
onBeforeUnmount(() => { wideQuery.removeEventListener('change', onWide); grid.cancel(); });
const editCells = computed<any[]>(() => grid.shown.value.map((i) => {
  const c = cat.value[i.id] ?? {};
  const got = byId.value[i.id];
  return { ...got, ...i, kind: c.kind, label: c.label, icon: c.icon, title: c.label, size: sizeOf({ ...i, kind: c.kind }), fresh: !got };
}));
const shown = computed<any[]>(() => (arranging.value ? editCells.value : viewCells.value));
// Empty cells drawn behind the cards while editing, with two spare rows to drop into.
const slots = computed(() => (arranging.value ? emptyCells(cols.value, Math.min(ROWS, rowsUsed(grid.shown.value, 2))) : []));
const SIDES: Side[] = ['top', 'bottom', 'start', 'end'];
const removed = computed(() => (data.value?.catalogue ?? []).filter((c: any) => !draft.value.some((i) => i.id === c.id)));
const dirty = computed(() => Boolean(data.value) && cellsKey(draft.value) !== initial);
const sizeText = (i: Item) => fa(`${i.w}×${i.h}`);

const focusGrip = (id: string | undefined) => setTimeout(() => {
  const el = (id && document.querySelector<HTMLElement>(`[data-widget="${id}"] [data-grip]`)) || document.querySelector<HTMLElement>('.pl-add-v2 .pl-chip');
  el?.focus();
});

// ---- remove, add ----
// After × the focus moves to the next card's grip in reading order (or the one before, or the add list), so
// keyboard users keep their place; an added card goes to the first free spot, selected, with the focus.
function removeItem(id: string) {
  const order = [...board.value].sort(readingOrder).map((c) => c.id);
  const at = order.indexOf(id);
  draft.value = board.value.filter((i) => i.id !== id).map(pick);
  if (grid.sel.value === id) grid.sel.value = null;
  focusGrip(order[at + 1] ?? order[at - 1]);
}
function addItem(id: string) {
  const c = cat.value[id];
  const spot = firstFree({ id, w: c.min[0], h: c.min[1] }, board.value, cols.value, ROWS);
  if (!spot) { say(NO_ROOM); act.error.value = NO_ROOM; return; }
  draft.value = [...board.value.map(pick), spot];
  grid.sel.value = id;
  say(`افزوده شد: «${c.label}».`);
  focusGrip(id);
}

async function save() {
  const items = board.value.map(pick);
  if (rowsUsed(items) > ROWS) { act.error.value = NO_ROOM; return; }
  if (await act.run(() => api.put('/dashboard/layout', { layout: { v: 2, items } }), 'چیدمان ذخیره شد.')) load();
}
async function undo() {
  const out = await act.run(() => api.post('/dashboard/layout/undo'));
  if (out) { act.notice.value = out.undone ? 'چیدمان قبلی برگشت.' : 'چیدمان قبلی وجود ندارد.'; load(); }
}
async function reset() {
  if (await act.run(() => api.post('/dashboard/layout/reset'), 'چیدمان به پیش‌فرض برگشت.')) load();
}
const toggleEdit = () => router.push(editing.value ? '/' : { path: '/', query: { edit: '1' } });

// Leaving the editor with unsaved changes asks first (SPEC §14.7 item 4): any in-app navigation, «پایان چیدمان»
// included, waits for the app's own dialog; closing or reloading the tab gets the browser's warning.
const leaveBox = ref<HTMLDialogElement | null>(null);
let answer: ((leave: boolean) => void) | null = null;
function askLeave() {
  answer?.(false); // a second navigation (browser Back) while the dialog is open: the first one stays put
  if (!leaveBox.value?.open) leaveBox.value?.showModal();
  return new Promise<boolean>((resolve) => { answer = resolve; });
}
function answerLeave(leave: boolean) {
  const done = answer;
  answer = null;
  leaveBox.value?.close();
  done?.(leave);
}
const leavesEditor = (to: RouteLocationNormalized) => to.path !== '/' || to.query.edit !== '1';
const guard = (to: RouteLocationNormalized) => (editing.value && dirty.value && leavesEditor(to) ? askLeave() : true);
onBeforeRouteLeave(guard);
onBeforeRouteUpdate(guard);
const warnUnload = (e: BeforeUnloadEvent) => { if (editing.value && dirty.value) e.preventDefault(); };
onMounted(() => window.addEventListener('beforeunload', warnUnload));
onBeforeUnmount(() => { window.removeEventListener('beforeunload', warnUnload); answerLeave(false); });
const isPrint = (href: string) => href.startsWith('/print/');

// «فرم‌های چاپی» widget: one day for every form; a range form gets that day as both ends, as the print index allows.
const printDay = ref(jc.format(jc.today()));
function printHref(f: { href: string; takes: string }) {
  const q: Record<string, string> | null = f.takes === 'day' ? { d: printDay.value }
    : f.takes === 'range' ? { from: printDay.value, to: printDay.value } : null;
  return q ? `${f.href}?${new URLSearchParams(q).toString()}` : f.href;
}
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
  <div v-if="editing && !wide" class="info-box" role="status">برای چیدن داشبورد پنجره را بزرگ‌تر کنید.</div>

  <template v-if="arranging">
    <p id="pl-help" class="sr-only">برای جابه‌جایی با صفحه‌کلید: فاصله یا Enter را بزنید، با کلیدهای جهت جابه‌جا کنید، Enter برای گذاشتن و Esc برای لغو. با Shift و کلیدهای جهت اندازه را تغییر دهید.</p>
    <div class="sr-only" aria-live="polite">{{ live }}</div>
  </template>
  <div v-if="data" class="dash-wrap"><div ref="gridEl" class="dash-grid dash-v2" :class="{ 'is-editing': arranging }" :style="{ '--cols': cols }">
    <template v-if="arranging">
      <div v-for="c in slots" :key="c.id" class="g-slot" :style="place(c)" aria-hidden="true"></div>
      <div v-if="grid.ghost.value" class="g-ghost" :class="{ 'is-bad': !grid.ghost.value.ok }" :style="place(grid.ghost.value)" aria-hidden="true"></div>
    </template>
    <div v-for="w in shown" :key="w.id" class="dash-cell" :style="place(w)" :data-tile="w.kind === 'tile' ? '' : undefined" :class="{ 'is-lifted-g': grid.lifted.value === w.id, 'is-kb': grid.carried.value === w.id, 'is-sel': arranging && grid.sel.value === w.id }" :data-widget="w.id" :data-g-id="arranging ? w.id : undefined" :data-size="w.size" @pointerdown="arranging && grid.down($event, w.id)">
      <template v-if="arranging">
        <span v-if="w.kind === 'tile'" class="qa-tile" :class="{ 'qa-primary': w.w > 1 && w.h > 1 && !w.locked }">
          <span class="pl-qa-tools">
            <GripButton :label="`جابه‌جایی «${w.label}»`" @keydown="grid.key($event, w.id)" @blur="grid.blur(w.id)" />
            <button type="button" class="pl-x" :aria-label="`برداشتن «${w.label}»`" @click="removeItem(w.id)"><Icon name="x" /></button>
          </span>
          <span class="qa-icon"><Icon :name="w.icon" /></span>
          <span class="qa-text"><b>{{ w.label }}</b><span v-if="w.locked">برای دیدن این بخش دسترسی ندارید</span></span>
        </span>
        <div v-else class="pl-w-head">
          <GripButton :label="`جابه‌جایی «${w.label}»`" @keydown="grid.key($event, w.id)" @blur="grid.blur(w.id)" />
          <b>{{ w.label }}</b>
          <span class="pl-w-tools">
            <span class="pl-size" dir="ltr" aria-hidden="true">{{ sizeText(w) }}</span>
            <button type="button" class="pl-x" :aria-label="`برداشتن «${w.label}»`" @click="removeItem(w.id)"><Icon name="x" /></button>
          </span>
        </div>
        <template v-if="grid.sel.value === w.id">
          <span v-for="side in SIDES" :key="side" class="g-handle" :class="`g-${side}`" aria-hidden="true" @pointerdown="grid.handleDown($event, w.id, side)"></span>
        </template>
      </template>
      <template v-if="w.kind === 'widget'">
        <div v-if="w.locked || w.fresh" class="pl-locked">{{ w.locked ? 'برای دیدن این بخش دسترسی ندارید' : 'پس از ذخیره نشان داده می‌شود.' }}</div>
        <section v-else-if="w.data === null" class="card"><p class="muted card-body">این بخش امروز چیزی برای نشان دادن ندارد.</p></section>
        <template v-else>
          <article v-if="w.id === 'active'" class="card stat"><div class="stat-label">بیماران فعال <span class="stat-icon"><Icon name="users" /></span></div><div class="stat-value">{{ faCount(w.data.n) }}</div><div class="stat-delta">از {{ faCount(w.data.total) }} پرونده</div></article>
          <article v-else-if="w.id === 'pending'" class="card stat"><div class="stat-label">در انتظار <span class="stat-icon"><Icon name="file" /></span></div><div class="stat-value">{{ faCount(w.data.n) }}</div><div class="stat-delta">پرونده‌ی ناقص یا نیازمند بررسی</div></article>
          <article v-else-if="w.id === 'critical'" class="card stat"><div class="stat-label">بحرانی <span class="stat-icon"><Icon name="pulse" /></span></div><div class="stat-value">{{ faCount(w.data.n) }}</div><div class="stat-delta">نیازمند توجه فوری</div></article>
          <RouterLink v-else-if="w.id === 'income_today'" class="card income-today" to="/finance">
            <span class="qa-icon"><Icon name="wallet" /></span>
            <span><span class="stat-label">درآمد امروز</span><b class="money">{{ w.data.total.display }}</b></span>
            <span class="muted">{{ faCount(w.data.count) }} پرداخت</span>
          </RouterLink>
          <section v-else-if="w.id === 'alerts'" class="card alerts-card" aria-labelledby="al-h">
            <div class="card-head"><div><h2 id="al-h">هشدارها</h2><p>{{ faCount(w.data.length) }} هشدار انبار</p></div><RouterLink class="btn btn-sm" to="/storage?f=alert">همه در انبار</RouterLink></div>
            <ul class="alert-list"><li v-for="(a, ai) in w.data.slice(0, 12)" :key="ai" class="alert-row" :class="`alert-${a.level}`"><span class="alert-dot" aria-hidden="true"></span><RouterLink :to="`/storage/items/${a.itemId}`">{{ a.name }}</RouterLink><span>{{ a.text }}</span><span class="sr-only">{{ a.level === 'crit' ? '(فوری)' : '(هشدار)' }}</span></li></ul>
          </section>
          <section v-else-if="w.id === 'sms'" class="card alerts-card" aria-labelledby="sms-h">
            <div class="card-head"><div><h2 id="sms-h">پیامک</h2><p>نیاز به توجه</p></div><RouterLink class="btn btn-sm" to="/sms">گزارش پیامک</RouterLink></div>
            <ul class="alert-list">
              <li v-if="w.data.noKey" class="alert-row alert-crit"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms/settings">کلید پیامک ثبت نشده یا خوانده نمی‌شود</RouterLink></li>
              <li v-if="w.data.low !== null" class="alert-row alert-crit"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms">اعتبار پیامک رو به پایان است</RouterLink><span>{{ faCount(w.data.low) }} پیام مانده</span></li>
              <li v-if="w.data.failed" class="alert-row alert-warn"><span class="alert-dot" aria-hidden="true"></span><RouterLink to="/sms?status=failed">{{ faCount(w.data.failed) }} پیام در ۲۴ ساعت گذشته ناموفق بود</RouterLink></li>
            </ul>
          </section>
          <section v-else-if="w.id === 'today_visits'" class="card today-visits" aria-labelledby="tv-h">
            <div class="card-head">
              <div><h2 id="tv-h">ویزیت‌های امروز</h2><p>{{ faCount(w.data.length) }} ویزیت</p></div>
              <div class="today-links">
                <RouterLink class="chip chip-filter" to="/visits?range=tomorrow">فردا</RouterLink>
                <RouterLink class="chip chip-filter" to="/visits?range=week">۷ روز آینده</RouterLink>
                <RouterLink class="chip chip-filter" to="/visits?range=month">این ماه</RouterLink>
                <RouterLink class="btn btn-sm" to="/visits">همه‌ی ویزیت‌ها</RouterLink>
              </div>
            </div>
            <div v-if="!w.data.length" class="card-body"><p class="muted">امروز ویزیتی ثبت نشده است.</p></div>
            <ul v-else class="visit-list visit-compact rail">
              <li v-for="v in w.data.slice(0, 30)" :key="v.id" class="visit" :class="[`visit-${v.status}`, { 'visit-overdue': v.overdue, 'visit-now': v.ongoing }]">
                <div class="visit-when"><b class="mono">{{ fa(v.time) }}</b><span>تا <span class="mono">{{ fa(v.until) }}</span></span></div>
                <div class="visit-body"><RouterLink class="visit-patient" :to="`/patients/${v.patient.code}`">{{ v.patient.firstName }} {{ v.patient.lastName }}</RouterLink><span class="visit-reason">{{ v.reason || 'بدون شرح' }}</span></div>
                <span class="chip" :class="visitState(v).chip">{{ visitState(v).label }}</span>
              </li>
            </ul>
          </section>
          <section v-else-if="w.id === 'recent'" class="card" aria-labelledby="rp-h">
            <div class="card-head"><div><h2 id="rp-h">آخرین پرونده‌های به‌روزشده</h2><p>۸ پرونده‌ی اخیر</p></div><RouterLink class="btn btn-sm" to="/patients">فهرست بیماران</RouterLink></div>
            <div v-if="!w.data.length" class="card-body"><p class="muted">هنوز بیماری ثبت نشده است.</p></div>
            <div v-else class="table-wrap">
              <table class="table">
                <thead><tr><th scope="col">بیمار</th><th scope="col">کد</th><th scope="col">آخرین تغییر</th><th scope="col">وضعیت</th></tr></thead>
                <tbody>
                  <tr v-for="p in w.data" :key="p.id">
                    <td data-label="بیمار"><div class="person"><span class="avatar avatar-sm">{{ initialsOf(p.firstName, p.lastName) }}</span><b><RouterLink :to="`/patients/${p.code}`">{{ p.firstName }} {{ p.lastName }}</RouterLink></b></div></td>
                    <td data-label="کد" class="mono">{{ p.code }}</td>
                    <td data-label="آخرین تغییر">{{ p.updatedDay?.long }}</td>
                    <td data-label="وضعیت"><span class="chip" :class="STATUS[p.status].chip">{{ STATUS[p.status].label }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <RouterLink v-else-if="w.id === 'physio' && w.h < 2" class="card stat" to="/physio">
            <div class="stat-label">فیزیوتراپی <span class="stat-icon"><Icon name="physio" /></span></div>
            <div class="stat-value">{{ faCount(w.data.count) }}</div><div class="stat-delta">بیمار با فیزیوتراپی ناتمام</div>
          </RouterLink>
          <section v-else-if="w.id === 'physio'" class="card ps-widget" aria-labelledby="ps-w-h">
            <div class="card-head"><div><h2 id="ps-w-h">فیزیوتراپی</h2><p>{{ faCount(w.data.count) }} بیمار با فیزیوتراپی ناتمام</p></div><RouterLink class="btn btn-sm" to="/physio">همه</RouterLink></div>
            <div v-if="!w.data.rows.length" class="card-body"><p class="muted">همه‌ی دوره‌ها تمام شده‌اند.</p></div>
            <ul v-else>
              <li v-for="r in w.data.rows" :key="r.courseId">
                <RouterLink :to="`/patients/${r.code}#physio`">{{ r.firstName }} {{ r.lastName }}</RouterLink>
                <span class="ps-cell"><PhysioBoxes :sessions="r.sessions" :dates="r.dates" dots /><span class="ps-count">{{ fa(r.done) }} از {{ fa(r.sessions) }}</span></span>
              </li>
            </ul>
          </section>
          <section v-else-if="w.id === 'print_forms'" class="card" aria-labelledby="pf-h">
            <div class="card-head"><div><h2 id="pf-h">فرم‌های چاپی</h2></div><RouterLink class="btn btn-sm" to="/print">فرم‌های چاپی</RouterLink></div>
            <div class="card-body">
              <div class="field"><label for="pf-day">روز</label><JalaliInput id="pf-day" v-model="printDay" /></div>
              <ul class="pf-list"><li v-for="f in w.data" :key="f.id"><a :href="printHref(f)"><Icon name="print" />{{ f.title }}</a></li></ul>
            </div>
          </section>
        </template>
      </template>
      <!-- Print forms are server pages (/print/...), not Vue routes: a plain link, as on the print index. -->
      <component :is="isPrint(w.href) ? 'a' : RouterLink" v-else-if="!arranging" class="qa-tile" :class="{ 'qa-primary': w.w > 1 && w.h > 1 }" v-bind="isPrint(w.href) ? { href: w.href } : { to: w.href }">
        <span class="qa-icon"><Icon :name="w.icon" /></span>
        <span class="qa-text"><b>{{ w.title }}</b><span v-if="w.text">{{ w.text }}</span></span>
      </component>
    </div>
    
  </div></div>
  <div v-if="arranging && removed.length" class="pl-w-add pl-add-v2">
    <span class="pl-w-add-title"><Icon name="plus" />افزودن کارت</span>
    <ul class="pl-chips"><li v-for="r in removed" :key="r.id"><button type="button" class="pl-chip" @click="addItem(r.id)"><Icon :name="r.icon || 'plus'" /><span>{{ r.label }}</span></button></li></ul>
  </div>
  <div v-if="arranging && data" class="pl-draft">
    <span class="pl-draft-state">{{ dirty ? 'تغییرات ذخیره نشده' : 'بدون تغییر' }}</span>
    <span class="pl-draft-btns">
      <button class="btn btn-ghost pl-wide" type="button" :disabled="act.busy.value" @click="reset">بازگشت به پیش‌فرض</button>
      <button class="btn btn-ghost pl-wide" type="button" :disabled="!data.hasPrevious || act.busy.value" @click="undo">چیدمان قبلی</button>
      <button class="btn btn-primary" type="button" :disabled="!dirty || act.busy.value" @click="save"><Icon name="check" />ذخیره</button>
    </span>
  </div>
  <dialog ref="leaveBox" class="app-dialog" aria-labelledby="dash-leave-h" @close="answerLeave(false)">
    <div class="card">
      <div class="card-body stack-lg">
        <p id="dash-leave-h">تغییرات ذخیره نشده‌اند. بدون ذخیره خارج می‌شوید؟</p>
        <div class="form-actions">
          <button class="btn btn-danger" type="button" @click="answerLeave(true)">خروج</button>
          <button class="btn btn-ghost" type="button" autofocus @click="answerLeave(false)">ماندن</button>
        </div>
      </div>
    </div>
  </dialog>
</template>
