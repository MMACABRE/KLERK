<script setup lang="ts">
// Jalali date text box with a calendar popup (legacy enhanceDate). The text box stays the source of truth: the user
// may type 1403/05/12 or Persian digits; the server parses it. Keys: RTL arrows move by day and week, Escape closes.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import Icon from './Icon.vue';
import * as jc from '../lib/jalali-math.js';
import { claimDropdown, releaseDropdown } from '../lib/popup';

const props = defineProps<{ id?: string; name?: string; placeholder?: string; disabled?: boolean; off?: boolean }>();
const model = defineModel<string>({ default: '' });

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
const WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
const fa = (n: number | string) => String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);

const now = jc.today();
const open = ref(false);
const view = ref({ jy: now.jy, jm: now.jm });
const wrap = ref<HTMLElement | null>(null);
const grid = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const focusDay = ref(1);

const years = computed(() => {
  const out: number[] = [];
  for (let y = now.jy + 5; y >= 1300; y--) out.push(y);
  if (!out.includes(view.value.jy)) out.unshift(view.value.jy);
  return out;
});
const selected = computed(() => jc.parse(model.value));
const days = computed(() => {
  const { jy, jm } = view.value;
  const lead = jc.weekColumn(jy, jm, 1);
  const n = jc.monthLength(jy, jm);
  const sel = selected.value;
  return {
    lead,
    list: Array.from({ length: n }, (_, i) => {
      const d = i + 1;
      return {
        d,
        sel: Boolean(sel && sel.jy === jy && sel.jm === jm && sel.jd === d),
        today: now.jy === jy && now.jm === jm && now.jd === d,
      };
    }),
  };
});

function shift(months: number) {
  const index = view.value.jy * 12 + (view.value.jm - 1) + months;
  view.value = { jy: Math.floor(index / 12), jm: (index % 12) + 1 };
}

function pick(d: { jy: number; jm: number; jd: number }) {
  model.value = jc.format(d);
  close(true);
}

const closeOther = () => close();
function close(focusButton = false) {
  open.value = false;
  releaseDropdown(closeOther);
  if (focusButton) button.value?.focus();
}

async function toggle() {
  if (open.value) return close();
  const s = selected.value;
  view.value = s ? { jy: s.jy, jm: s.jm } : { jy: now.jy, jm: now.jm };
  focusDay.value = s ? s.jd : now.jd;
  claimDropdown(closeOther);
  open.value = true;
  await nextTick();
  focusTo(focusDay.value);
}

function focusTo(d: number) {
  grid.value?.querySelector<HTMLButtonElement>(`[data-day="${d}"]`)?.focus();
}

async function onKey(e: KeyboardEvent) {
  const day = Number((e.target as HTMLElement).dataset?.day);
  if (!day) return;
  const step = ({ ArrowLeft: 1, ArrowRight: -1, ArrowDown: 7, ArrowUp: -7 } as Record<string, number>)[e.key];
  if (!step) return;
  e.preventDefault();
  let target = day + step;
  const len = jc.monthLength(view.value.jy, view.value.jm);
  if (target < 1) { shift(-1); target += jc.monthLength(view.value.jy, view.value.jm); } else if (target > len) { target -= len; shift(1); }
  focusDay.value = target;
  await nextTick();
  focusTo(target);
}

function onFocusOut() {
  setTimeout(() => {
    if (open.value && wrap.value && !wrap.value.contains(document.activeElement)) close();
  }, 0);
}

function onDocClick(e: MouseEvent) {
  if (open.value && wrap.value && !wrap.value.contains(e.target as Node)) close();
}
onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));
const tabDay = computed(() => Math.min(focusDay.value, days.value.list.length));
</script>

<template>
  <span ref="wrap" class="field-addon jdp" :class="{ 'jdp-off': props.off }" @focusout="onFocusOut">
    <input :id="id" v-model="model" class="input" type="text" :name="name" inputmode="numeric" dir="ltr" autocomplete="off"
      :placeholder="placeholder" :disabled="disabled">
    <button ref="button" type="button" class="addon-btn" aria-label="انتخاب تاریخ از تقویم" title="انتخاب تاریخ از تقویم"
      aria-haspopup="dialog" :aria-expanded="open ? 'true' : 'false'" :disabled="disabled" @click="toggle"><Icon name="calendar" /></button>
    <div v-if="open" class="jdp-pop" role="dialog" aria-label="تقویم شمسی" tabindex="-1" @keydown.esc.prevent="close(true)">
      <div class="jdp-head">
        <button type="button" class="jdp-nav" aria-label="ماه قبل" @click="shift(-1)">›</button>
        <select class="jdp-select" aria-label="ماه" :value="view.jm" @change="view.jm = Number(($event.target as HTMLSelectElement).value)">
          <option v-for="(m, i) in MONTHS" :key="m" :value="i + 1">{{ m }}</option>
        </select>
        <select class="jdp-select" aria-label="سال" :value="view.jy" @change="view.jy = Number(($event.target as HTMLSelectElement).value)">
          <option v-for="y in years" :key="y" :value="y">{{ fa(y) }}</option>
        </select>
        <button type="button" class="jdp-nav" aria-label="ماه بعد" @click="shift(1)">‹</button>
      </div>
      <div class="jdp-week" aria-hidden="true"><span v-for="d in WEEKDAYS" :key="d">{{ d }}</span></div>
      <div ref="grid" class="jdp-grid" role="group" aria-label="روزهای ماه" @keydown="onKey">
        <span v-for="i in days.lead" :key="`l${i}`"></span>
        <button v-for="x in days.list" :key="x.d" type="button" class="jdp-day" :class="{ 'is-selected': x.sel, 'is-today': x.today }"
          :data-day="x.d" :aria-label="`${fa(x.d)} ${MONTHS[view.jm - 1]} ${fa(view.jy)}`" :aria-current="x.today ? 'date' : undefined"
          :aria-pressed="x.sel ? 'true' : 'false'" :tabindex="x.d === tabDay ? 0 : -1"
          @click="pick({ jy: view.jy, jm: view.jm, jd: x.d })">{{ fa(x.d) }}</button>
      </div>
      <div class="jdp-foot">
        <button type="button" class="btn btn-sm" @click="pick(now)">امروز</button>
        <button type="button" class="btn btn-sm btn-ghost" @click="model = ''; close(true)">پاک کردن</button>
      </div>
    </div>
  </span>
</template>
