<script setup lang="ts">
// SMS wording editor (legacy enhanceSmsTemplate): token buttons insert at the cursor (or drag into the text),
// the length and the number of SMS parts (70 characters, then 67 per part), and an optional sample line.
import { computed, ref } from 'vue';
import { fa } from '../lib/fmt';

const props = defineProps<{ id: string; rows?: number; maxlength?: number; tokens?: boolean; sample?: Record<string, string> | null; disabled?: boolean }>();
const model = defineModel<string>({ default: '' });
const area = ref<HTMLTextAreaElement | null>(null);
const parts = (n: number) => (n === 0 ? 0 : n <= 70 ? 1 : Math.ceil(n / 67));
const shown = computed(() => {
  if (!props.sample) return model.value;
  const s = props.sample;
  return model.value.replace(/{(?:نام|تاریخ|ساعت)}/g, (m) => ({ '{نام}': s.name, '{تاریخ}': s.date, '{ساعت}': s.time } as Record<string, string>)[m] ?? m);
});
const count = computed(() => {
  const n = Array.from(shown.value).length;
  return `${fa(n)} نویسه · ${fa(parts(n))} پیامک`;
});
function insert(token: string) {
  const el = area.value;
  if (!el) return;
  el.setRangeText(token, el.selectionStart, el.selectionEnd, 'end');
  model.value = el.value;
  el.focus();
}
function drag(e: DragEvent, token: string) {
  e.dataTransfer?.setData('text/plain', token);
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy';
}
</script>

<template>
  <textarea :id="id" ref="area" v-model="model" class="textarea" :rows="rows ?? 3" :maxlength="maxlength ?? 500" dir="rtl" required :disabled="disabled"></textarea>
  <div v-if="tokens" class="token-row">
    <span class="hint">بکشید یا بزنید تا در متن بنشیند:</span>
    <button v-for="[t, l] in [['{نام}', 'نام'], ['{تاریخ}', 'تاریخ'], ['{ساعت}', 'ساعت']]" :key="t" class="btn btn-sm" type="button" draggable="true" @click="insert(t)" @dragstart="drag($event, t)">{{ l }}</button>
  </div>
  <slot />
  <span class="sms-count" aria-live="polite">{{ count }}</span>
  <p v-if="sample" class="sms-sample">نمونه: <span>{{ shown }}</span></p>
</template>
