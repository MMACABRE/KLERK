<script setup lang="ts">
// The «فیزیوتراپی» card on the patient profile, above «ویزیت‌ها» (SPEC §15.6). Shows the unfinished course's circles
// and count, folds the earlier courses below, and lets users with physio edit start a course, change the count,
// tick, untick and delete a course with no ticks. An archived record is read only.
import { computed, nextTick, ref } from 'vue';
import Icon from './Icon.vue';
import ConfirmDelete from './ConfirmDelete.vue';
import PhysioBoxes, { type PhysioDay } from './PhysioBoxes.vue';
import PhysioDialogs from './PhysioDialogs.vue';
import { api } from '../api/client';
import { can } from '../lib/session';
import { fa } from '../lib/fmt';
import { useAction } from '../lib/usePage';

type Course = { id: number; sessions: number; done: number; finished: boolean; createdDay: PhysioDay; dates: PhysioDay[] };
const props = defineProps<{ code: string; courses: Course[]; archived: boolean }>();
const emit = defineEmits<{ changed: []; error: [message: string] }>();

const edit = computed(() => can('physio', 2) && !props.archived);
const current = computed(() => (props.courses[0] && !props.courses[0].finished ? props.courses[0] : null));
const no = (c: Course) => props.courses.length - props.courses.indexOf(c);
const earlier = computed(() => props.courses.filter((c) => c !== current.value));
const latest = computed(() => props.courses[0] ?? null);
const span = (c: Course) => {
  const first = c.dates[0]?.input ?? c.createdDay.input;
  const last = c.dates[c.dates.length - 1]?.input ?? c.createdDay.input;
  return `دوره ${fa(no(c))} · ${fa(c.done)} از ${fa(c.sessions)} · ${fa(first)} تا ${fa(last)}`;
};
const sub = computed(() => {
  const c = current.value;
  if (!c) return props.courses.length ? 'دوره‌ی ناتمامی ندارد' : 'دوره‌ای ندارد';
  const last = c.dates[c.done - 1]?.input;
  return `دوره ${fa(no(c))} · ${fa(c.done)} از ${fa(c.sessions)} جلسه${last ? ` · آخرین جلسه ${fa(last)}` : ''}`;
});

const dialogs = ref<InstanceType<typeof PhysioDialogs> | null>(null);
const mode = ref<'' | 'count' | 'new'>('');
const count = ref('');
const countInput = ref<HTMLInputElement | null>(null);
const act = useAction();
async function open(m: 'count' | 'new') {
  mode.value = m;
  count.value = fa(m === 'count' && current.value ? current.value.sessions : 10);
  act.error.value = '';
  await nextTick();
  countInput.value?.select();
}
async function save() {
  const c = current.value;
  const ok = await act.run(() => (mode.value === 'count' && c
    ? api.patch(`/physio/${c.id}`, { sessions: count.value })
    : api.post(`/patients/${props.code}/physio`, { sessions: count.value })));
  if (ok) { mode.value = ''; emit('changed'); }
}
async function remove(c: Course) {
  const ok = await act.run(() => api.del(`/physio/${c.id}`));
  if (ok) emit('changed');
  else emit('error', act.error.value);
}
</script>

<template>
  <section id="physio" class="card" aria-labelledby="physio-h">
    <div class="card-head">
      <div><h2 id="physio-h">فیزیوتراپی</h2><p>{{ sub }}</p></div>
      <span v-if="archived && can('physio', 2)" class="text-xs-muted">پرونده بایگانی‌شده است؛ فیزیوتراپی تغییر نمی‌کند.</span>
      <form v-else-if="edit && mode" class="ps-count-edit" @submit.prevent="save">
        <label class="text-xs-muted" for="ps-count">تعداد جلسه‌ها</label>
        <input id="ps-count" ref="countInput" v-model="count" class="input" type="text" inputmode="numeric" dir="ltr" maxlength="4" autocomplete="off" required>
        <button class="btn btn-sm btn-primary" type="submit" :disabled="act.busy.value">{{ mode === 'new' ? 'ساختن' : 'ذخیره' }}</button>
        <button class="btn btn-sm btn-ghost" type="button" @click="mode = ''">انصراف</button>
      </form>
      <button v-else-if="edit && current" class="btn btn-sm btn-ghost" type="button" @click="open('count')"><Icon name="edit" />تغییر تعداد</button>
      <button v-else-if="edit" class="btn btn-sm btn-primary" type="button" @click="open('new')"><Icon name="plus" />دوره جدید</button>
    </div>
    <div class="card-body ps-body">
      <p v-if="act.error.value && mode" class="field-error" role="alert">{{ act.error.value }}</p>
      <PhysioBoxes v-if="current" :sessions="current.sessions" :dates="current.dates" :edit="edit"
        @tick="dialogs?.tick(current)" @untick="dialogs?.untick(current)" />
      <p v-else-if="latest" class="muted">دوره‌ی {{ fa(no(latest)) }} تمام شد.<template v-if="edit"> برای دوره‌ی تازه «دوره جدید» را بزنید.</template></p>
      <p v-else class="muted">هنوز دوره‌ی فیزیوتراپی ثبت نشده است.</p>
      <details v-if="earlier.length" class="ps-history">
        <summary>دوره‌های قبلی ({{ fa(earlier.length) }})</summary>
        <ul><li v-for="c in earlier" :key="c.id">{{ span(c) }}</li></ul>
      </details>
      <div v-if="edit && current && !current.done" class="ps-foot">
        <ConfirmDelete question="این دوره‌ی بدون جلسه حذف شود؟" label="حذف دوره" :busy="act.busy.value" @confirm="remove(current)" />
      </div>
    </div>
    <PhysioDialogs ref="dialogs" @changed="emit('changed')" @error="emit('error', $event)" />
  </section>
</template>
