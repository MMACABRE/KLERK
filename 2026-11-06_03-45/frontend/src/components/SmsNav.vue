<script setup lang="ts">
// SMS sub-navigation (legacy views/sms/nav.ejs).
import { computed } from 'vue';
import { has } from '../lib/session';

const props = defineProps<{ here: string }>();
const items = computed(() => ([
  ['log', '/sms', 'گزارش ارسال', true],
  ['bulk', '/sms/bulk', 'ارسال گروهی', has('sms_bulk')],
  ['settings', '/sms/settings', 'تنظیمات', true],
] as [string, string, string, boolean][]).filter((x) => x[3]));
</script>

<template>
  <nav class="segmented sub-nav mb-4" aria-label="بخش‌های پیامک">
    <template v-for="[k, href, label] in items" :key="k">
      <span v-if="k === props.here" class="is-on" aria-current="page">{{ label }}</span>
      <RouterLink v-else :to="href">{{ label }}</RouterLink>
    </template>
  </nav>
</template>
