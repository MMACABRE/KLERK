<script setup lang="ts">
// Page links (legacy list pages). `to(page)` builds the route for a page number.
import { computed } from 'vue';
import type { RouteLocationRaw } from 'vue-router';
import { fa } from '../lib/fmt';

const props = defineProps<{ page: number; pages: number; to: (page: number) => RouteLocationRaw }>();
const list = computed(() => {
  const out: (number | string)[] = [];
  for (let n = 1; n <= props.pages; n++) {
    if (n === 1 || n === props.pages || Math.abs(n - props.page) <= 1) out.push(n);
    else if (out[out.length - 1] !== '…') out.push('…');
  }
  return out;
});
</script>

<template>
  <div v-if="pages > 1" class="pagination">
    <RouterLink class="page-btn" :to="to(Math.max(1, page - 1))" aria-label="صفحه‌ی قبلی" :aria-disabled="page === 1 ? 'true' : undefined">&rsaquo;</RouterLink>
    <template v-for="(n, i) in list" :key="i">
      <span v-if="n === '…'" class="ellipsis">…</span>
      <RouterLink v-else class="page-btn" :to="to(n as number)" :aria-current="n === page ? 'page' : undefined">{{ fa(n) }}</RouterLink>
    </template>
    <RouterLink class="page-btn" :to="to(Math.min(pages, page + 1))" aria-label="صفحه‌ی بعدی" :aria-disabled="page === pages ? 'true' : undefined">&lsaquo;</RouterLink>
  </div>
</template>
