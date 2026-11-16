<script setup lang="ts">
// Permission editor (legacy views/admin/permissions.ejs, D25): a level per area and flags; a preset fills the form.
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import Icon from '../../components/Icon.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

const route = useRoute();
const id = String(route.params.id);
const areas = ref<Record<string, number>>({});
const flags = ref<string[]>([]);
const preset = ref('');
const presetNotice = ref('');
const act = useAction();
const { data, error } = useLoad(async () => {
  const d = await api.get(`/users/${id}/permissions`);
  setTitle(`دسترسی‌های ${d.user.displayName}`);
  areas.value = { ...d.perms.areas };
  flags.value = [...d.perms.flags];
  preset.value = d.preset ?? 'staff';
  return d;
});
const current = computed(() => {
  if (!data.value) return null;
  for (const [k, p] of Object.entries<any>(data.value.presets)) {
    const same = Object.keys(areas.value).every((a) => p.perms[a] === areas.value[a]) && [...p.perms.flags].sort().join() === [...flags.value].sort().join();
    if (same) return k;
  }
  return null;
});
function applyPreset() {
  const p = data.value.presets[preset.value];
  areas.value = Object.fromEntries(data.value.areas.map((a: any) => [a.key, p.perms[a.key]]));
  flags.value = [...p.perms.flags];
  presetNotice.value = `قالب «${p.label}» در فرم گذاشته شد؛ برای ثبت، «ذخیره» را بزنید.`;
}
async function save() {
  presetNotice.value = '';
  const out = await act.run(() => api.put(`/users/${id}/permissions`, { areas: areas.value, flags: flags.value }));
  if (out) {
    areas.value = { ...out.perms.areas };
    flags.value = [...out.perms.flags];
    act.notice.value = out.notice;
  }
}
const flagsOf = (area: string) => data.value.flags.filter((f: any) => f.area === area);
</script>

<template>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="page-head">
      <div>
        <div class="breadcrumb"><RouterLink to="/admin/users">مدیریت کاربران</RouterLink> / <span class="mono">{{ data.user.username }}</span></div>
        <h1>دسترسی‌های {{ data.user.displayName }}</h1>
        <p>برای هر بخش یکی از «بدون دسترسی»، «مشاهده» یا «ویرایش» را بگذارید. کارهای حساس جدا تیک می‌خورند و فقط وقتی کار می‌کنند که آن بخش باز باشد.</p>
      </div>
    </div>
    <div v-if="act.notice.value || presetNotice" class="callout callout-info" role="status"><Icon name="check" /><span>{{ presetNotice || act.notice.value }}</span></div>
    <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
    <form class="stack-lg" @submit.prevent="save">
      <section class="card">
        <div class="card-body preset-bar">
          <div class="field"><label for="p-preset">قالب آماده</label>
            <select id="p-preset" v-model="preset" class="select"><option v-for="(p, k) in data.presets" :key="k" :value="k">{{ p.label }}</option></select></div>
          <button class="btn" type="button" @click="applyPreset">اعمال قالب در فرم</button>
          <span class="hint">وضعیت فعلی: <b>{{ current ? data.presets[current].label : 'سفارشی' }}</b></span>
        </div>
      </section>
      <div class="perm-grid">
        <fieldset v-for="a in data.areas" :key="a.key" class="card perm-card">
          <legend class="sr-only">{{ a.label }}</legend>
          <div class="card-head"><h2 aria-hidden="true">{{ a.label }}</h2></div>
          <div class="card-body stack">
            <div class="levels" role="radiogroup" :aria-label="`سطح دسترسی ${a.label}`">
              <label v-for="l in a.max + 1" :key="l" class="level"><input v-model="areas[a.key]" type="radio" :name="`a_${a.key}`" :value="l - 1"><span>{{ data.levels[l - 1] }}</span></label>
            </div>
            <label v-for="f in flagsOf(a.key)" :key="f.key" class="check"><input v-model="flags" type="checkbox" :value="f.key"><span>{{ f.label }} <span class="hint">(نیاز به {{ data.levels[f.needs] }})</span></span></label>
          </div>
        </fieldset>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="check" />ذخیره‌ی دسترسی‌ها</button>
        <RouterLink class="btn btn-ghost" to="/admin/users">بازگشت</RouterLink>
      </div>
    </form>
  </template>
</template>
