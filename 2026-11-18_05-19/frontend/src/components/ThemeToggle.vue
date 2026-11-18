<script setup lang="ts">
import Icon from './Icon.vue';
import { setTheme } from '../lib/theme';
</script>

<template>
  <form class="theme-form" @submit.prevent>
    <button class="btn btn-ghost btn-icon theme-to-dark" type="button" title="حالت تاریک" aria-label="حالت تاریک" @click="setTheme('dark')"><Icon name="moon" /></button>
    <button class="btn btn-ghost btn-icon theme-to-light" type="button" title="حالت روشن" aria-label="حالت روشن" @click="setTheme('light')"><Icon name="sun" /></button>
  </form>
</template>
