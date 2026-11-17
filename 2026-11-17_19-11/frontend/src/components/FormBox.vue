<script setup lang="ts">
// One box of the patient form (legacy partial form-box, D52, D53). `values` is the form's reactive values object:
// built-in boxes use their field name, custom boxes `c_<id>`. `disabled` is the layout editor's preview.
import { computed } from 'vue';
import JalaliInput from './JalaliInput.vue';
import { CATEGORY, STATUS } from '../lib/fmt';
import { vFloat } from '../lib/directives';

const props = defineProps<{
  box: any; required?: boolean; values: Record<string, any>; errors?: Record<string, string>;
  suggestions?: Record<string, string[]>; nextCode?: string | null; disabled?: boolean;
}>();

const BUILTIN: Record<string, any> = {
  code: { kind: 'text', label: 'کد بیمار (اختیاری)', dir: 'ltr', maxlength: 20, code: true },
  doc_category: { kind: 'select', label: 'طبقه‌بندی مدارک', options: Object.entries(CATEGORY) },
  first_name: { kind: 'text', label: 'نام', maxlength: 80 },
  last_name: { kind: 'text', label: 'نام خانوادگی', maxlength: 80 },
  father_name: { kind: 'text', label: 'نام پدر', maxlength: 80 },
  national_id: { kind: 'text', label: 'کد ملی', dir: 'ltr', inputmode: 'numeric', maxlength: 10, hint: '۱۰ رقم' },
  birth_date: { kind: 'date', label: 'تاریخ تولد' },
  sex: { kind: 'select', label: 'جنسیت', options: [['', 'مشخص نشده'], ['female', 'زن'], ['male', 'مرد']] },
  status: { kind: 'select', label: 'وضعیت', options: Object.entries(STATUS).map(([k, s]) => [k, s.label]) },
  visit_reason: { kind: 'text', label: 'علت مراجعه', maxlength: 1000, list: 'visit_reason', hint: 'از فهرست انتخاب کنید یا متن تازه بنویسید' },
  referral: { kind: 'text', label: 'معرف', maxlength: 120, list: 'referral', hint: 'از فهرست انتخاب کنید یا نام تازه بنویسید' },
  phone: { kind: 'text', label: 'تلفن همراه', dir: 'ltr', inputmode: 'tel', maxlength: 20 },
  email: { kind: 'text', label: 'ایمیل', type: 'email', dir: 'ltr', maxlength: 120 },
  city: { kind: 'text', label: 'شهر', maxlength: 100 },
  sms_optout: { kind: 'optout' },
  address: { kind: 'area', label: 'نشانی', rows: 3 },
  emergency_name: { kind: 'text', label: 'نام', maxlength: 100 },
  emergency_phone: { kind: 'text', label: 'تلفن', dir: 'ltr', inputmode: 'tel', maxlength: 20 },
  emergency_relation: { kind: 'text', label: 'نسبت', maxlength: 60 },
  insurance_name: { kind: 'text', label: 'نوع بیمه', maxlength: 100 },
  insurance_number: { kind: 'text', label: 'شماره بیمه', dir: 'ltr', maxlength: 60 },
  blood_type: { kind: 'select', label: 'گروه خونی', options: [['', 'مشخص نشده'], ...['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((b) => [b, b])] },
  blood_pressure: { kind: 'text', label: 'فشار خون', dir: 'ltr', placeholder: '120/80', maxlength: 20 },
  height_cm: { kind: 'text', label: 'قد (سانتی‌متر)', dir: 'ltr', inputmode: 'decimal' },
  weight_kg: { kind: 'text', label: 'وزن (کیلوگرم)', dir: 'ltr', inputmode: 'decimal' },
  allergies: { kind: 'text', label: 'حساسیت‌ها', hint: 'با ویرگول جدا کنید، مثل پنی‌سیلین، صدف' },
  conditions: { kind: 'text', label: 'بیماری‌های زمینه‌ای', hint: 'با ویرگول جدا کنید' },
  medical_notes: { kind: 'area', label: 'یادداشت‌های بالینی', rows: 5 },
};

const spec = computed(() => {
  const b = props.box;
  if (b.type !== undefined) {
    const name = `c_${b.id}`;
    const base = { name, label: b.label, full: b.full };
    switch (b.type) {
      case 'long_text': return { ...base, kind: 'area', rows: 3 };
      case 'number': return { ...base, kind: 'text', dir: 'ltr', inputmode: 'decimal' };
      case 'date': return { ...base, kind: 'date' };
      case 'choice': {
        const held = String(props.values[name] ?? '');
        const offered = (b.choices ?? []).filter((c: any) => !c.hidden || String(c.id) === held);
        return { ...base, kind: 'select', options: [['', 'انتخاب نشده'], ...offered.map((c: any) => [String(c.id), c.label])] };
      }
      case 'yes_no': return { ...base, kind: 'yesno' };
      default: return { ...base, kind: 'text', maxlength: 200 };
    }
  }
  return { name: b.id, full: b.full, ...(BUILTIN[b.id] ?? { kind: 'none' }) };
});
const id = computed(() => `f-${spec.value.name}`);
const err = computed(() => (props.disabled ? '' : props.errors?.[spec.value.name] ?? ''));
const list = computed(() => (spec.value.list ? props.suggestions?.[spec.value.list] ?? [] : []));
const model = computed({
  get: () => props.values[spec.value.name] ?? '',
  set: (v) => { props.values[spec.value.name] = v; },
});
const optout = computed({
  get: () => props.values.sms_optout === '1' || props.values.sms_optout === true,
  set: (v) => { props.values.sms_optout = v ? '1' : ''; },
});
</script>

<template>
  <div v-if="spec.kind === 'text'" v-float class="field" :class="{ 'span-2': spec.full }">
    <label :for="id">{{ spec.label }}<span v-if="required" class="muted"> (الزامی)</span></label>
    <input :id="id" v-model="model" class="input" :type="spec.type || 'text'" :dir="spec.dir" :inputmode="spec.inputmode"
      :placeholder="spec.code ? nextCode ?? '' : spec.placeholder" :maxlength="spec.maxlength" :list="list.length ? `${id}-list` : undefined"
      autocomplete="off" :aria-invalid="err ? 'true' : undefined" :aria-describedby="err ? `${id}-err` : undefined"
      :disabled="disabled" :tabindex="disabled ? -1 : undefined">
    <datalist v-if="list.length && !disabled" :id="`${id}-list`"><option v-for="o in list" :key="o" :value="o" /></datalist>
    <span v-if="spec.code && !err" class="hint">خالی بماند تا کد <span class="mono">{{ nextCode }}</span> خودکار داده شود؛ یا کد دلخواه مثل <span class="mono">P-000123</span> یا فقط عدد آن</span>
    <span v-else-if="spec.hint && !err" class="hint">{{ spec.hint }}</span>
    <p v-if="err" :id="`${id}-err`" class="field-error" role="alert">{{ err }}</p>
  </div>
  <div v-else-if="spec.kind === 'date'" class="field" :class="{ 'span-2': spec.full }">
    <label :for="id">{{ spec.label }}<span v-if="required" class="muted"> (الزامی)</span></label>
    <JalaliInput :id="id" v-model="model" placeholder="۱۴۰۳/۰۵/۱۲" :disabled="disabled" />
    <span v-if="!err" class="hint">تاریخ شمسی، مثل ۱۴۰۳/۰۵/۱۲</span>
    <p v-if="err" :id="`${id}-err`" class="field-error" role="alert">{{ err }}</p>
  </div>
  <div v-else-if="spec.kind === 'select'" v-float class="field">
    <label :for="id">{{ spec.label }}<span v-if="required" class="muted"> (الزامی)</span></label>
    <select :id="id" v-model="model" class="select" :aria-invalid="err ? 'true' : undefined" :disabled="disabled" :tabindex="disabled ? -1 : undefined">
      <option v-for="[val, text] in spec.options" :key="val" :value="val">{{ text }}</option>
    </select>
    <p v-if="err" :id="`${id}-err`" class="field-error" role="alert">{{ err }}</p>
  </div>
  <div v-else-if="spec.kind === 'area'" v-float class="field" :class="{ 'span-2': spec.full }">
    <label :for="id">{{ spec.label }}<span v-if="required" class="muted"> (الزامی)</span></label>
    <textarea :id="id" v-model="model" class="textarea" :rows="spec.rows" :aria-invalid="err ? 'true' : undefined" :disabled="disabled" :tabindex="disabled ? -1 : undefined"></textarea>
    <p v-if="err" :id="`${id}-err`" class="field-error" role="alert">{{ err }}</p>
  </div>
  <fieldset v-else-if="spec.kind === 'yesno'" :id="id" class="field">
    <legend>{{ spec.label }}<span v-if="required" class="muted"> (الزامی)</span></legend>
    <label v-for="[val, text] in [['1', 'بله'], ['0', 'خیر'], ['', 'نامشخص']]" :key="val" class="check">
      <input v-model="model" type="radio" :name="disabled ? undefined : spec.name" :value="val" :disabled="disabled"><span>{{ text }}</span>
    </label>
    <p v-if="err" class="field-error" role="alert">{{ err }}</p>
  </fieldset>
  <div v-else-if="spec.kind === 'optout'" class="field">
    <label class="check"><input v-model="optout" type="checkbox" :disabled="disabled"><span>دریافت نکردن پیامک</span></label>
    <span class="hint">اگر تیک بخورد، یادآوری و پیام گروهی برای این بیمار نمی‌رود.</span>
  </div>
</template>
