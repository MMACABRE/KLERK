<script setup lang="ts">
// Storage list (legacy views/storage/index.ejs).
import { useRoute } from 'vue-router';
import Icon from '../../components/Icon.vue';
import { api } from '../../api/client';
import { can, has, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useLoad } from '../../lib/usePage';

setTitle('انبار');
const route = useRoute();
const LOW: Record<string, [string, string]> = { crit: ['chip-crit', 'موجودی بحرانی'], warn: ['chip-warn', 'موجودی کم'] };
const EXP: Record<string, [string, string]> = { expired: ['chip-crit', 'منقضی شده'], crit: ['chip-crit', 'انقضای نزدیک'], warn: ['chip-warn', 'انقضا در ۳۰ روز'] };
const { data, error } = useLoad(() => api.get('/storage/items', { f: route.query.f === 'alert' ? 'alert' : '' }));
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Storage</span></div>
      <h1>انبار</h1>
      <p>موجودی کالاها به تعداد، با تاریخ انقضای هر بسته. مصرف همیشه از بسته‌ای برداشته می‌شود که زودتر منقضی می‌شود.</p>
    </div>
    <div class="page-actions">
      <a v-if="can('pdf')" class="btn" href="/print/stock/inventory"><Icon name="print" />چاپ موجودی انبار</a>
      <RouterLink v-if="has('finance_settings')" class="btn btn-primary" to="/storage/items/new"><Icon name="plus" />کالای جدید</RouterLink>
    </div>
  </div>
  <div v-if="route.query.ok === 'removed'" class="callout callout-info" role="status"><Icon name="check" /><span>کالا و همه‌ی گردش آن حذف شد.</span></div>
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <div class="segmented mb-4" role="group" aria-label="نمایش">
      <template v-if="data.filter === 'all'"><span class="is-on">همه‌ی کالاها</span><RouterLink to="/storage?f=alert">دارای هشدار ({{ fa(data.alertCount) }})</RouterLink></template>
      <template v-else><RouterLink to="/storage">همه‌ی کالاها</RouterLink><span class="is-on">دارای هشدار ({{ fa(data.alertCount) }})</span></template>
    </div>
    <section class="card">
      <div v-if="!data.data.length" class="card-body empty-state">
        <Icon name="box" />
        <p>{{ data.filter === 'alert' ? 'هیچ کالایی هشدار ندارد.' : 'هنوز کالایی تعریف نشده است.' }}</p>
        <RouterLink v-if="data.filter === 'all' && has('finance_settings')" class="btn btn-primary" to="/storage/items/new">تعریف اولین کالا</RouterLink>
      </div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">کالا</th><th scope="col">موجود قابل مصرف</th><th scope="col">نزدیک‌ترین انقضا</th><th scope="col">وضعیت</th><th v-if="can('finance')" scope="col">قیمت فروش</th></tr></thead>
          <tbody>
            <tr v-for="it in data.data" :key="it.id">
              <td data-label="کالا"><b><RouterLink :to="`/storage/items/${it.id}`">{{ it.name }}</RouterLink></b></td>
              <td data-label="موجود قابل مصرف"><span class="num-lg">{{ it.usable.display }}</span> <span class="muted">عدد</span></td>
              <td data-label="نزدیک‌ترین انقضا">{{ it.nextExpiry?.short ?? '—' }}</td>
              <td data-label="وضعیت"><div class="chips">
                <span v-if="it.low" class="chip" :class="LOW[it.low][0]">{{ LOW[it.low][1] }}</span>
                <span v-if="it.expiry" class="chip" :class="EXP[it.expiry][0]">{{ EXP[it.expiry][1] }}</span>
                <span v-if="!it.low && !it.expiry" class="chip chip-ok">عادی</span>
              </div></td>
              <td v-if="can('finance')" data-label="قیمت فروش"><span class="money">{{ it.salePrice?.display }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <p class="text-xs-muted mt-3">حد پیش‌فرض هشدار: {{ data.settings.lowWarn.display }} عدد، حد بحرانی: {{ data.settings.lowCrit.display }} عدد. هشدار انقضا از ۳۰ روز مانده (زرد) و ۱۰ روز مانده (قرمز).</p>
  </template>
</template>
