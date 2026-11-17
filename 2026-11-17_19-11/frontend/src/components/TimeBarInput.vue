<script setup lang="ts">
// Visit time box with the day bar dropdown (legacy enhanceDayBar, D50). The text box stays the source of truth and
// typing always works; the dropdown draws the day's bookings on a 24-hour ruler (left to right, even in RTL) and a
// click on free space writes the start time, snapped to 5 minutes. The visit-to-be is a dashed ghost as wide as
// `duration`; it turns red on a clash. The server re-checks the overlap on save.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import Icon from './Icon.vue';
import { api, ApiError } from '../api/client';
import { fa } from '../lib/fmt';
import { claimDropdown, hhmm, minuteAt, minutesNow, parseMinutes, placePop, releaseDropdown, revealPop } from '../lib/popup';

const props = defineProps<{ id: string; date: string; duration: number; exclude?: string; describedby?: string; invalid?: boolean }>();
const model = defineModel<string>({ default: '' });
const emit = defineEmits<{ failed: [boolean] }>();

type Booking = { start: number; end: number; time: string; until: string; name: string; status: string; fromYesterday: boolean };
const dayFmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { weekday: 'long', day: 'numeric', month: 'long' });

const wrap = ref<HTMLElement | null>(null);
const input = ref<HTMLInputElement | null>(null);
const pop = ref<HTMLElement | null>(null);
const scroll = ref<HTMLElement | null>(null);
const track = ref<HTMLElement | null>(null);

const open = ref(false);
const busy = ref(false);
const hour = ref(120); // px per hour, read once at each open
const bookings = ref<Booking[]>([]);
const today = ref(false);
const dateLabel = ref('');
const note = ref<string | null>(null); // status line override: loading, bad date, or load failure
const pick = ref<number | null>(null);
const glide = ref(false);
const hoverAt = ref<number | null>(null);
const tip = ref<{ name: string; text: string; left: number; top: number } | null>(null);
const nowMin = ref(minutesNow());
let refocusing = false; // true while focus returns to the box, so the focus handler does not reopen
let lastPointer = 'mouse';
let drag: { kind: 'mouse' | 'touch' | 'knob'; id: number; x?: number; m?: number | null; moved?: boolean } | null = null;
let seq = 0; // a newer load makes the older answer stale

const px = (m: number) => (m * hour.value) / 60;
const dur = computed(() => props.duration || 15);
const clash = computed(() => (pick.value === null ? null : bookings.value.find((b) => b.start < pick.value! + dur.value && pick.value! < b.end) ?? null));

const pickLabel = computed(() => {
  if (pick.value === null) return 'ساعت شروع را روی نوار بزنید';
  const end = pick.value + dur.value;
  return end > 1440 ? `${fa(hhmm(pick.value))} تا فردا ${fa(hhmm(end - 1440))}` : `${fa(hhmm(pick.value))} تا ${fa(hhmm(end))}`;
});
const status = computed(() => {
  if (note.value) return note.value;
  if (pick.value === null) return 'روی جای آزاد نوار بزنید؛ ساعت در کادر نوشته می‌شود.';
  const c = clash.value;
  if (c) return `با ویزیت ساعت ${fa(c.time)} تا ${fa(c.until)} هم‌پوشانی دارد.`;
  // The bar does not load the next day, so the overrun is checked by the server on save.
  if (pick.value + dur.value > 1440) return 'ادامه‌ی این ویزیت به فردا می‌رسد؛ هم‌پوشانی با فردا هنگام ذخیره بررسی می‌شود.';
  return `آزاد است: ${fa(hhmm(pick.value))} تا ${fa(hhmm(pick.value + dur.value))}`;
});

function setPick(m: number, smooth: boolean) {
  pick.value = m;
  glide.value = smooth;
  model.value = hhmm(m);
}
function keepVisible(m: number) {
  const s = scroll.value;
  if (!s) return;
  const x = px(m);
  if (x < s.scrollLeft + 24 || x > s.scrollLeft + s.clientWidth - 24) s.scrollLeft = x - s.clientWidth / 3;
}
// Typing moves the pick; the script's own writes come back here with the same value and change nothing.
watch(model, (text) => {
  const m = parseMinutes(text);
  if (m === pick.value) return;
  pick.value = m;
  glide.value = true;
  if (m !== null && open.value) keepVisible(m);
});

async function load() {
  const mine = ++seq;
  busy.value = true;
  note.value = 'در حال بارگذاری…';
  try {
    const data = await api.get('/visits/day', { d: props.date.trim(), exclude: props.exclude ?? '' });
    if (mine !== seq) return;
    bookings.value = data.bookings;
    today.value = data.today;
    note.value = null;
    dateLabel.value = dayFmt.format(new Date(`${data.date}T12:00:00`));
    emit('failed', false);
  } catch (e) {
    if (mine !== seq) return;
    bookings.value = [];
    today.value = false;
    dateLabel.value = '';
    if (e instanceof ApiError && e.status === 400) {
      note.value = 'تاریخ را درست وارد کنید تا نوار ساعت پر شود.';
    } else {
      note.value = 'نوار ساعت بارگذاری نشد؛ ساعت را تایپ کنید.';
      emit('failed', true);
    }
  }
  busy.value = false;
}

// The typed time, else 30 minutes before the first booking that is not a tail from yesterday, else 08:00, at a third.
function scrollToStart() {
  const first = bookings.value.find((b) => !b.fromYesterday);
  const m = pick.value ?? (first ? Math.max(0, first.start - 30) : 480);
  if (scroll.value) scroll.value.scrollLeft = px(m) - scroll.value.clientWidth / 3;
}

async function show() {
  if (open.value || refocusing) return;
  claimDropdown(close);
  hour.value = matchMedia('(max-width: 600px)').matches ? 96 : 120;
  pick.value = parseMinutes(model.value);
  glide.value = false;
  nowMin.value = minutesNow();
  open.value = true;
  await nextTick();
  placePop(wrap.value!, pop.value!);
  // .is-open one frame after unhiding so the transition runs; set by hand like is-above, so Vue never rewrites the class.
  requestAnimationFrame(() => { if (open.value) pop.value?.classList.add('is-open'); });
  await load();
  if (!open.value) return;
  await nextTick();
  scrollToStart();
  placePop(wrap.value!, pop.value!);
  revealPop(pop.value!);
}
function close() {
  if (!open.value) return;
  open.value = false;
  pop.value?.classList.remove('is-open');
  tip.value = null;
  hoverAt.value = null;
  releaseDropdown(close);
}
function refocus() {
  refocusing = true;
  input.value?.focus();
  refocusing = false;
}
const closeAndReturn = () => { close(); refocus(); };
const toggle = () => (open.value ? close() : show());

watch(() => props.date, () => { if (open.value) load(); });
watch(dur, () => { glide.value = false; });

// Booked visit tip: name, span, length, and «از دیروز» for a tail. A child of the pop, so the scroller never clips it.
function showTip(node: HTMLElement, b: Booking) {
  const parts = [`${fa(b.time)} تا ${fa(b.until)}`, `${fa(b.end - b.start)} دقیقه`];
  if (b.fromYesterday) parts.push('از دیروز');
  const r = node.getBoundingClientRect();
  const p = pop.value!.getBoundingClientRect();
  tip.value = { name: b.name, text: parts.join('، '), left: r.left - p.left, top: r.top - p.top };
  nextTick(() => {
    const el = pop.value?.querySelector<HTMLElement>('.dbar-tip');
    if (el && tip.value) tip.value.left = Math.max(0, Math.min(tip.value.left, pop.value!.clientWidth - el.offsetWidth));
  });
}
function onBlockEnter(e: PointerEvent, b: Booking) {
  if (e.pointerType === 'mouse') showTip(e.currentTarget as HTMLElement, b);
}
function onBlockLeave(e: PointerEvent) {
  if (e.pointerType === 'mouse') tip.value = null;
}
function onBlockClick(e: MouseEvent, b: Booking) {
  if (lastPointer === 'mouse') return;
  if (tip.value) tip.value = null;
  else showTip(e.currentTarget as HTMLElement, b);
}

// Picking: blocks never pick; a mouse picks on press and follows the drag; touch picks on a tap only (8 px = scroll).
function onKnobDown(e: PointerEvent) {
  e.stopPropagation();
  e.preventDefault();
  drag = { kind: 'knob', id: e.pointerId };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
}
function onKnobMove(e: PointerEvent) {
  if (!drag || drag.kind !== 'knob' || e.pointerId !== drag.id) return;
  const m = minuteAt(track.value!, e.clientX);
  if (m !== null) setPick(m, false);
}
function onKnobUp(e: PointerEvent) {
  if (drag && e.pointerId === drag.id) drag = null;
}
function onLaneDown(e: PointerEvent) {
  lastPointer = e.pointerType;
  if ((e.target as Element).closest('.dbar-block')) return;
  tip.value = null;
  const m = minuteAt(track.value!, e.clientX);
  if (m === null) return;
  if (e.pointerType === 'mouse') {
    drag = { kind: 'mouse', id: e.pointerId };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setPick(m, true);
  } else {
    drag = { kind: 'touch', id: e.pointerId, x: e.clientX, m, moved: false };
  }
}
function onLaneMove(e: PointerEvent) {
  if (drag) {
    hoverAt.value = null;
    if (drag.kind === 'touch') {
      if (Math.abs(e.clientX - drag.x!) >= 8) drag.moved = true;
    } else if (drag.kind === 'mouse' && e.pointerId === drag.id) {
      const m = minuteAt(track.value!, e.clientX);
      if (m !== null) setPick(m, false);
    }
    return;
  }
  if (e.pointerType !== 'mouse' || (e.target as Element).closest('.dbar-block')) { hoverAt.value = null; return; }
  hoverAt.value = minuteAt(track.value!, e.clientX);
}
function onLaneUp(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  if (drag.kind === 'touch' && !drag.moved && drag.m != null) setPick(drag.m, true);
  drag = null;
}
const onScroll = () => { tip.value = null; hoverAt.value = null; };

// Keyboard on the ruler: arrows 5 minutes, Page Up/Down an hour, Home/End the day, Enter closes.
function onTrackKey(e: KeyboardEvent) {
  if (e.key === 'Enter') { e.preventDefault(); closeAndReturn(); return; }
  const step = ({ ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5, PageUp: 60, PageDown: -60 } as Record<string, number>)[e.key];
  if (step === undefined && e.key !== 'Home' && e.key !== 'End') return;
  e.preventDefault();
  let next = Math.min(1435, Math.max(0, (pick.value ?? 480) + (step ?? 0)));
  if (e.key === 'Home') next = 0;
  if (e.key === 'End') next = 1435;
  keepVisible(next);
  setPick(next, true);
}
function onEsc(e: KeyboardEvent) {
  if (!open.value) return;
  e.preventDefault();
  closeAndReturn();
}
function onFocusOut() {
  setTimeout(() => { if (open.value && wrap.value && !wrap.value.contains(document.activeElement)) close(); }, 0);
}
function onDocDown(e: PointerEvent) {
  if (open.value && wrap.value && !wrap.value.contains(e.target as Node)) close();
}
function onResize() {
  if (open.value) placePop(wrap.value!, pop.value!);
}
onMounted(() => {
  document.addEventListener('pointerdown', onDocDown);
  window.addEventListener('resize', onResize);
});
onBeforeUnmount(() => {
  close();
  document.removeEventListener('pointerdown', onDocDown);
  window.removeEventListener('resize', onResize);
});
</script>

<template>
  <span ref="wrap" class="field-addon dbar" @keydown.esc="onEsc" @focusout="onFocusOut">
    <input :id="id" ref="input" v-model="model" class="input" type="text" placeholder="۰۹:۳۰" inputmode="numeric" dir="ltr" maxlength="5"
      required autocomplete="off" :aria-describedby="describedby" :aria-invalid="invalid ? 'true' : undefined" @focus="show" @click="show">
    <button type="button" class="addon-btn" aria-label="انتخاب ساعت از نوار روز" title="انتخاب ساعت از نوار روز" aria-haspopup="dialog"
      :aria-expanded="open ? 'true' : 'false'" @click="toggle"><Icon name="clock" /></button>
    <div v-show="open" ref="pop" class="dbar-pop" role="dialog" aria-label="نوار ساعت روز" tabindex="-1"
      :aria-busy="busy ? 'true' : undefined">
      <div class="dbar-head">
        <div class="dbar-when"><b class="dbar-date">{{ dateLabel }}</b><span class="dbar-pick">{{ pickLabel }}</span></div>
        <button type="button" class="dbar-close" aria-label="بستن" tabindex="-1" @click="closeAndReturn"><Icon name="x" /></button>
      </div>
      <div ref="scroll" class="dbar-scroll" @scroll.passive="onScroll">
        <div ref="track" class="dbar-track" role="slider" tabindex="0" aria-label="ساعت شروع ویزیت" aria-valuemin="0" aria-valuemax="1435"
          :aria-valuenow="pick ?? undefined" :aria-valuetext="pick === null ? 'انتخاب نشده' : fa(hhmm(pick))" :style="{ width: `${24 * hour}px` }"
          @keydown="onTrackKey">
          <div class="dbar-hours">
            <span v-for="h in 24" :key="h" class="dbar-hour" :style="{ left: `${(h - 1) * hour}px` }">{{ fa(String(h - 1).padStart(2, '0')) }}</span>
          </div>
          <div class="dbar-lane" @pointerdown="onLaneDown" @pointermove="onLaneMove" @pointerup="onLaneUp" @pointercancel="drag = null" @pointerleave="hoverAt = null">
            <div v-for="(b, i) in bookings" :key="i" class="dbar-block" :class="{ 'is-done': b.status === 'done' }"
              :style="{ left: `${px(b.start)}px`, width: `${px(b.end - b.start)}px` }"
              @pointerenter="onBlockEnter($event, b)" @pointerleave="onBlockLeave" @click="onBlockClick($event, b)"></div>
            <div v-if="today" class="dbar-now" :style="{ left: `${px(nowMin)}px` }"></div>
            <div v-show="pick !== null" class="dbar-ghost" :class="{ 'is-clash': clash, 'is-gliding': glide }"
              :style="pick === null ? {} : { left: `${px(pick)}px`, width: `${px(Math.min(dur, 1440 - pick))}px` }"></div>
            <div v-show="pick !== null" class="dbar-marker" :class="{ 'is-gliding': glide }" :style="pick === null ? {} : { left: `${px(pick)}px` }">
              <span class="dbar-knob" @pointerdown="onKnobDown" @pointermove="onKnobMove" @pointerup="onKnobUp" @pointercancel="onKnobUp"></span>
            </div>
            <div v-show="hoverAt !== null" class="dbar-hover" :style="hoverAt === null ? {} : { left: `${px(hoverAt)}px` }"><span>{{ hoverAt === null ? '' : fa(hhmm(hoverAt)) }}</span></div>
          </div>
        </div>
      </div>
      <div v-if="tip" class="dbar-tip" :style="{ left: `${tip.left}px`, top: `${tip.top}px` }"><b>{{ tip.name }}</b><span>{{ tip.text }}</span></div>
      <div class="dbar-foot">
        <p class="dbar-status" :class="{ 'is-clash': !note && clash }" aria-live="polite">{{ status }}</p>
        <div class="dbar-keys" aria-hidden="true">
          <span><i class="key-booked"></i>رزروشده</span><span><i class="key-done"></i>انجام‌شده</span><span><i class="key-pick"></i>ویزیت شما</span>
        </div>
      </div>
    </div>
  </span>
</template>
