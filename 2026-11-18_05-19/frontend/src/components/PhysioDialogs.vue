<script setup lang="ts">
// The two confirmations of SPEC §15.6: every tick asks first (with the last session's date and a date field set to
// today), every untick asks first. The server checks the session number, so a stale page gets 409 and redraws.
import { ref } from 'vue';
import JalaliInput from './JalaliInput.vue';
import { api, ApiError } from '../api/client';
import { fa } from '../lib/fmt';
import * as jc from '../lib/jalali-math';
import type { PhysioDay } from './PhysioBoxes.vue';

export type PhysioCourseRef = { id: number; dates: PhysioDay[] };
const emit = defineEmits<{ changed: []; error: [message: string] }>();

const tickBox = ref<HTMLDialogElement | null>(null);
const untickBox = ref<HTMLDialogElement | null>(null);
const course = ref<PhysioCourseRef | null>(null);
const date = ref('');
const error = ref('');
const busy = ref(false);

const n = () => (course.value?.dates.length ?? 0);
const lastInput = () => course.value?.dates[n() - 1]?.input ?? '';

function tick(c: PhysioCourseRef) {
  course.value = c;
  date.value = jc.format(jc.today());
  error.value = '';
  tickBox.value?.showModal();
}
function untick(c: PhysioCourseRef) {
  course.value = c;
  error.value = '';
  untickBox.value?.showModal();
}

async function send(box: HTMLDialogElement | null, fn: () => Promise<unknown>) {
  busy.value = true;
  error.value = '';
  try {
    await fn();
    box?.close();
    emit('changed');
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      error.value = e.fields.date || e.message;
      return;
    }
    box?.close();
    emit('error', e instanceof ApiError ? e.message : 'خطایی رخ داد.');
    emit('changed');
  } finally {
    busy.value = false;
  }
}
const saveTick = () => send(tickBox.value, () => api.post(`/physio/${course.value!.id}/sessions`, { number: n() + 1, date: date.value }));
const saveUntick = () => send(untickBox.value, () => api.del(`/physio/${course.value!.id}/sessions/${n()}`));
defineExpose({ tick, untick });
</script>

<template>
  <dialog ref="tickBox" class="app-dialog" aria-labelledby="ps-tick-h">
    <form class="card" @submit.prevent="saveTick">
      <div class="card-head"><h2 id="ps-tick-h">ثبت جلسه</h2></div>
      <div class="card-body stack-lg">
        <p v-if="n()">آخرین جلسه: {{ fa(lastInput()) }}. جلسه {{ fa(n() + 1) }} ثبت شود؟</p>
        <p v-else>هنوز جلسه‌ای ثبت نشده است. جلسه {{ fa(1) }} ثبت شود؟</p>
        <div class="field">
          <label for="ps-tick-date">تاریخ جلسه</label>
          <JalaliInput id="ps-tick-date" v-model="date" placeholder="۱۴۰۳/۰۵/۱۲" />
          <p v-if="error" class="field-error" role="alert">{{ error }}</p>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="busy">ثبت</button>
          <button class="btn btn-ghost" type="button" @click="tickBox?.close()">انصراف</button>
        </div>
      </div>
    </form>
  </dialog>
  <dialog ref="untickBox" class="app-dialog" aria-labelledby="ps-untick-h">
    <form class="card" @submit.prevent="saveUntick">
      <div class="card-head"><h2 id="ps-untick-h">برداشتن جلسه</h2></div>
      <div class="card-body stack-lg">
        <p>جلسه {{ fa(n()) }} ({{ fa(lastInput()) }}) برداشته شود؟</p>
        <p v-if="error" class="info-box" role="alert">{{ error }}</p>
        <div class="form-actions">
          <button class="btn btn-danger" type="submit" :disabled="busy">بله، برداشته شود</button>
          <button class="btn btn-ghost" type="button" @click="untickBox?.close()">انصراف</button>
        </div>
      </div>
    </form>
  </dialog>
</template>
