<script setup lang="ts">
// The drag handle of the layout editors (legacy pl-grip). Pointer and keyboard handlers come from useDragList through
// the attributes the parent passes; aria-describedby points at the editor's keyboard help (#pl-help).
defineProps<{ label: string }>();
</script>

<template>
  <button type="button" class="pl-grip" data-grip :aria-label="label" aria-describedby="pl-help">
    <svg class="pl-grip-ic" viewBox="0 0 12 18" aria-hidden="true"><circle cx="3" cy="3" r="1.6" /><circle cx="9" cy="3" r="1.6" /><circle cx="3" cy="9" r="1.6" /><circle cx="9" cy="9" r="1.6" /><circle cx="3" cy="15" r="1.6" /><circle cx="9" cy="15" r="1.6" /></svg>
  </button>
</template>
