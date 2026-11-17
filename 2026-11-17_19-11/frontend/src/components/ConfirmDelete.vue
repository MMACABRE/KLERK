<script setup lang="ts">
// Two-step delete without a browser dialog (legacy partial confirm-delete).
import { ref } from 'vue';
import Icon from './Icon.vue';

withDefaults(defineProps<{ question: string; label?: string; busy?: boolean }>(), { label: 'حذف' });
const emit = defineEmits<{ confirm: [] }>();
const box = ref<HTMLDetailsElement | null>(null);
function yes() {
  if (box.value) box.value.open = false;
  emit('confirm');
}
</script>

<template>
  <details ref="box" class="confirm">
    <summary class="btn btn-sm btn-ghost btn-quiet-danger"><Icon name="trash" /><span>{{ label }}</span></summary>
    <form class="confirm-pop" @submit.prevent="yes">
      <p>{{ question }}</p>
      <button class="btn btn-sm btn-danger" type="submit" :disabled="busy">بله، حذف شود</button>
    </form>
  </details>
</template>
