<script setup lang="ts">
// One card of the patient form layout editor as a home-screen grid (owner decision 2026-11-17: the dashboard's
// editor, lib/gridEditor.ts): 4 columns, boxes at their cells, empty cells shown with two spare rows. Drag a box
// anywhere in the card (the boxes it covers slide aside), tap it for edge handles to resize it, keyboard on its grip.
// The parent owns the boxes; each change comes back as `update` with every box's new cell.
import { computed, onBeforeUnmount, ref } from 'vue';
import { useGridEditor } from '../lib/gridEditor';
import type { Side } from '../lib/gridEditor';
import { cellVars as place, emptyCells, rowsUsed } from '../lib/grid-math';
import type { Item } from '../lib/grid-math';

const props = defineProps<{ items: Item[]; label: (id: string) => string; say: (t: string) => void }>();
const emit = defineEmits<{ update: [items: Item[]] }>();
const FORM_COLS = 4;
const FORM_ROWS = 80;
const LIMITS = { min: [1, 1], max: [4, 3] };
const boardEl = ref<HTMLElement | null>(null);
const grid = useGridEditor({
  items: () => props.items,
  commit: (items) => emit('update', items),
  cols: () => FORM_COLS,
  rows: FORM_ROWS,
  limits: () => LIMITS,
  label: props.label,
  say: props.say,
  board: () => boardEl.value,
  noRoom: 'جای خالی برای این کادر نیست.',
});
onBeforeUnmount(() => grid.cancel());
const slots = computed(() => emptyCells(FORM_COLS, rowsUsed(grid.shown.value, 2)));
const SIDES: Side[] = ['top', 'bottom', 'start', 'end'];
defineExpose({ grid });
</script>

<template>
  <div ref="boardEl" class="fl-grid">
    <div v-for="c in slots" :key="c.id" class="g-slot" :style="place(c)" aria-hidden="true"></div>
    <div v-if="grid.ghost.value" class="g-ghost" :class="{ 'is-bad': !grid.ghost.value.ok }" :style="place(grid.ghost.value)" aria-hidden="true"></div>
    <div v-for="b in grid.shown.value" :key="b.id" class="fl-cell" :class="{ 'is-lifted-g': grid.lifted.value === b.id, 'is-kb': grid.carried.value === b.id, 'is-sel': grid.sel.value === b.id }"
      :style="place(b)" :data-g-id="b.id" :data-box-id="b.id" @pointerdown="grid.down($event, b.id)">
      <slot :id="b.id" :item="b" :keydown="(ev: KeyboardEvent) => grid.key(ev, b.id)" :blur="() => grid.blur(b.id)" />
      <template v-if="grid.sel.value === b.id">
        <span v-for="side in SIDES" :key="side" class="g-handle" :class="`g-${side}`" aria-hidden="true" @pointerdown="grid.handleDown($event, b.id, side)"></span>
      </template>
    </div>
  </div>
</template>
