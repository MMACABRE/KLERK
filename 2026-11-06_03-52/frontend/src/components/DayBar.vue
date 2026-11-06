<script setup lang="ts">
// Day bar on /visits (legacy partial day-bar + enhancePageBar, D50): the booked times of one day on a 00:00-24:00
// ruler, left to right. A click on a free spot starts a new visit at that time (5-minute snap); a block opens its
// visit. One shared hover card replaces the native tooltip; on touch the first tap shows it and a second tap on the
// same block opens the visit. Modified clicks fall through to the plain links (new tab and so on).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { can } from '../lib/session';
import { fa } from '../lib/fmt';
import { hhmm, minuteAt, minutesNow } from '../lib/popup';

type Booking = { id: number; start: number; end: number; time: string; until: string; name: string; status: string; fromYesterday: boolean };
const props = defineProps<{ bar: any; dateLong: string }>();
const router = useRouter();
const hh = (h: number) => String(h).padStart(2, '0');
const canAdd = computed(() => can('visits', 2));
const bookedMin = computed(() => props.bar.bookings.reduce((s: number, b: Booking) => s + b.end - b.start, 0));
const bookedText = computed(() => {
  const m = bookedMin.value;
  return m >= 60 ? `${fa(Math.floor(m / 60))} ساعت${m % 60 ? ` و ${fa(m % 60)} دقیقه` : ''}` : `${fa(m)} دقیقه`;
});
const newHref = (t: string) => router.resolve({ path: '/visits/new', query: { d: props.bar.input, t } }).href;

const scroller = ref<HTMLElement | null>(null);
const track = ref<HTMLElement | null>(null);
const tipEl = ref<HTMLElement | null>(null);
const nowMin = ref(minutesNow());
const tip = ref<{ name: string; text: string; left: number } | null>(null);
const guideAt = ref<number | null>(null);
let pointer = 'mouse';
let touchBlock: Booking | null = null;

const modified = (e: MouseEvent) => e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0;
const trackPx = (m: number) => (m / 1440) * (track.value?.offsetWidth ?? 0);

async function showTip(b: Booking) {
  const span = `${fa(b.time)} تا ${fa(b.until)}${b.fromYesterday ? '، از دیروز' : ''}`;
  tip.value = { name: b.name, text: span, left: trackPx(b.start) };
  await nextTick();
  const w = track.value?.offsetWidth ?? 0;
  if (tip.value && tipEl.value) tip.value.left = Math.max(0, Math.min(tip.value.left, w - tipEl.value.offsetWidth));
}
const hideTip = () => { tip.value = null; };

function onBlockClick(e: MouseEvent, b: Booking) {
  if (modified(e)) return; // the plain link opens it
  e.preventDefault();
  if (pointer !== 'mouse' && touchBlock !== b) {
    touchBlock = b;
    showTip(b);
    return;
  }
  router.push(`/visits/${b.id}`);
}
function onTrackMove(e: PointerEvent) {
  if (!canAdd.value || e.pointerType !== 'mouse') return;
  guideAt.value = (e.target as Element).closest('.vbar-block') ? null : minuteAt(track.value!, e.clientX);
}
function onTrackClick(e: MouseEvent) {
  if (!canAdd.value || (e.target as Element).closest('.vbar-block') || modified(e)) return;
  const m = minuteAt(track.value!, e.clientX);
  if (m === null) return;
  e.preventDefault();
  touchBlock = null;
  router.push({ path: '/visits/new', query: { d: props.bar.input, t: hhmm(m) } });
}
// A tap anywhere but on a block dismisses the card (touch gives no pointerleave).
function onDocDown(e: PointerEvent) {
  if ((e.target as Element).closest?.('.vbar-block')) return;
  hideTip();
  touchBlock = null;
}

// Start the view at the first booking that is not a tail from yesterday, else now (today), else 08:00.
function scrollToStart() {
  const s = scroller.value;
  if (!s || s.scrollWidth <= s.clientWidth) return;
  const starts = props.bar.bookings.filter((b: Booking) => !b.fromYesterday).map((b: Booking) => b.start);
  const m = starts.length ? Math.min(...starts) : props.bar.isToday ? minutesNow() : 480;
  s.scrollLeft = trackPx(m) - 48;
}
watch(() => props.bar, () => { hideTip(); nextTick(scrollToStart); });

let timer = 0;
onMounted(() => {
  document.addEventListener('pointerdown', onDocDown);
  timer = window.setInterval(() => { nowMin.value = minutesNow(); }, 60000);
  scrollToStart();
});
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocDown);
  clearInterval(timer);
});
</script>

<template>
  <section class="card vbar" aria-labelledby="vbar-title">
    <div class="vbar-head">
      <div class="vbar-title">
        <h2 id="vbar-title">نوار ساعت روز</h2>
        <p>{{ dateLong }} <span v-if="bar.isToday" class="chip chip-ok chip-plain">امروز</span></p>
      </div>
      <p class="vbar-sum">{{ bar.bookings.length ? `${fa(bar.bookings.length)} ویزیت، ${bookedText} رزرو` : 'همه‌ی روز آزاد است' }}</p>
      <nav class="vbar-days" aria-label="روزها">
        <RouterLink class="vbar-nav" :to="{ path: '/visits', query: { d: bar.prev } }" aria-label="روز قبل" title="روز قبل">&rsaquo;</RouterLink>
        <RouterLink v-if="!bar.isToday" class="btn btn-sm btn-ghost" to="/visits">امروز</RouterLink>
        <RouterLink class="vbar-nav" :to="{ path: '/visits', query: { d: bar.next } }" aria-label="روز بعد" title="روز بعد">&lsaquo;</RouterLink>
      </nav>
    </div>
    <div ref="scroller" class="vbar-scroll" tabindex="0" role="region" aria-label="ساعت‌های روز از ۰۰:۰۰ تا ۲۴:۰۰">
      <div ref="track" class="vbar-track" :data-new="canAdd ? '' : undefined" :data-today="bar.isToday ? '' : undefined"
        @click="onTrackClick" @pointermove="onTrackMove" @pointerleave="guideAt = null">
        <ol class="vbar-hours">
          <li v-for="h in 24" :key="h">
            <a v-if="canAdd" :href="newHref(`${hh(h - 1)}:00`)" :aria-label="`ویزیت جدید ساعت ${fa(hh(h - 1))}:۰۰`" tabindex="-1"><span>{{ fa(hh(h - 1)) }}</span></a>
            <span v-else><span>{{ fa(hh(h - 1)) }}</span></span>
          </li>
        </ol>
        <svg class="vbar-blocks" viewBox="0 0 1440 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">
          <a v-for="b in bar.bookings" :key="`${b.id}-${b.start}`" :href="router.resolve(`/visits/${b.id}`).href" tabindex="-1"
            @click="onBlockClick($event, b)">
            <rect class="vbar-block" :class="{ 'is-done': b.status === 'done' }" :x="b.start" y="14" :width="b.end - b.start" height="72" rx="5"
              @pointerdown="pointer = $event.pointerType" @pointerenter="$event.pointerType === 'mouse' && showTip(b)"
              @pointerleave="$event.pointerType === 'mouse' && hideTip()" />
          </a>
          <line v-if="bar.isToday" class="vbar-now" :x1="nowMin" :x2="nowMin" y1="0" y2="100" />
        </svg>
        <div v-if="tip" ref="tipEl" class="vbar-tip" :style="{ left: `${tip.left}px` }"><b>{{ tip.name }}</b><span>{{ tip.text }}</span></div>
        <div v-if="guideAt !== null" class="vbar-guide" :style="{ left: `${trackPx(guideAt)}px` }"><span class="vbar-guide-label">{{ fa(hhmm(guideAt)) }}</span></div>
      </div>
    </div>
    <div class="vbar-legend" aria-hidden="true">
      <span><i class="key-booked"></i>رزروشده</span><span><i class="key-done"></i>انجام‌شده</span><span><i class="key-free"></i>آزاد</span>
      <span v-if="canAdd" class="vbar-tipline">برای ویزیت جدید روی ساعتی آزاد بزنید.</span>
    </div>
  </section>
</template>
