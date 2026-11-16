<script setup lang="ts">
// Dashboard (legacy views/home.ejs + views/dashboard/*, D54; layout v2, ADR-0014; owner decision 2026-11-16 "packed
// order"): the dashboard is an ordered list of widgets and tiles, each with a size. From 1200 px the view and the
// editor place that list with the same function (grid-math `pack`) on the same number of columns, which grows with
// the window (8 at 1440 px, up to 16 when zoomed out), so cards fill every gap, never stretch, and what is edited is
// what is shown. Edit mode (layout flag, 1200 px and wider): drag a card by its grip to another place in the order
// (pointer, or keyboard: Space picks up, arrows move one place, Enter drops, Escape puts back), resize it by the
// corner handle or Shift + arrows, remove it with ×, add it back from the list, then save.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink, useRoute, useRouter } from 'vue-router';
import type { RouteLocationNormalized } from 'vue-router';
import Icon from '../components/Icon.vue';
import ClockCard from '../components/ClockCard.vue';
import GripButton from '../components/GripButton.vue';
import JalaliInput from '../components/JalaliInput.vue';
import { api } from '../api/client';
import { has, setTitle } from '../lib/session';
import { fa, faCount, initialsOf, STATUS, visitState } from '../lib/fmt';
import { useAction, useLoad } from '../lib/usePage';
import { useDragList } from '../lib/dragList';
import { clampSize, colsFor, COLS, orderOf, pack, packSaved } from '../lib/grid-math';
import type { Item, Size } from '../lib/grid-math';
import * as jc from '../lib/jalali-math';

setTitle('');
const route = useRoute();
const router = useRouter();
const editing = computed(() => route.query.edit === '1' && has('layout'));
const draft = ref<Size[]>([]);
const sizes = (items: Size[]) => items.map((i) => `${i.id}:${i.w}x${i.h}`).join('|');
let initial = '';
const act = useAction();
const { data, load } = useLoad(async () => {
  const d = await api.get('/dashboard', editing.value ? { edit: '1' } : {});
  draft.value = orderOf(d.layout.items).map(({ id, w, h }) => ({ id, w, h }));
  initial = sizes(draft.value);
  return d;
});

// Editing happens only at 1200 px and wider (ADR-0014 "Screens"); narrower windows keep the 4-column and phone flows.
const wideQuery = window.matchMedia('(min-width: 1200px)');
const wide = ref(wideQuery.matches);
const onWide = () => { wide.value = wideQuery.matches; };
onMounted(() => wideQuery.addEventListener('change', onWide));
onBeforeUnmount(() => { wideQuery.removeEventListener('change', onWide); stopResize(); });
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

// data-size keeps the v1 meaning (a widget's v2 width is twice its v1 width) so the v1 styles and the narrow-window
// flow still fit; from 1200 px the cell comes from --x/--y/--w/--h instead.
const sizeOf = (i: any) => `${i.kind === 'tile' ? i.w : Math.ceil(i.w / 2)}x${i.h}`;
const byId = computed<Record<string, any>>(() => Object.fromEntries((data.value?.grid.items ?? []).map((i: any) => [i.id, i])));
const cat = computed<Record<string, any>>(() => Object.fromEntries((data.value?.catalogue ?? []).map((c: any) => [c.id, c])));
// The view packs only what it shows (a locked item or an empty widget leaves no hole), in the saved list order.
const viewCells = computed<any[]>(() => {
  const shownItems = (data.value ? orderOf(data.value.layout.items) : []).map((i) => byId.value[i.id])
    .filter((i: any) => i && !i.locked && (i.kind === 'tile' || i.data !== null));
  const at = pack(shownItems, cols.value);
  return shownItems.map((i: any, n: number) => ({ ...i, ...at[n], size: sizeOf(i) }));
});
// The editor packs the items the view shows first, in list order, so they land exactly where the view puts them;
// the ones the view leaves out (locked, or a widget with nothing to show today) follow after them, with their note.
const hiddenInView = (i: any) => i && (i.locked || (i.kind === 'widget' && i.data === null));
const editCells = computed<any[]>(() => {
  const list = [...draft.value.filter((i) => !hiddenInView(byId.value[i.id])), ...draft.value.filter((i) => hiddenInView(byId.value[i.id]))];
  const at = pack(list, cols.value);
  return list.map((i, n) => {
    const c = cat.value[i.id] ?? {};
    const got = byId.value[i.id];
    return { ...got, ...at[n], kind: c.kind, label: c.label, icon: c.icon, title: c.label, size: sizeOf({ ...i, kind: c.kind }), fresh: !got };
  });
});
const shown = computed<any[]>(() => (arranging.value ? editCells.value : viewCells.value));
const place = (i: Item) => ({ '--x': i.x + 1, '--y': i.y + 1, '--w': i.w, '--h': i.h });
const removed = computed(() => (data.value?.catalogue ?? []).filter((c: any) => !draft.value.some((i) => i.id === c.id)));
const dirty = computed(() => Boolean(data.value) && sizes(draft.value) !== initial);

// ---- live region ----
const live = ref('');
const say = (t: string) => { live.value = t; };
const sizeText = (i: Size) => fa(`${i.w}×${i.h}`);
const NO_ROOM = 'جای خالی برای این مورد نیست.';

// ---- move: a place in the order, by pointer or keyboard (the same drag code as the form layout editor) ----
const move = useDragList<Size>({
  ns: 'd',
  groups: () => [{ key: 'all', items: draft.value }],
  idOf: (i) => i.id,
  label: (id) => cat.value[id]?.label ?? id,
  say,
});

// ---- resize: corner handle or Shift + arrows; refused when the list would not fit the saved 8 x 40 grid ----
function setSize(id: string, w: number, h: number): boolean {
  const it = draft.value.find((i) => i.id === id)!;
  const s = clampSize(w, h, cat.value[id].min, cat.value[id].max);
  if (s.w === it.w && s.h === it.h) return false;
  const next = draft.value.map((i) => (i.id === id ? { ...i, ...s } : i));
  if (!packSaved(next)) { if (live.value !== NO_ROOM) say(NO_ROOM); return false; }
  draft.value = next;
  return true;
}
// In RTL the inline end is on the left, so ArrowLeft widens; ArrowDown makes it taller.
function key(ev: KeyboardEvent, id: string) {
  if (ev.shiftKey && ev.key.startsWith('Arrow')) {
    ev.preventDefault();
    const rtl = getComputedStyle(ev.currentTarget as HTMLElement).direction === 'rtl';
    const it = draft.value.find((i) => i.id === id)!;
    const dw = ev.key === 'ArrowLeft' ? (rtl ? 1 : -1) : ev.key === 'ArrowRight' ? (rtl ? -1 : 1) : 0;
    const dh = ev.key === 'ArrowDown' ? 1 : ev.key === 'ArrowUp' ? -1 : 0;
    setSize(id, it.w + dw, it.h + dh);
    say(`اندازه‌ی ${sizeText(draft.value.find((i) => i.id === id)!)}`);
    return;
  }
  move.key(ev, id);
}
let sizing: { id: string; sx: number; sy: number; w: number; h: number; px: number; py: number; rtl: boolean } | null = null;
function startResize(ev: PointerEvent, id: string) {
  if (ev.button !== 0 || !gridEl.value) return;
  ev.preventDefault();
  const cs = getComputedStyle(gridEl.value);
  const col = parseFloat(cs.gridTemplateColumns.split(' ')[0]) || 120;
  const row = parseFloat(cs.gridTemplateRows.split(' ')[0]) || 120;
  const it = draft.value.find((i) => i.id === id)!;
  sizing = { id, sx: ev.clientX, sy: ev.clientY, w: it.w, h: it.h, px: col + parseFloat(cs.columnGap), py: row + parseFloat(cs.rowGap), rtl: cs.direction === 'rtl' };
  window.addEventListener('pointermove', onResize);
  window.addEventListener('pointerup', endResize);
  window.addEventListener('pointercancel', stopResize);
}
function onResize(ev: PointerEvent) {
  const s = sizing;
  if (!s) return;
  const dx = (s.rtl ? s.sx - ev.clientX : ev.clientX - s.sx) / s.px;
  const dy = (ev.clientY - s.sy) / s.py;
  if (setSize(s.id, s.w + Math.round(dx), s.h + Math.round(dy)) && live.value === NO_ROOM) say('');
}
function endResize() {
  if (sizing) say(`اندازه‌ی ${sizeText(draft.value.find((i) => i.id === sizing!.id)!)}`);
  stopResize();
}
function stopResize() {
  sizing = null;
  window.removeEventListener('pointermove', onResize);
  window.removeEventListener('pointerup', endResize);
  window.removeEventListener('pointercancel', stopResize);
}

const focusGrip = (id: string | undefined) => nextTick(() => {
  const el = (id && document.querySelector<HTMLElement>(`[data-widget="${id}"] [data-grip]`)) || document.querySelector<HTMLElement>('.pl-add-v2 .pl-chip');
  el?.focus();
});

// ---- remove, add ----
// After × the focus moves to the next item's grip (or the one before, or the add list), so keyboard users keep
// their place; an added item joins the end of the list (so it fills the first gap it fits) and gets the focus.
function removeItem(id: string) {
  const order = draft.value.map((c) => c.id);
  const at = order.indexOf(id);
  draft.value = draft.value.filter((i) => i.id !== id);
  focusGrip(order[at + 1] ?? order[at - 1]);
}
function addItem(id: string) {
  const c = cat.value[id];
  const next = [...draft.value, { id, w: c.min[0], h: c.min[1] }];
  if (!packSaved(next)) { say(NO_ROOM); act.error.value = NO_ROOM; return; }
  draft.value = next;
  say(`افزوده شد: «${c.label}».`);
  focusGrip(id);
}

async function save() {
  const items = packSaved(draft.value);
  if (!items) { act.error.value = NO_ROOM; return; }
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
  <div v-if="data" class="dash-wrap"><div ref="gridEl" class="dash-grid dash-v2" :class="{ 'is-editing': arranging }" :style="{ '--cols': cols }" data-d-group="all">
    <div v-for="w in shown" :key="w.id" class="dash-cell" :style="place(w)" :data-tile="w.kind === 'tile' ? '' : undefined" :class="{ 'pl-ph': move.lifted.value === w.id, 'is-kb': move.carried.value === w.id }" :data-widget="w.id" :data-d-id="arranging ? w.id : undefined" :data-size="w.size">
      <template v-if="arranging">
        <span v-if="w.kind === 'tile'" class="qa-tile" :class="{ 'qa-primary': w.w > 1 && w.h > 1 && !w.locked }">
          <span class="pl-qa-tools">
            <GripButton :label="`جابه‌جایی «${w.label}»`" @pointerdown="move.down($event, w.id)" @keydown="key($event, w.id)" @blur="move.blur()" />
            <button type="button" class="pl-x" :aria-label="`برداشتن «${w.label}»`" @click="removeItem(w.id)"><Icon name="x" /></button>
          </span>
          <span class="qa-icon"><Icon :name="w.icon" /></span>
          <span class="qa-text"><b>{{ w.label }}</b><span v-if="w.locked">برای دیدن این بخش دسترسی ندارید</span></span>
        </span>
        <div v-else class="pl-w-head">
          <GripButton :label="`جابه‌جایی «${w.label}»`" @pointerdown="move.down($event, w.id)" @keydown="key($event, w.id)" @blur="move.blur()" />
          <b>{{ w.label }}</b>
          <span class="pl-w-tools">
            <span class="pl-size" dir="ltr" aria-hidden="true">{{ sizeText(w) }}</span>
            <button type="button" class="pl-x" :aria-label="`برداشتن «${w.label}»`" @click="removeItem(w.id)"><Icon name="x" /></button>
          </span>
        </div>
        <button type="button" class="pl-resize" :aria-label="`تغییر اندازه‌ی «${w.label}»`" tabindex="-1" @pointerdown="startResize($event, w.id)"></button>
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
