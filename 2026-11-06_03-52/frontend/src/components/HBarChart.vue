<script setup lang="ts">
// Horizontal bars for shares (legacy charts.js hbarChart): label on the right, bar grows leftwards, value at left.
import { computed } from 'vue';

const props = withDefaults(defineProps<{ data: { label: string; value: number }[]; label: string; fmt: (v: number) => string; width?: number; row?: number }>(), { width: 460, row: 28 });
const g = computed(() => {
  const labelW = 120; const valueW = 104;
  const barMax = props.width - labelW - valueW - 16;
  const max = Math.max(1, ...props.data.map((d) => d.value));
  const height = Math.max(props.row, props.data.length * props.row) + 4;
  const barStart = props.width - labelW - 8;
  const rows = props.data.map((d, i) => {
    const yy = i * props.row + 4;
    const w = Math.max((d.value / max) * barMax, d.value > 0 ? 2 : 0);
    return { ...d, ty: yy + props.row / 2 + 1, bx: barStart - w, by: yy + 5, w, bh: props.row - 12, hi: i === 0 };
  });
  return { height, rows };
});
</script>

<template>
  <svg class="chart" direction="ltr" :viewBox="`0 0 ${width} ${g.height}`" role="img" :aria-label="label" preserveAspectRatio="xMidYMid meet">
    <template v-for="(r, i) in g.rows" :key="i">
      <text class="ch-label" :x="width" :y="r.ty.toFixed(1)" text-anchor="end">{{ r.label }}</text>
      <rect class="ch-bar" :class="{ 'ch-bar-hi': r.hi }" :x="r.bx.toFixed(1)" :y="r.by.toFixed(1)" :width="r.w.toFixed(1)" :height="r.bh.toFixed(1)" rx="4"><title>{{ `${r.label}: ${fmt(r.value)}` }}</title></rect>
      <text class="ch-value" x="0" :y="r.ty.toFixed(1)" text-anchor="start">{{ fmt(r.value) }}</text>
    </template>
  </svg>
</template>
