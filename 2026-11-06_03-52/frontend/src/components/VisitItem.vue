<script setup lang="ts">
// One visit row (legacy partial visit-item): used by /visits and the patient timeline.
import { computed } from 'vue';
import Icon from './Icon.vue';
import ConfirmDelete from './ConfirmDelete.vue';
import { api, ApiError } from '../api/client';
import { can, session } from '../lib/session';
import { fa, visitState } from '../lib/fmt';

const props = defineProps<{ v: any; showPatient?: boolean; archived?: boolean; back?: string }>();
const emit = defineEmits<{ changed: []; error: [string] }>();
const state = computed(() => visitState(props.v));
const archivedNow = computed(() => props.archived || props.v.patient?.status === 'archived');

const REMINDER_CHIP: Record<string, string> = { sent: 'chip-ok', pending: 'chip-info', sending: 'chip-info', failed: 'chip-warn', skipped: 'chip-mute' };
const reminderText = computed(() => {
  const r = props.v.reminder;
  if (!r) return '';
  return ({
    sent: 'یادآوری ارسال شد',
    pending: `یادآوری در انتظار (${r.due?.text ?? ''})`,
    sending: 'یادآوری در انتظار',
    failed: `یادآوری ناموفق: ${r.reason || ''}`,
    skipped: `یادآوری ارسال نمی‌شود: ${r.reason || ''}`,
  } as Record<string, string>)[r.status] ?? '';
});

async function act(fn: () => Promise<unknown>) {
  try {
    await fn();
    emit('changed');
  } catch (e) {
    emit('error', e instanceof ApiError ? e.message : 'خطایی رخ داد.');
  }
}
const setStatus = (status: string) => act(() => api.post(`/visits/${props.v.id}/status`, { status }));
const remove = () => act(() => api.del(`/visits/${props.v.id}`));
</script>

<template>
  <li class="visit" :class="[`visit-${v.status}`, { 'visit-overdue': v.overdue, 'visit-now': v.ongoing }]">
    <div class="visit-when">
      <b class="mono">{{ fa(v.time) }}</b>
      <span class="visit-until">تا <span class="mono">{{ fa(v.until) }}</span></span>
      <span class="visit-dur">{{ fa(v.durationMin) }} دقیقه</span>
      <span>{{ v.date.short }}</span>
    </div>
    <div class="visit-body">
      <RouterLink v-if="showPatient && v.patient" class="visit-patient" :to="`/patients/${v.patient.code}`">{{ v.patient.firstName }} {{ v.patient.lastName }}</RouterLink>
      <span class="visit-reason">{{ v.reason || 'بدون شرح' }}</span>
      <span v-if="v.notes" class="visit-notes">{{ v.notes }}</span>
      <span v-if="session.me?.smsOn && v.status === 'scheduled' && v.reminder" class="chip chip-plain" :class="REMINDER_CHIP[v.reminder.status]"><Icon name="mail" />{{ reminderText }}</span>
    </div>
    <span class="chip" :class="state.chip">{{ state.label }}</span>
    <div class="visit-actions">
      <RouterLink class="btn btn-sm" :to="`/visits/${v.id}`"><Icon name="file" />{{ can('finance') ? 'شرح و صورتحساب' : 'شرح پزشک' }}</RouterLink>
      <template v-if="can('visits', 2)">
        <button v-if="v.status !== 'done'" class="btn btn-sm" type="button" @click="setStatus('done')"><Icon name="check" />انجام شد</button>
        <button v-if="v.status === 'scheduled'" class="btn btn-sm btn-danger" type="button" @click="setStatus('cancelled')">لغو</button>
        <button v-else-if="!archivedNow" class="btn btn-sm btn-ghost" type="button" @click="setStatus('scheduled')">برنامه‌ریزی دوباره</button>
        <RouterLink class="btn btn-sm btn-ghost" :to="{ path: `/visits/${v.id}/edit`, query: back ? { back } : {} }">ویرایش</RouterLink>
        <ConfirmDelete question="این ویزیت حذف شود؟" @confirm="remove" />
      </template>
    </div>
  </li>
</template>
