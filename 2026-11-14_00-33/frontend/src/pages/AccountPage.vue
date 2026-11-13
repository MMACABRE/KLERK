<script setup lang="ts">
// Own account (legacy views/account.ejs): change password; other devices are signed out.
import { ref } from 'vue';
import Icon from '../components/Icon.vue';
import PasswordInput from '../components/PasswordInput.vue';
import { api } from '../api/client';
import { session, setTitle } from '../lib/session';
import { useAction } from '../lib/usePage';

setTitle('حساب کاربری');
const form = ref({ current: '', password: '', confirm: '' });
const done = ref(false);
const { busy, error, run } = useAction();
async function save() {
  done.value = false;
  if (await run(() => api.post('/me/password', form.value))) {
    done.value = true;
    form.value = { current: '', password: '', confirm: '' };
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">Account</span></div>
      <h1>حساب کاربری</h1>
      <p>{{ session.me?.displayName }} · <span class="mono">{{ session.me?.username }}</span> · {{ session.me?.roleLabel }}</p>
    </div>
  </div>
  <section class="card" aria-labelledby="pw-h">
    <div class="card-head"><h2 id="pw-h">تغییر رمز عبور</h2></div>
    <form class="card-body stack-lg" autocomplete="off" @submit.prevent="save">
      <div v-if="done" class="callout callout-info" role="status"><Icon name="check" /><span>رمز عبور عوض شد. در دستگاه‌های دیگر باید دوباره وارد شوید.</span></div>
      <div v-if="error" class="info-box" role="alert">{{ error }}</div>
      <div class="form-grid">
        <div class="field span-2"><label for="cur">رمز فعلی</label><PasswordInput id="cur" v-model="form.current" autocomplete="current-password" required /></div>
        <div class="field"><label for="new">رمز جدید</label><PasswordInput id="new" v-model="form.password" autocomplete="new-password" required /><span class="hint">دست‌کم ۱۰ نویسه</span></div>
        <div class="field"><label for="rep">تکرار رمز جدید</label><PasswordInput id="rep" v-model="form.confirm" autocomplete="new-password" required /></div>
      </div>
      <div><button class="btn btn-primary" type="submit" :disabled="busy">ذخیره‌ی رمز جدید</button></div>
    </form>
  </section>
</template>
