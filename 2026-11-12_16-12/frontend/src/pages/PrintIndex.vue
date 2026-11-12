<script setup lang="ts">
// «فرم‌های چاپی» (legacy views/print/index.ejs): one card per document; each opens the server-rendered print page.
import { ref } from 'vue';
import Icon from '../components/Icon.vue';
import JalaliInput from '../components/JalaliInput.vue';
import { can, setTitle } from '../lib/session';
import * as jc from '../lib/jalali-math.js';

setTitle('فرم‌های چاپی');
const now = jc.today();
const today = jc.format(now);
const monthFrom = jc.format({ jy: now.jy, jm: now.jm, jd: 1 });
const d = ref({ fin: today, vday: today, vrep: today, sday: today, from: monthFrom, to: today, by: 'item' });
function open(path: string, q: Record<string, string>) {
  window.location.href = `${path}?${new URLSearchParams(q).toString()}`;
}
</script>

<template>
  <div class="page-head"><div><div class="breadcrumb"><span lang="en" dir="ltr">Printable documents</span></div><h1>فرم‌های چاپی</h1>
    <p>هر فرم در یک صفحه‌ی آماده‌ی چاپ باز می‌شود؛ با چاپ مرورگر می‌توانید آن را به PDF ذخیره کنید. صورتحساب ویزیت از صفحه‌ی هر ویزیت و پرونده‌ی کامل از صفحه‌ی هر بیمار چاپ می‌شود.</p></div></div>
  <div class="print-cards">
    <section v-if="can('finance') && can('patients')" class="card"><div class="card-head"><div><h2>گزارش مالی روزانه</h2><p>همه‌ی پرداخت‌ها و بازپرداخت‌های یک روز، با جمع هر روش و هر حساب.</p></div></div>
      <div class="card-body"><form @submit.prevent="open('/print/finance/day', { d: d.fin })">
        <div class="field"><label for="p1">روز</label><JalaliInput id="p1" v-model="d.fin" /></div>
        <button class="btn btn-primary" type="submit"><Icon name="print" />نمایش فرم</button></form></div></section>
    <section v-if="can('finance') && can('patients') && can('visits')" class="card"><div class="card-head"><div><h2>فهرست ویزیت‌های روز</h2><p>ویزیت‌های یک روز با شماره‌ی ویزیت، مبلغ، پرداخت، روش و حساب، و جمع روز.</p></div></div>
      <div class="card-body"><form @submit.prevent="open('/print/visits/day', { d: d.vday })">
        <div class="field"><label for="p2">روز</label><JalaliInput id="p2" v-model="d.vday" /></div>
        <button class="btn btn-primary" type="submit"><Icon name="print" />نمایش فرم</button></form></div></section>
    <section v-if="can('finance') && can('patients') && can('visits')" class="card"><div class="card-head"><div><h2>گزارش کامل روزانه</h2><p>هر ویزیت روز با علت مراجعه، خدمات و کالاها با تعداد و مبلغ، مبلغ قابل پرداخت و پرداخت‌ها با روش و حساب؛ در پایان جمع هر حساب.</p></div></div>
      <div class="card-body"><form @submit.prevent="open('/print/visits/report', { d: d.vrep })">
        <div class="field"><label for="p4">روز</label><JalaliInput id="p4" v-model="d.vrep" /></div>
        <button class="btn btn-primary" type="submit"><Icon name="print" />نمایش فرم</button></form></div></section>
    <section v-if="can('storage') && can('patients') && can('visits')" class="card"><div class="card-head"><div><h2>گزارش روزانه‌ی مصرف کالا</h2><p>فقط کالاهای انبار که در ویزیت‌های یک روز مصرف شده‌اند: هر بیمار با کالاهایش، و در پایان جمع هر کالا.</p></div></div>
      <div class="card-body"><form @submit.prevent="open('/print/stock/day', { d: d.sday })">
        <div class="field"><label for="p5">روز</label><JalaliInput id="p5" v-model="d.sday" /></div>
        <button class="btn btn-primary" type="submit"><Icon name="print" />نمایش فرم</button></form></div></section>
    <section v-if="can('storage')" class="card"><div class="card-head"><div><h2>موجودی انبار</h2><p>همه‌ی کالاهای انبار با موجود قابل مصرف، هر بار ورود با مانده و تاریخ انقضا، و هشدارها.</p></div></div>
      <div class="card-body"><a class="btn btn-primary" href="/print/stock/inventory"><Icon name="print" />نمایش فرم</a></div></section>
    <section v-if="can('storage')" class="card"><div class="card-head"><div><h2>کالاهای مصرف‌شده</h2><p>مصرف کالا در یک بازه، به تفکیک کالا یا بیمار، با مبلغ.</p></div></div>
      <div class="card-body"><form @submit.prevent="open('/print/stock/usage', { from: d.from, to: d.to, by: d.by })">
        <div class="field"><label for="p3a">از</label><JalaliInput id="p3a" v-model="d.from" /></div>
        <div class="field"><label for="p3b">تا</label><JalaliInput id="p3b" v-model="d.to" /></div>
        <div class="field"><label for="p3c">تفکیک</label><select id="p3c" v-model="d.by" class="select"><option value="item">بر اساس کالا</option><option v-if="can('patients')" value="patient">بر اساس بیمار</option></select></div>
        <button class="btn btn-primary" type="submit"><Icon name="print" />نمایش فرم</button></form></div></section>
  </div>
</template>
