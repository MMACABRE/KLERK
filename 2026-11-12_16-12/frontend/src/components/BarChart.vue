<script setup lang="ts">
// Vertical bars, the same SVG as legacy src/lib/charts.js barChart (D29): oldest on the right, role="img" with an
// aria-label; every bar has a <title>. No chart library; colours come from page-finance.css classes.
import { computed } from 'vue';

const props = withDefaults(defineProps<{ data: { label: string; value: number; title?: string; highlight?: boolean }[]; label: string; tick?: number; fmt: (v: number) => string; width?: number; height?: number }>(), { tick: 1, width: 460, height: 210 });

function niceMax(max: number) {
  if (max <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(max));
  return [1, 2, 5, 10].map((m) => m * p).find((v) => v >= max) ?? max;
}
const g = computed(() => {
  const padTop = 12; const padBottom = 28; const padSide = 44;
  const plotW = props.width - padSide - 8;
  const plotH = props.height - padTop - padBottom;
  const top = niceMax(Math.max(0, ...props.data.map((d) => d.value)));
  const step = plotW / Math.max(props.data.length, 1);
  const barW = Math.max(2, Math.min(36, step * 0.66));
  const y = (v: number) => padTop + plotH - (Math.max(v, 0) / top) * plotH;
  const grid = [0, 0.5, 1].map((f) => ({ gy: y(top * f), text: props.fmt(top * f) }));
  const bars = props.data.map((d, i) => {
    const cx = plotW - (i + 0.5) * step;
    const by = y(d.value);
    const h = Math.max(padTop + plotH - by, d.value > 0 ? 1.5 : 0);
    return { ...d, cx, x: cx - barW / 2, y: padTop + plotH - h, h, showLabel: i % props.tick === 0 };
  });
  return { plotW, barW, grid, bars };
});
</script>

<template>
  <svg class="chart" direction="ltr" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="label" preserveAspectRatio="xMidYMid meet">
    <template v-for="(l, i) in g.grid" :key="`g${i}`">
      <line class="ch-grid" x1="0" :x2="(g.plotW + 8).toFixed(1)" :y1="l.gy.toFixed(1)" :y2="l.gy.toFixed(1)" />
      <text class="ch-axis" :x="(width - 4).toFixed(1)" :y="(l.gy + 4).toFixed(1)" text-anchor="end">{{ l.text }}</text>
    </template>
    <template v-for="(b, i) in g.bars" :key="`b${i}`">
      <rect class="ch-bar" :class="{ 'ch-bar-hi': b.highlight }" :x="b.x.toFixed(1)" :y="b.y.toFixed(1)" :width="g.barW.toFixed(1)" :height="b.h.toFixed(1)" rx="3"><title>{{ b.title ?? `${b.label}: ${fmt(b.value)}` }}</title></rect>
      <text v-if="b.showLabel" class="ch-label" :x="b.cx.toFixed(1)" :y="(height - 8).toFixed(1)" text-anchor="middle">{{ b.label }}</text>
    </template>
  </svg>
</template>
