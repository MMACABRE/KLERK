<script setup lang="ts">
// A folder in the documents gallery, Windows style (owner, 2026-11-16): it sits before the loose files, shows its
// name and how many files it holds, and opens on click. It is also a drop target for dragged cards (data-drop).
import Icon from './Icon.vue';
import { fa } from '../lib/fmt';

defineProps<{ f: { id: number; name: string; count: number }; dropOn?: string | null }>();
const emit = defineEmits<{ open: [string] }>();
</script>

<template>
  <button type="button" class="doc-tile folder-tile" :class="{ 'is-drop': dropOn === String(f.id) }" :data-drop="String(f.id)" :data-folder="String(f.id)" @click="emit('open', String(f.id))">
    <span class="doc-media doc-media-file"><span class="doc-type"><Icon name="folder" /><b>پوشه</b></span></span>
    <span class="doc-body">
      <span class="doc-head"><b class="doc-name folder-name" :title="f.name">{{ f.name }}</b></span>
      <span class="doc-sub">{{ fa(f.count) }} فایل</span>
    </span>
  </button>
</template>
