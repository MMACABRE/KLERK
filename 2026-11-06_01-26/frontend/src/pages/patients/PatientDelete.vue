<script setup lang="ts">
// Delete a patient (legacy views/patients/delete.ejs). The folder moves to data/trash on the server.
import { useRoute, useRouter } from 'vue-router';
import Icon from '../../components/Icon.vue';
import { api } from '../../api/client';
import { refreshMe, setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('حذف بیمار');
const route = useRoute();
const router = useRouter();
const code = String(route.params.code);
const { data, error } = useLoad(() => api.get(`/patients/${code}/delete-check`));
const act = useAction();

async function remove() {
  const ok = await act.run(() => api.del(`/patients/${code}`));
  if (ok) { refreshMe(); router.push('/patients'); }
}
</script>

<template>
  <section class="card">
    <p v-if="error" class="card-body info-box" role="alert">{{ error }}</p>
    <form v-else-if="data" class="card-body form-section" @submit.prevent="remove">
      <h1>حذف پرونده‌ی بیمار</h1>
      <p>پرونده‌ی <b>{{ data.patient.firstName }} {{ data.patient.lastName }}</b> (<span class="mono">{{ data.patient.code }}</span>) از سامانه حذف می‌شود.</p>
      <p class="muted">اطلاعات ثبت‌شده و داروها پاک می‌شوند. پوشه‌ی فایل‌های بیمار پاک نمی‌شود و به پوشه‌ی <span class="mono">data/trash</span> روی سرور منتقل می‌شود. اگر فقط می‌خواهید پرونده از فهرست کنار برود، به‌جای حذف آن را بایگانی کنید.</p>
      <div v-if="data.blocked" class="info-box" role="alert">{{ data.message }}</div>
      <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
      <div class="form-actions">
        <button class="btn btn-danger" type="submit" :disabled="act.busy.value || data.blocked"><Icon name="trash" />حذف پرونده</button>
        <RouterLink class="btn" :to="`/patients/${code}`">انصراف</RouterLink>
      </div>
    </form>
  </section>
</template>
