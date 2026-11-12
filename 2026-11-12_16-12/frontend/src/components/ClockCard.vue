<script setup lang="ts">
// Live clock (legacy partial clock-card + enhanceClock, D24): CSS seven-segment digits ticking from the browser
// clock; screen readers get the time once a minute.
import { computed, onBeforeUnmount, ref } from 'vue';
import { fa } from '../lib/fmt';

const now = ref(new Date());
const timer = setInterval(() => { now.value = new Date(); }, 1000);
onBeforeUnmount(() => clearInterval(timer));
const p = (n: number) => String(n).padStart(2, '0');
const h = computed(() => p(now.value.getHours()));
const m = computed(() => p(now.value.getMinutes()));
const s = computed(() => p(now.value.getSeconds()));
const jalaliFmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const gregFmt = new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const jalali = computed(() => {
  const x = Object.fromEntries(jalaliFmt.formatToParts(now.value).map((q) => [q.type, q.value]));
  return `${x.weekday} ${x.day} ${x.month} ${x.year}`;
});
const greg = computed(() => gregFmt.format(now.value).replace(',', ''));
const sr = computed(() => fa(`${h.value}:${m.value}`));
const SEGS = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
</script>

<template>
  <section class="clock-card" aria-label="ساعت و تاریخ">
    <div class="clock-time" aria-hidden="true">
      <span class="clock-group"><span v-for="(c, i) in h" :key="`h${i}`" class="seg" :data-n="c"><i v-for="x in SEGS" :key="x" :class="x"></i></span></span>
      <span class="clock-colon"><i></i><i></i></span>
      <span class="clock-group"><span v-for="(c, i) in m" :key="`m${i}`" class="seg" :data-n="c"><i v-for="x in SEGS" :key="x" :class="x"></i></span></span>
      <span class="clock-group clock-sec"><span v-for="(c, i) in s" :key="`s${i}`" class="seg" :data-n="c"><i v-for="x in SEGS" :key="x" :class="x"></i></span></span>
    </div>
    <span class="sr-only">{{ sr }}</span>
    <div class="clock-dates">
      <span class="clock-jalali">{{ jalali }}</span>
      <span class="clock-greg" lang="en">{{ greg }}</span>
    </div>
  </section>
</template>
