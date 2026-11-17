<script setup lang="ts">
// The app shell (legacy partials shell-top, sidebar, tabbar): sidebar, phone tab bar under 900 px, top search,
// theme button. Links the user may not open are not shown.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from './Icon.vue';
import ThemeToggle from './ThemeToggle.vue';
import { session, can, has, refreshMe } from '../lib/session';
import { faCount } from '../lib/fmt';
import { api } from '../api/client';

const route = useRoute();
const router = useRouter();
const me = computed(() => session.me!);
const active = computed(() => (route.meta.active as string) ?? '');
const q = ref('');
const more = ref<HTMLDetailsElement | null>(null);
const initial = computed(() => Array.from(me.value?.displayName ?? '?')[0]);
const moreKeys = ['storage', 'finance', 'sms', 'print', 'data', 'users', 'audit', 'account', 'contact'];

watch(() => route.fullPath, () => { if (more.value) more.value.open = false; });

// Critique S4: the server lists stopped services for the owner only; re-read /me every 5 minutes so a stop shows up
// without a reload.
const problems = computed(() => me.value?.systemProblems ?? []);
let timer: number | undefined;
onMounted(() => { timer = window.setInterval(refreshMe, 5 * 60 * 1000); });
onUnmounted(() => window.clearInterval(timer));

function search() {
  router.push({ path: '/patients', query: q.value ? { q: q.value } : {} });
  q.value = '';
}

async function logout() {
  try { await api.post('/auth/logout'); } catch { /* signed out anyway */ }
  session.me = null;
  router.push('/login');
}
const cur = (key: string) => (active.value === key ? 'page' : undefined);
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark"><Icon name="mark" /></span>
        <span>{{ session.siteName }}<small>پرتال کارکنان</small></span>
      </RouterLink>
      <nav class="nav" aria-label="منوی اصلی">
        <div class="nav-label">فضای کار</div>
        <RouterLink to="/" :aria-current="cur('dashboard')"><Icon name="home" /><span>داشبورد</span></RouterLink>
        <RouterLink v-if="can('patients')" to="/patients" :aria-current="cur('patients')"><Icon name="users" /><span>بیماران</span><span class="count">{{ faCount(me.patientCount) }}</span></RouterLink>
        <RouterLink v-if="can('patients') && can('visits')" to="/visits" :aria-current="cur('visits')"><Icon name="calendar" /><span>ویزیت‌ها</span></RouterLink>
        <RouterLink v-if="can('storage')" to="/storage" :aria-current="cur('storage')"><Icon name="box" /><span>انبار</span></RouterLink>
        <RouterLink v-if="can('finance')" to="/finance" :aria-current="cur('finance')"><Icon name="wallet" /><span>امور مالی</span></RouterLink>
        <RouterLink v-if="can('sms') && can('patients')" to="/sms" :aria-current="cur('sms')"><Icon name="mail" /><span>پیامک</span></RouterLink>
        <RouterLink v-if="can('pdf')" to="/print" :aria-current="cur('print')"><Icon name="print" /><span>فرم‌های چاپی</span></RouterLink>
        <div v-if="can('patients') || can('data') || can('users') || has('audit_log')" class="nav-label">داده</div>
        <RouterLink v-if="can('patients')" to="/search" :aria-current="cur('search')"><Icon name="search" /><span>جستجوی پیشرفته</span></RouterLink>
        <RouterLink v-if="can('data')" to="/data" :aria-current="cur('data')"><Icon name="swap" /><span>ورود و خروج داده</span></RouterLink>
        <RouterLink v-if="can('users')" to="/admin/users" :aria-current="cur('users')"><Icon name="users" /><span>مدیریت کاربران</span></RouterLink>
        <RouterLink v-if="has('audit_log')" to="/admin/audit" :aria-current="cur('audit')"><Icon name="shield" /><span>گزارش فعالیت</span></RouterLink>
        <div class="nav-label">پشتیبانی</div>
        <RouterLink to="/contact" :aria-current="cur('contact')"><Icon name="help" /><span>تماس با ما</span></RouterLink>
      </nav>
      <div class="sidebar-foot">
        <RouterLink class="user-chip" to="/account" title="حساب کاربری" :aria-current="cur('account')">
          <span class="avatar">{{ initial }}</span>
          <div><b>{{ me.displayName }}</b><span>{{ me.roleLabel }}</span></div>
        </RouterLink>
        <form @submit.prevent="logout"><button class="btn btn-sm btn-block" type="submit">خروج</button></form>
      </div>
    </aside>

    <nav class="tabbar" aria-label="منوی اصلی موبایل">
      <RouterLink to="/" :aria-current="cur('dashboard')"><Icon name="home" /><span>خانه</span></RouterLink>
      <RouterLink v-if="can('patients')" to="/patients" :aria-current="cur('patients')"><Icon name="users" /><span>بیماران</span></RouterLink>
      <RouterLink v-if="can('patients', 2)" class="tabbar-new" to="/patients/new" aria-label="ثبت بیمار جدید"><span class="tabbar-plus"><Icon name="plus" /></span><span>جدید</span></RouterLink>
      <RouterLink v-if="can('patients') && can('visits')" to="/visits" :aria-current="cur('visits')"><Icon name="calendar" /><span>ویزیت‌ها</span></RouterLink>
      <RouterLink v-if="can('patients')" to="/search" :aria-current="cur('search')"><Icon name="search" /><span>جستجو</span></RouterLink>
      <details ref="more" class="tabbar-more">
        <summary :aria-current="moreKeys.includes(active) ? 'page' : undefined"><Icon name="more" /><span>بیشتر</span></summary>
        <div class="tabbar-menu">
          <div class="tabbar-user">
            <span class="avatar avatar-sm">{{ initial }}</span>
            <div><b>{{ me.displayName }}</b><span>{{ me.roleLabel }}</span></div>
          </div>
          <RouterLink v-if="can('storage')" to="/storage"><Icon name="box" />انبار</RouterLink>
          <RouterLink v-if="can('finance')" to="/finance"><Icon name="wallet" />امور مالی</RouterLink>
          <RouterLink v-if="can('sms') && can('patients')" to="/sms"><Icon name="mail" />پیامک</RouterLink>
          <RouterLink v-if="can('pdf')" to="/print"><Icon name="print" />فرم‌های چاپی</RouterLink>
          <RouterLink v-if="can('data')" to="/data"><Icon name="swap" />ورود و خروج داده</RouterLink>
          <RouterLink v-if="can('users')" to="/admin/users"><Icon name="users" />مدیریت کاربران</RouterLink>
          <RouterLink v-if="has('audit_log')" to="/admin/audit"><Icon name="shield" />گزارش فعالیت</RouterLink>
          <RouterLink to="/contact"><Icon name="help" />تماس با ما</RouterLink>
          <RouterLink to="/account"><Icon name="shield" />حساب کاربری</RouterLink>
          <form @submit.prevent="logout"><button class="btn btn-block" type="submit">خروج از حساب</button></form>
        </div>
      </details>
    </nav>

    <div class="main">
      <header class="topbar">
        <RouterLink class="topbar-brand" to="/" aria-label="داشبورد"><span class="brand-mark"><Icon name="mark" /></span></RouterLink>
        <form v-if="can('patients')" class="input-group search" @submit.prevent="search">
          <Icon name="search" />
          <input v-model="q" class="input" type="search" name="q" placeholder="جستجوی بیمار، کد یا شماره تلفن" aria-label="جستجو">
        </form>
        <span v-else class="grow"></span>
        <div class="topbar-actions">
          <RouterLink v-if="me?.diagOn" class="chip chip-terra" to="/admin/diagnostics">عیب‌یابی روشن</RouterLink>
          <ThemeToggle />
          <RouterLink v-if="can('patients', 2)" class="btn btn-primary topbar-new" to="/patients/new"><Icon name="plus" />بیمار جدید</RouterLink>
        </div>
      </header>
      <main class="content">
        <div v-if="problems.includes('worker')" class="callout callout-crit" role="alert"><Icon name="alert" /><span><b>سرویس پس‌زمینه‌ی سامانه در حال اجرا نیست.</b> پیامک‌ها، ثبت بیماران از فایل و نسخه‌ی پشتیبان شبانه تا راه‌اندازی دوباره‌ی آن متوقف می‌مانند. به پشتیبان سامانه خبر دهید.</span></div>
        <div v-if="problems.includes('backup')" class="callout callout-crit" role="alert"><Icon name="alert" /><span><b>نسخه‌ی پشتیبان شبانه ساخته نشده است.</b> بیش از یک روز است که از داده‌ها نسخه‌ی پشتیبان تازه‌ای گرفته نشده. به پشتیبان سامانه خبر دهید.</span></div>
        <slot />
      </main>
    </div>
  </div>
</template>
