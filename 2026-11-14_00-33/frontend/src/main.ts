import { createApp } from 'vue';
import { installErrorReporter } from './lib/reportErrors';
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import App from './App.vue';
import { setUnauthorizedHandler } from './api/client';
import { loadSession, session, can, has } from './lib/session';
import { applyTheme } from './lib/theme';
import { installFloats, scheduleFloatSync } from './lib/directives';

document.documentElement.classList.add('js');

// meta.need: [area, level] the page needs; meta.flag: a flag it needs. Cosmetic only: the server decides.
const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('./pages/LoginPage.vue'), meta: { bare: true, public: true } },
  { path: '/contact', component: () => import('./pages/ContactPage.vue'), meta: { public: true, active: 'contact' } },
  { path: '/', component: () => import('./pages/DashboardPage.vue'), meta: { active: 'dashboard' } },
  { path: '/account', component: () => import('./pages/AccountPage.vue'), meta: { active: 'account' } },
  { path: '/patients', component: () => import('./pages/patients/PatientList.vue'), meta: { active: 'patients', need: ['patients', 1] } },
  { path: '/patients/new', component: () => import('./pages/patients/PatientForm.vue'), meta: { active: 'patients', need: ['patients', 2] } },
  { path: '/patients/layout', component: () => import('./pages/patients/FormLayoutEditor.vue'), meta: { active: 'patients', flag: 'layout' } },
  { path: '/patients/:code', component: () => import('./pages/patients/PatientProfile.vue'), meta: { active: 'patients', need: ['patients', 1] } },
  { path: '/patients/:code/edit', component: () => import('./pages/patients/PatientForm.vue'), meta: { active: 'patients', need: ['patients', 2] } },
  { path: '/patients/:code/delete', component: () => import('./pages/patients/PatientDelete.vue'), meta: { active: 'patients', flag: 'patient_delete' } },
  { path: '/patients/:code/documents', component: () => import('./pages/patients/DocumentsPage.vue'), meta: { active: 'patients', need: ['documents', 1] } },
  { path: '/patients/:code/history', component: () => import('./pages/patients/PatientHistory.vue'), meta: { active: 'patients', need: ['finance', 1] } },
  { path: '/patients/:code/sms', component: () => import('./pages/sms/PatientSms.vue'), meta: { active: 'patients', need: ['sms', 2] } },
  { path: '/visits', component: () => import('./pages/visits/VisitList.vue'), meta: { active: 'visits', need: ['visits', 1] } },
  { path: '/visits/new', component: () => import('./pages/visits/VisitForm.vue'), meta: { active: 'visits', need: ['visits', 2] } },
  { path: '/visits/:id', component: () => import('./pages/visits/VisitPage.vue'), meta: { active: 'visits', need: ['visits', 1] } },
  { path: '/visits/:id/edit', component: () => import('./pages/visits/VisitForm.vue'), meta: { active: 'visits', need: ['visits', 2] } },
  { path: '/finance', component: () => import('./pages/finance/FinanceOverview.vue'), meta: { active: 'finance', need: ['finance', 1] } },
  { path: '/finance/payments', component: () => import('./pages/finance/FinancePayments.vue'), meta: { active: 'finance', need: ['finance', 1] } },
  { path: '/finance/pay', component: () => import('./pages/finance/FinancePay.vue'), meta: { active: 'finance', need: ['finance', 2] } },
  { path: '/finance/settings', component: () => import('./pages/finance/FinanceSettings.vue'), meta: { active: 'finance', flag: 'finance_settings' } },
  { path: '/storage', component: () => import('./pages/storage/StorageList.vue'), meta: { active: 'storage', need: ['storage', 1] } },
  { path: '/storage/items/new', component: () => import('./pages/storage/StorageNew.vue'), meta: { active: 'storage', flag: 'finance_settings' } },
  { path: '/storage/items/:id', component: () => import('./pages/storage/StorageItem.vue'), meta: { active: 'storage', need: ['storage', 1] } },
  { path: '/search', component: () => import('./pages/SearchPage.vue'), meta: { active: 'search', need: ['patients', 1] } },
  { path: '/data', component: () => import('./pages/DataPage.vue'), meta: { active: 'data', need: ['data', 1] } },
  { path: '/sms', component: () => import('./pages/sms/SmsLog.vue'), meta: { active: 'sms', need: ['sms', 1] } },
  { path: '/sms/settings', component: () => import('./pages/sms/SmsSettings.vue'), meta: { active: 'sms', need: ['sms', 1] } },
  { path: '/sms/bulk', component: () => import('./pages/sms/SmsBulk.vue'), meta: { active: 'sms', flag: 'sms_bulk' } },
  { path: '/admin/users', component: () => import('./pages/admin/UsersPage.vue'), meta: { active: 'users', need: ['users', 1] } },
  { path: '/admin/users/:id/permissions', component: () => import('./pages/admin/PermissionsPage.vue'), meta: { active: 'users', flag: 'manage_users' } },
  { path: '/admin/audit', component: () => import('./pages/admin/AuditPage.vue'), meta: { active: 'audit', flag: 'audit_log' } },
  { path: '/admin/wipe', component: () => import('./pages/admin/WipePage.vue'), meta: { active: 'users', flag: 'manage_users' } },
  { path: '/admin/diagnostics', component: () => import('./pages/admin/DiagnosticsPage.vue'), meta: { active: 'users', owner: true } },
  { path: '/print', component: () => import('./pages/PrintIndex.vue'), meta: { active: 'print', need: ['pdf', 1] } },
  { path: '/:rest(.*)*', component: () => import('./pages/NotFound.vue'), meta: { public: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, _from, saved) {
    if (saved) return saved;
    if (to.hash) return { el: to.hash, top: 80 };
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  if (!session.loaded) {
    const me = await loadSession();
    applyTheme(me?.theme ?? session.theme);
  }
  if (to.meta.public) {
    if (to.path === '/login' && session.me) return '/';
    return true;
  }
  if (!session.me) return { path: '/login', query: { next: to.fullPath } };
  const need = to.meta.need as [string, number] | undefined;
  const flag = to.meta.flag as string | undefined;
  if ((need && !can(need[0], need[1])) || (flag && !has(flag)) || (to.meta.owner && !session.me.owner)) {
    return { path: '/', query: { denied: '1' } };
  }
  return true;
});

setUnauthorizedHandler(() => {
  if (!session.me) return;
  session.me = null;
  router.push({ path: '/login', query: { next: router.currentRoute.value.fullPath, expired: '1' } });
});

const app = createApp(App).use(router);
installErrorReporter(app, router);
app.mixin({ updated: scheduleFloatSync });
app.mount('#app');
installFloats(document.getElementById('app')!);
