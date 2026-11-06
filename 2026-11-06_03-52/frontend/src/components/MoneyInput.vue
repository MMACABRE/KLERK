<script setup lang="ts">
// Amount box that groups thousands while typing (legacy enhanceMoney, D39). Text with anything besides digits and
// separators (a pasted "50000 R") is left as typed: the server reads the suffix or refuses it.
import { ref, watch } from 'vue';

defineProps<{ id?: string; name?: string; placeholder?: string; required?: boolean }>();
const model = defineModel<string>({ default: '' });
const input = ref<HTMLInputElement | null>(null);

const toLatin = (s: string) => s.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
const group = (digits: string) => digits.replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const plain = (v: string) => /^[\d,٬،\s]*$/.test(toLatin(v));

function regroup(digits: string, before: number) {
  const text = group(digits);
  model.value = text;
  if (input.value) input.value.value = text;
  let pos = 0;
  for (let seen = 0; pos < text.length && seen < before; pos += 1) if (/\d/.test(text[pos])) seen += 1;
  if (document.activeElement === input.value) input.value?.setSelectionRange(pos, pos);
}

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  model.value = el.value;
  if (!plain(el.value)) return;
  const value = toLatin(el.value);
  const caret = el.selectionStart ?? value.length;
  const before = value.slice(0, caret).replace(/\D/g, '').length;
  const digits = value.replace(/\D/g, '');
  const zeros = Math.min(digits.length - group(digits).replace(/\D/g, '').length, before);
  regroup(digits, before - zeros);
}

function onKey(e: KeyboardEvent) {
  const el = e.target as HTMLInputElement;
  if ((e.key !== 'Backspace' && e.key !== 'Delete') || el.selectionStart !== el.selectionEnd || !plain(el.value)) return;
  const pos = el.selectionStart ?? 0;
  const comma = e.key === 'Backspace' ? pos - 1 : pos;
  if (el.value[comma] !== ',') return;
  e.preventDefault();
  const target = e.key === 'Backspace' ? comma - 1 : comma + 1;
  const before = el.value.slice(0, target).replace(/\D/g, '').length;
  regroup((el.value.slice(0, target) + el.value.slice(target + 1)).replace(/\D/g, ''), before);
}

watch(model, (v) => {
  if (input.value && input.value.value !== v) input.value.value = v;
});
</script>

<template>
  <input :id="id" ref="input" class="input input-money" type="text" inputmode="numeric" dir="ltr" autocomplete="off"
    :name="name" :placeholder="placeholder" :required="required" :value="model" @input="onInput" @keydown="onKey">
</template>
