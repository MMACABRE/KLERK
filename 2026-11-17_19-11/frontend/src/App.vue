<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import AppShell from './components/AppShell.vue';
import Sprite from './components/Sprite.vue';
import { session } from './lib/session';

const route = useRoute();
const shell = computed(() => Boolean(session.me) && !route.meta.bare);
</script>

<template>
  <Sprite />
  <AppShell v-if="shell">
    <RouterView :key="route.fullPath" />
  </AppShell>
  <RouterView v-else :key="route.fullPath" />
</template>
