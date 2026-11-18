<script setup lang="ts">
// Password box with a show/hide button (legacy enhancePassword).
import { ref } from 'vue';
import Icon from './Icon.vue';

defineProps<{ id?: string; name?: string; autocomplete?: string; required?: boolean }>();
const model = defineModel<string>({ default: '' });
const shown = ref(false);
const input = ref<HTMLInputElement | null>(null);
function toggle() {
  shown.value = !shown.value;
  input.value?.focus();
}
defineExpose({ hide: () => { shown.value = false; } });
</script>

<template>
  <span class="field-addon">
    <input :id="id" ref="input" v-model="model" class="input" :type="shown ? 'text' : 'password'" :name="name"
      :autocomplete="autocomplete" dir="ltr" :required="required">
    <button type="button" class="addon-btn" :aria-pressed="shown ? 'true' : 'false'" :aria-label="shown ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'"
      :title="shown ? 'پنهان کردن رمز عبور' : 'نمایش رمز عبور'" @click="toggle"><Icon name="eye" /></button>
  </span>
</template>
