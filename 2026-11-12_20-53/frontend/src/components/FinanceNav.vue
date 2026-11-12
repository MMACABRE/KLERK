<script setup lang="ts">
// Finance sub-navigation (legacy views/finance/nav.ejs).
import { computed } from 'vue';
import { can, has } from '../lib/session';

const props = defineProps<{ here: string }>();
const items = computed(() => [
  ['overview', '/finance', 'نمای کلی', true],
  ['payments', '/finance/payments', 'پرداخت‌ها', can('patients')],
  ['pay', '/finance/pay', 'ثبت پرداخت', can('finance', 2) && can('patients')],
  ['settings', '/finance/settings', 'تنظیمات و قیمت‌ها', has('finance_settings')],
].filter((x) => x[3]) as [string, string, string, boolean][]);
</script>

<template>
  <nav class="segmented sub-nav mb-4" aria-label="بخش‌های امور مالی">
    <template v-for="[k, href, label] in items" :key="k">
      <span v-if="k === props.here" class="is-on" aria-current="page">{{ label }}</span>
      <RouterLink v-else :to="href">{{ label }}</RouterLink>
    </template>
  </nav>
</template>
