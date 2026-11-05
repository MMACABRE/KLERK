<script setup lang="ts">
// Visit length dial (legacy enhanceDial, D51): a clock face for 5-60 minutes, pills for 75 and 90. The v-model
// (a string, like the select it replaces) is the source of truth. The ruler arcs use pathLength 60, so the dash
// length equals the minutes. Keys: arrows step through the values, Home/End jump, Escape closes.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { claimDropdown, placePop, releaseDropdown, revealPop } from '../lib/popup';
import { fa } from '../lib/fmt';

const props = defineProps<{ id: string; labelId: string }>();
const model = defineModel<string>({ default: '15' });

const VALUES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 75, 90];
const RING = VALUES.filter((n) => n <= 60);
const PILLS = VALUES.filter((n) => n > 60);
const v = computed(() => Number(model.value) || 15);

const wrap = ref<HTMLElement | null>(null);
const btn = ref<HTMLButtonElement | null>(null);
const pop = ref<HTMLElement | null>(null);
const face = ref<HTMLElement | null>(null);
const open = ref(false);
const dragging = ref(false);

// Clock position: 5 at one o'clock, 60 at twelve. Percentages keep the numbers on the face at any size.
const numPos = (n: number) => {
  const a = (n / 60) * 2 * Math.PI;
  return { left: `${50 + 31.03 * Math.sin(a)}%`, top: `${50 - 31.03 * Math.cos(a)}%` };
};
const knob = computed(() => {
  const onRing = v.value <= 60;
  const a = ((onRing ? v.value : v.value - 60) / 60) * 2 * Math.PI;
  const r = onRing ? 100 : 110;
  return { cx: (116 + r * Math.sin(a)).toFixed(2), cy: (116 - r * Math.cos(a)).toFixed(2) };
});

function setValue(n: number) {
  model.value = String(n);
}
async function focusValue(n: number) {
  await nextTick();
  pop.value?.querySelector<HTMLButtonElement>(`[data-value="${n}"]`)?.focus();
}

// Dragging the ring: the angle from twelve, snapped to 5 minutes. The centre readout is not a drag target.
function pointAt(e: PointerEvent): number | null {
  const rect = face.value!.getBoundingClientRect();
  const x = e.clientX - (rect.left + rect.width / 2);
  const y = e.clientY - (rect.top + rect.height / 2);
  if (Math.hypot(x, y) < rect.width * 0.22) return null;
  let theta = Math.atan2(x, -y);
  if (theta < 0) theta += 2 * Math.PI;
  const n = Math.round((theta / (2 * Math.PI)) * 12) * 5;
  return n === 0 ? 60 : n;
}
function onDown(e: PointerEvent) {
  if ((e.target as Element).closest('.dial-num')) return;
  const n = pointAt(e);
  if (n === null) return;
  dragging.value = true;
  face.value!.setPointerCapture(e.pointerId);
  setValue(n);
}
function onMove(e: PointerEvent) {
  if (!dragging.value) return;
  const n = pointAt(e);
  if (n !== null && n !== v.value) setValue(n);
}
const endDrag = () => { dragging.value = false; };

async function show() {
  if (open.value) return;
  claimDropdown(close);
  open.value = true;
  await nextTick();
  placePop(wrap.value!, pop.value!);
  revealPop(pop.value!);
  // .is-open one frame after unhiding so the transition runs; set by hand like is-above, so Vue never rewrites the class.
  requestAnimationFrame(() => { if (open.value) pop.value?.classList.add('is-open'); });
}
function close() {
  if (!open.value) return;
  open.value = false;
  pop.value?.classList.remove('is-open');
  releaseDropdown(close);
}
const toggle = () => (open.value ? close() : show());

async function onBtnKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  e.preventDefault();
  await show();
  focusValue(v.value);
}
function onPopKey(e: KeyboardEvent) {
  const i = VALUES.indexOf(v.value);
  let j: number;
  if (e.key === 'ArrowRight' || e.key === 'ArrowUp') j = i + 1;
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') j = i - 1;
  else if (e.key === 'Home') j = 0;
  else if (e.key === 'End') j = VALUES.length - 1;
  else return;
  e.preventDefault();
  const next = VALUES[Math.min(VALUES.length - 1, Math.max(0, j))];
  setValue(next);
  focusValue(next);
}
function onEsc(e: KeyboardEvent) {
  if (!open.value) return;
  e.preventDefault();
  close();
  btn.value?.focus();
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
// A click on the field label focuses the button instead of opening the dial.
function onLabelClick(e: MouseEvent) {
  e.preventDefault();
  btn.value?.focus();
}
onMounted(() => {
  document.addEventListener('pointerdown', onDocDown);
  window.addEventListener('resize', onResize);
  document.getElementById(props.labelId)?.addEventListener('click', onLabelClick);
});
onBeforeUnmount(() => {
  close();
  document.removeEventListener('pointerdown', onDocDown);
  window.removeEventListener('resize', onResize);
  document.getElementById(props.labelId)?.removeEventListener('click', onLabelClick);
});
</script>

<template>
  <span ref="wrap" class="dial" @keydown.esc="onEsc" @focusout="onFocusOut">
    <button :id="id" ref="btn" type="button" class="select dial-btn" aria-haspopup="dialog" :aria-expanded="open"
      :aria-labelledby="`${labelId} ${id}`" @click="toggle" @keydown="onBtnKey">{{ fa(v) }} دقیقه</button>
    <div v-show="open" ref="pop" class="dial-pop" role="dialog" aria-label="مدت ویزیت" tabindex="-1" @keydown="onPopKey">
      <div ref="face" class="dial-face" :class="{ 'is-dragging': dragging }" @pointerdown="onDown" @pointermove="onMove" @pointerup="endDrag" @pointercancel="endDrag">
        <svg class="dial-ring" viewBox="0 0 232 232" aria-hidden="true" focusable="false">
          <circle class="dial-plate" cx="116" cy="116" r="112" />
          <circle class="dial-track" cx="116" cy="116" r="100" />
          <circle class="dial-arc" cx="116" cy="116" r="100" pathLength="60" transform="rotate(-90 116 116)" :stroke-dasharray="`${Math.min(v, 60)} 60`" />
          <circle v-if="v > 60" class="dial-extra" cx="116" cy="116" r="110" pathLength="60" transform="rotate(-90 116 116)" :stroke-dasharray="`${v - 60} 60`" />
          <circle class="dial-knob" r="9" :cx="knob.cx" :cy="knob.cy" />
        </svg>
        <button v-for="n in RING" :key="n" type="button" class="dial-num" :class="{ 'is-on': n === v }" :style="numPos(n)" :data-value="n"
          :aria-label="`${fa(n)} دقیقه`" :aria-pressed="n === v" :tabindex="n === v ? 0 : -1" @click="setValue(n)">{{ fa(n) }}</button>
        <div class="dial-center" aria-hidden="true"><b class="dial-value">{{ fa(v) }}</b><span class="dial-unit">دقیقه</span></div>
      </div>
      <div class="dial-more">
        <span>بیش از یک ساعت</span>
        <div class="dial-pills">
          <button v-for="n in PILLS" :key="n" type="button" class="dial-pill" :class="{ 'is-on': n === v }" :data-value="n"
            :aria-label="`${fa(n)} دقیقه`" :aria-pressed="n === v" :tabindex="n === v ? 0 : -1" @click="setValue(n)">{{ fa(n) }}</button>
        </div>
      </div>
    </div>
  </span>
</template>
