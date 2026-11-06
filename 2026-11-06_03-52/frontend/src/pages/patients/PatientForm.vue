<script setup lang="ts">
// New / edit patient (legacy views/patients/form.ejs): boxes in the clinic's layout order (D52), custom boxes (D53),
// optional code box (D48) and first documents (D49) on the new form; the code change form on the edit page (D36).
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import FormBox from '../../components/FormBox.vue';
import DropZone from '../../components/DropZone.vue';
import { api } from '../../api/client';
import { can, has, refreshMe, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const router = useRouter();
const code = route.params.code ? String(route.params.code) : '';
const editing = Boolean(code);
const showAll = ref(route.query.all === '1');
const values = reactive<Record<string, any>>({});
const files = ref<File[]>([]);
const shrinking = ref(false);
const { busy, error, fields, run } = useAction();
const codeAct = useAction();
const codeForm = ref({ code: '', confirm: '' });

const { data, error: loadError, loading } = useLoad(async () => {
  const d = await api.get('/patients/form', editing ? { code } : {});
  Object.assign(values, d.values);
  setTitle(editing ? `ویرایش ${d.patient.firstName} ${d.patient.lastName}` : 'بیمار جدید');
  return d;
});
const title = computed(() => (editing && data.value ? `ویرایش ${data.value.patient.firstName} ${data.value.patient.lastName}` : 'بیمار جدید'));

function boxOf(ref: string) {
  if (ref.startsWith('c:')) return data.value.customBoxes[ref.slice(2)];
  return data.value.builtin.boxes.find((b: any) => b.id === ref) ?? { id: ref };
}
const cards = computed(() => (data.value ? data.value.layout.cards.filter((c: any) => c.boxes.length) : []));
const cardTitle = (card: any) => card.label ?? data.value.builtin.cards.find((c: any) => c.id === card.id)?.label;
const shownIds = computed(() => new Set(cards.value.flatMap((c: any) => c.boxes.map((b: any) => b.id))));
const hidden = computed(() => (data.value ? [
  ...data.value.builtin.boxes.filter((b: any) => !shownIds.value.has(b.id)).map((b: any) => b.id),
  ...Object.values(data.value.customBoxes).filter((b: any) => !shownIds.value.has(`c:${b.id}`)).map((b: any) => `c:${b.id}`),
] : []));
const rendered = computed(() => [...shownIds.value, ...(editing && showAll.value ? hidden.value : [])]);

async function save() {
  if (shrinking.value) return;
  const payload: Record<string, any> = { ...values, boxes: rendered.value.join(','), sms_optout_form: rendered.value.includes('sms_optout') ? '1' : '' };
  if (editing) {
    const ok = await run(() => api.patch(`/patients/${code}`, payload));
    if (ok) { refreshMe(); router.push(`/patients/${code}`); }
    return;
  }
  const form = new FormData();
  for (const [k, v] of Object.entries(payload)) if (v !== undefined && v !== null) form.append(k, String(v));
  for (const f of files.value) form.append('files', f);
  const out = await run(() => api.post('/patients', form));
  if (out) { refreshMe(); router.push(`/patients/${out.code}${out.files ? '#docs' : ''}`); }
}

async function changeCode() {
  const out = await codeAct.run(() => api.post(`/patients/${code}/change-code`, codeForm.value));
  if (out) router.push({ path: `/patients/${out.code}`, query: { code: 'changed' } });
}
</script>

<template>
  <div class="breadcrumb">
    <RouterLink to="/patients" lang="en">Patients</RouterLink> / <span lang="en">{{ editing ? 'Edit Patient' : 'New Patient' }}</span>
  </div>
  <p v-if="loading" class="muted">در حال بارگذاری…</p>
  <div v-else-if="loadError" class="card"><div class="card-body"><p class="info-box" role="alert">{{ loadError }}</p></div></div>
  <template v-else-if="data">
    <form class="card" novalidate @submit.prevent="save">
      <div class="card-body form-section">
        <h1>{{ title }}</h1>
        <div v-if="error" class="info-box" role="alert">{{ error }}</div>
        <p v-if="editing" class="muted">کد بیمار: <span class="mono">{{ data.patient.code }}</span>{{ has('patient_code') ? ' (برای تغییر، فرم پایین صفحه)' : '' }}</p>
        <div v-if="!editing && data.nextCode" class="form-grid">
          <FormBox :box="{ id: 'code' }" :values="values" :errors="fields" :next-code="data.nextCode" />
        </div>
        <template v-for="card in cards" :key="card.id">
          <h2>{{ cardTitle(card) }}</h2>
          <div class="form-grid">
            <FormBox v-for="ref in card.boxes" :key="ref.id" :box="boxOf(ref.id)" :required="ref.req === true" :values="values"
              :errors="fields" :suggestions="data.suggestions" />
          </div>
        </template>
        <p v-if="editing && !showAll && hidden.length"><a href="#more" @click.prevent="showAll = true">نمایش همه‌ی کادرها</a></p>
        <template v-if="editing && showAll && hidden.length">
          <h2 id="more">سایر کادرها</h2>
          <div class="form-grid">
            <FormBox v-for="id in hidden" :key="id" :box="boxOf(id)" :values="values" :errors="fields" :suggestions="data.suggestions" />
          </div>
        </template>

        <template v-if="!editing && can('documents', 2)">
          <h2>مدارک پزشکی <span class="muted">(اختیاری)</span></h2>
          <div class="form-grid">
            <div class="field span-2">
              <DropZone id="f-files" v-model="files" multiple :hint="`تا ${fa(data.newFilesMax)} فایل PDF، JPG، PNG یا DICOM، روی هم تا ۳۰ مگابایت · عکس‌های بزرگ خودکار کوچک می‌شوند`" @busy="shrinking = $event" />
              <p v-if="fields.files" id="f-files-err" class="field-error" role="alert">{{ fields.files }}</p>
            </div>
            <FormBox :box="{ id: 'doc_category' }" :values="values" :errors="fields" />
          </div>
        </template>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="busy || shrinking"><Icon name="check" />ذخیره</button>
          <RouterLink class="btn" :to="editing ? `/patients/${code}` : '/patients'">انصراف</RouterLink>
        </div>
      </div>
    </form>

    <form v-if="editing && has('patient_code')" id="code" class="card mt-6" novalidate aria-labelledby="code-h" @submit.prevent="changeCode">
      <div class="card-body form-section">
        <h2 id="code-h">تغییر کد بیمار</h2>
        <p class="muted">کد فعلی <span class="mono">{{ data.patient.code }}</span> است. با تغییر کد، پوشه‌ی پرونده روی سرور هم به نام تازه درمی‌آید و همه‌ی صفحه‌ها و خروجی‌ها کد تازه را نشان می‌دهند. کد قبلی آزاد می‌شود.</p>
        <div v-if="codeAct.error.value" id="code-err" class="info-box" role="alert">{{ codeAct.error.value }}</div>
        <div class="form-grid">
          <div class="field"><label for="f-new-code">کد تازه</label><input id="f-new-code" v-model="codeForm.code" class="input mono" type="text" dir="ltr" placeholder="P-000123" maxlength="20" autocomplete="off" required><span class="hint">مثل P-000123 یا فقط عدد آن</span></div>
          <div class="field"><label for="f-new-code2">تکرار کد تازه</label><input id="f-new-code2" v-model="codeForm.confirm" class="input mono" type="text" dir="ltr" placeholder="P-000123" maxlength="20" autocomplete="off" required></div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="codeAct.busy.value"><Icon name="check" />تغییر کد</button>
        </div>
      </div>
    </form>
  </template>
</template>
