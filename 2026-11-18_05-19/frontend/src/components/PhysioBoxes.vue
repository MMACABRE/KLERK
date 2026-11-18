<script setup lang="ts">
// One physiotherapy course as numbered circles (SPEC §15.6, mockup docs/design/physio/): ticked ones filled with a
// check, the next one dashed (tap to tick), the last ticked one tappable to untick. Two rows up to 12 sessions,
// three above. `dots` draws the 11 px read-only version of the dashboard widget.
import { computed } from 'vue';
import Icon from './Icon.vue';
import { fa } from '../lib/fmt';

export type PhysioDay = { input: string };
const props = defineProps<{ sessions: number; dates: PhysioDay[]; edit?: boolean; dots?: boolean }>();
const emit = defineEmits<{ tick: []; untick: [] }>();

const done = computed(() => props.dates.length);
const cols = computed(() => Math.max(1, Math.ceil(props.sessions / (props.sessions > 12 ? 3 : 2))));
const boxes = computed(() => Array.from({ length: props.sessions }, (_, i) => {
  const n = i + 1;
  const date = props.dates[i]?.input;
  const isNext = n === done.value + 1;
  const isLast = n === done.value && n > 0;
  return {
    n, isDone: n <= done.value, isNext, live: Boolean(props.edit && !props.dots && (isNext || isLast)),
    title: date ? `جلسه ${fa(n)} · ${fa(date)}` : `جلسه ${fa(n)}`,
  };
}));
</script>

<template>
  <div class="ps-boxes" :class="{ 'ps-dots': dots }" :style="{ '--cols': cols }">
    <template v-for="b in boxes" :key="b.n">
      <button v-if="b.live" type="button" class="ps-box" :class="{ 'is-done': b.isDone, 'is-next': b.isNext, 'is-last': !b.isNext }"
        :title="b.title" :aria-label="b.isNext ? `ثبت جلسه ${fa(b.n)}` : `برداشتن جلسه ${fa(b.n)}`"
        @click="b.isNext ? emit('tick') : emit('untick')">
        <template v-if="b.isDone"><Icon name="check" /><span class="ps-n">{{ fa(b.n) }}</span></template>
        <template v-else>{{ fa(b.n) }}</template>
      </button>
      <span v-else class="ps-box" :class="{ 'is-done': b.isDone, 'is-next': b.isNext && edit }" :title="b.title" role="img"
        :aria-label="b.isDone ? `${b.title}، انجام شد` : b.title">
        <template v-if="b.isDone && !dots"><Icon name="check" /><span class="ps-n">{{ fa(b.n) }}</span></template>
        <template v-else-if="!dots">{{ fa(b.n) }}</template>
      </span>
    </template>
  </div>
</template>
