<script setup lang="ts">
// Sign-in (legacy views/login.ejs). Same messages as legacy: wrong (401), locked (429), busy (503).
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Icon from '../components/Icon.vue';
import PasswordInput from '../components/PasswordInput.vue';
import ThemeToggle from '../components/ThemeToggle.vue';
import { api, ApiError } from '../api/client';
import { session, setTitle } from '../lib/session';
import { applyTheme } from '../lib/theme';
import { enhanceSun } from '../lib/sun';

setTitle('ورود');
const route = useRoute();
const router = useRouter();
const username = ref('');
const password = ref('');
const error = ref(route.query.expired === '1' ? 'نشست شما به پایان رسیده است. لطفاً دوباره وارد شوید.' : '');
const busy = ref(false);
const sun = ref<HTMLElement | null>(null);
let stopSun = () => {};
onMounted(() => { if (sun.value) stopSun = enhanceSun(sun.value); });
onBeforeUnmount(() => stopSun());

function safeNext(n: unknown): string {
  return typeof n === 'string' && /^\/(?![/\\])/.test(n) ? n : '/';
}

async function submit() {
  busy.value = true;
  error.value = '';
  try {
    const me = await api.post('/auth/login', { username: username.value, password: password.value });
    session.me = me;
    session.siteName = me.siteName;
    applyTheme(me.theme);
    router.replace(safeNext(route.query.next));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'خطایی رخ داد.';
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="auth-theme"><ThemeToggle /></div>
  <div class="auth">
    <div class="auth-side">
      <span ref="sun" class="auth-sun" aria-hidden="true"></span>
      <div>
        <span class="brand-mark auth-brand mb-3rem"><Icon name="mark" /></span>
        <p class="auth-side-title mb-1rem">دسترسی امن کارکنان</p>
        <p class="muted mb-2rem auth-intro">فقط کارکنان مجاز با حساب کاربری شخصی به پرونده‌ی بیماران دسترسی دارند.</p>
      </div>
      <div class="sidebar-footer">{{ session.siteName }}</div>
    </div>
    <div class="auth-main">
      <form class="auth-card" @submit.prevent="submit">
        <div>
          <h1 class="mb-sp2">ورود</h1>
          <p class="muted signin-subtitle">برای دسترسی به پرونده‌ی بیماران وارد شوید.</p>
        </div>
        <div v-if="error" class="info-box" role="alert">{{ error }}</div>
        <div class="stack-lg">
          <div class="field">
            <label for="username">نام کاربری</label>
            <input id="username" v-model="username" class="input" type="text" autocomplete="username" dir="ltr" required autofocus>
          </div>
          <div class="field">
            <label for="password">رمز عبور</label>
            <PasswordInput id="password" v-model="password" autocomplete="current-password" required />
          </div>
          <button type="submit" class="btn btn-primary btn-block" :disabled="busy"><Icon name="check" />ورود</button>
          <p class="text-center link-sm muted">رمز عبور را فراموش کرده‌اید؟ به مدیر سیستم اطلاع دهید.</p>
          <p class="text-center link-sm"><RouterLink class="contact-link" to="/contact"><Icon name="help" />مشکلی پیش آمده؟ تماس با پشتیبانی</RouterLink></p>
        </div>
      </form>
    </div>
  </div>
</template>
