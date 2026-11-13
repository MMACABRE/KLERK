<script setup lang="ts">
// Finance overview (legacy views/finance/index.ejs, D29): income figures and four charts with hidden tables.
import Icon from '../../components/Icon.vue';
import BarChart from '../../components/BarChart.vue';
import HBarChart from '../../components/HBarChart.vue';
import FinanceNav from '../../components/FinanceNav.vue';
import { api } from '../../api/client';
import { can, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useLoad } from '../../lib/usePage';

setTitle('امور مالی');
const { data, error } = useLoad(() => api.get('/finance/overview'));

function shortMoney(cur: string) {
  return (rial: number) => {
    const n = cur === 'R' ? rial : rial / 10;
    if (n >= 1e9) return `${+(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${+(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${+(n / 1e3).toFixed(0)}K`;
    return String(Math.round(n));
  };
}
const moneyText = (rows: any[]) => (v: number) => rows.find((r) => r.value === v)?.money?.display ?? String(v);
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Finance</span></div>
      <h1>امور مالی</h1>
      <p>درآمد همیشه در روزی حساب می‌شود که پول دریافت شده است؛ پیش‌پرداخت در روز پرداخت می‌آید، نه روز ویزیت.</p>
    </div>
    <div v-if="can('pdf')" class="head-actions">
      <a class="btn btn-sm" href="/print/finance/day"><Icon name="print" />گزارش مالی امروز</a>
      <a v-if="can('patients') && can('visits')" class="btn btn-sm" href="/print/visits/day"><Icon name="print" />فهرست ویزیت‌های امروز</a>
    </div>
  </div>
  <FinanceNav here="overview" />
  <p v-if="error" class="info-box" role="alert">{{ error }}</p>
  <template v-if="data">
    <section class="grid grid-3 fin-figures" aria-label="درآمد">
      <article class="card stat"><div class="stat-label">درآمد امروز <span class="stat-icon"><Icon name="wallet" /></span></div><div class="stat-value fin-value"><span class="money">{{ data.figures.today.total.display }}</span></div><div class="stat-delta">{{ fa(data.figures.today.count) }} پرداخت</div></article>
      <article class="card stat"><div class="stat-label">درآمد این هفته</div><div class="stat-value fin-value"><span class="money">{{ data.figures.week.total.display }}</span></div><div class="stat-delta">از شنبه · {{ fa(data.figures.week.count) }} پرداخت</div></article>
      <article class="card stat"><div class="stat-label">درآمد {{ data.monthName }}</div><div class="stat-value fin-value"><span class="money">{{ data.figures.month.total.display }}</span></div><div class="stat-delta">{{ fa(data.figures.month.count) }} پرداخت</div></article>
    </section>
    <section class="grid grid-2 fin-figures mt-3" aria-label="مانده و بستانکار">
      <article class="card stat"><div class="stat-label">مانده‌ی همه‌ی بیماران</div><div class="stat-value fin-value fin-due"><span class="money">{{ data.figures.remaining.display }}</span></div><div class="stat-delta">بدهی ثبت‌شده که هنوز پرداخت نشده؛ درآمد نیست</div></article>
      <article class="card stat"><div class="stat-label">بستانکاری بیماران</div><div class="stat-value fin-value"><span class="money">{{ data.figures.credit.display }}</span></div><div class="stat-delta">پولی که باید برگردد یا به ویزیت دیگری منتقل شود</div></article>
    </section>
    <div class="chart-grid mt-6">
      <section class="card chart-card" aria-labelledby="ch1">
        <div class="card-head"><div><h2 id="ch1">درآمد روزانه</h2><p>۳۰ روز اخیر؛ امروز پررنگ است</p></div></div>
        <div class="card-body"><BarChart :data="data.charts.daily" :fmt="shortMoney(data.currency)" :tick="5" label="درآمد روزانه‌ی ۳۰ روز اخیر" /></div>
        <table class="sr-only"><caption>درآمد روزانه</caption><tbody><tr v-for="d in data.charts.daily" :key="d.day.iso"><th scope="row">{{ d.day.long }}</th><td>{{ d.money.display }}</td></tr></tbody></table>
      </section>
      <section class="card chart-card" aria-labelledby="ch2">
        <div class="card-head"><div><h2 id="ch2">درآمد ماهانه</h2><p>۶ ماه اخیر</p></div></div>
        <div class="card-body"><BarChart :data="data.charts.monthly" :fmt="shortMoney(data.currency)" label="درآمد ۶ ماه اخیر" /></div>
        <table class="sr-only"><caption>درآمد ماهانه</caption><tbody><tr v-for="m in data.charts.monthly" :key="m.label"><th scope="row">{{ m.label }}</th><td>{{ m.money.display }}</td></tr></tbody></table>
      </section>
      <section class="card chart-card" aria-labelledby="ch3">
        <div class="card-head"><div><h2 id="ch3">فروش {{ data.monthName }} بر اساس نوع</h2><p>جمع ردیف‌های صورتحساب ویزیت‌های این ماه، پس از تخفیف ردیف<template v-if="data.billDisc.rial">؛ تخفیف کل صورتحساب‌ها: <span class="money">{{ data.billDisc.display }}</span></template></p></div></div>
        <div class="card-body"><HBarChart :data="data.charts.source" :fmt="moneyText(data.charts.source)" label="فروش این ماه بر اساس نوع" /></div>
        <div v-if="data.charts.top.length" class="card-body chart-sub"><h3>پرفروش‌ترین موارد</h3><HBarChart :data="data.charts.top" :fmt="moneyText(data.charts.top)" label="پرفروش‌ترین موارد این ماه" /></div>
        <table class="sr-only"><caption>فروش بر اساس نوع و مورد</caption><tbody><tr v-for="r in [...data.charts.source, ...data.charts.top]" :key="r.label"><th scope="row">{{ r.label }}</th><td>{{ r.money.display }}</td></tr></tbody></table>
      </section>
      <section v-if="data.charts.usage" class="card chart-card" aria-labelledby="ch4">
        <div class="card-head"><div><h2 id="ch4">مصرف کالا</h2><p>تعداد کالای مصرف‌شده در ویزیت‌ها، ۳۰ روز اخیر</p></div></div>
        <div class="card-body"><BarChart :data="data.charts.usage" :fmt="(v: number) => fa(Math.round(v))" :tick="5" label="تعداد کالای مصرف‌شده در ۳۰ روز اخیر" /></div>
        <table class="sr-only"><caption>مصرف کالا</caption><tbody><tr v-for="d in data.charts.usage" :key="d.day.iso"><th scope="row">{{ d.day.long }}</th><td>{{ fa(d.value) }} عدد</td></tr></tbody></table>
      </section>
    </div>
  </template>
</template>
