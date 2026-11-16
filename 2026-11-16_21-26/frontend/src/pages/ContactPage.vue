<script setup lang="ts">
// "Contact us" (legacy views/contact.ejs): the same content for visitors and signed-in users.
import { onBeforeUnmount, onMounted, ref } from 'vue';
import Icon from '../components/Icon.vue';
import ThemeToggle from '../components/ThemeToggle.vue';
import { api } from '../api/client';
import { session, setTitle } from '../lib/session';
import { useLoad } from '../lib/usePage';

setTitle('تماس با ما');
const { data } = useLoad(() => api.get('/public/contact'));
const copied = ref<Record<string, string>>({});
const steps = [
  'صفحه‌ای که در آن بودید، مثلاً «جستجوی پیشرفته».',
  'کاری که انجام می‌دادید و پیامی که روی صفحه دیدید.',
  'زمان تقریبی رخ‌دادن مشکل.',
  'عکس صفحه (اسکرین‌شات)، اگر ممکن است.',
];
async function copy(key: string, text: string) {
  try { await navigator.clipboard.writeText(text); copied.value[key] = 'کپی شد'; } catch { copied.value[key] = 'کپی نشد'; }
  setTimeout(() => { copied.value[key] = ''; }, 1800);
}
const cls = session.me ? 'contact-app' : 'contact-public';
onMounted(() => document.body.classList.add(cls));
onBeforeUnmount(() => document.body.classList.remove(cls));
</script>

<template>
  <template v-if="!session.me">
    <header class="contact-bar">
      <RouterLink class="brand contact-brand" to="/login">
        <span class="brand-mark"><Icon name="mark" /></span>
        <span>{{ session.siteName }}</span>
      </RouterLink>
      <div class="contact-bar-actions">
        <RouterLink class="btn btn-sm" to="/login"><Icon name="arrow" />بازگشت به ورود</RouterLink>
        <ThemeToggle />
      </div>
    </header>
  </template>
  <component :is="session.me ? 'div' : 'main'" :class="session.me ? '' : 'content contact-main'">
    <section class="contact-hero" aria-labelledby="contact-h">
      <div class="contact-hero-copy">
        <div class="contact-person"><div><b>{{ data?.contact.name }}</b><span>سازنده و پشتیبان سامانه</span></div></div>
        <h1 id="contact-h">کمک لازم دارید؟</h1>
        <p>اگر هنگام کار با سامانه خطایی دیدید یا چیزی درست کار نکرد، مستقیم با من در تماس باشید. هر مشکلی را بنویسید تا هرچه زودتر بررسی کنم.</p>
      </div>
    </section>
    <div v-if="data" class="contact-grid">
      <section class="card contact-sheet" aria-label="راه‌های تماس">
        <div class="contact-row">
          <span class="contact-icon" aria-hidden="true"><Icon name="phone" /></span>
          <div class="contact-info"><span class="contact-label">تلفن همراه</span><bdi id="contact-phone" class="contact-value">{{ data.contact.phoneShown }}</bdi></div>
          <div class="contact-actions">
            <a class="btn btn-primary btn-sm" :href="`tel:${data.contact.phone}`"><Icon name="phone" />تماس</a>
            <button class="btn btn-sm contact-copy" type="button" :data-done="copied.phone ? '' : undefined" @click="copy('phone', data.contact.phone)"><Icon name="copy" /><span>{{ copied.phone || 'کپی' }}</span></button>
          </div>
        </div>
        <div class="contact-row">
          <span class="contact-icon" aria-hidden="true"><Icon name="mail" /></span>
          <div class="contact-info"><span class="contact-label">ایمیل</span><bdi id="contact-email" class="contact-value">{{ data.contact.email }}</bdi></div>
          <div class="contact-actions">
            <a class="btn btn-primary btn-sm" :href="`mailto:${data.contact.email}`"><Icon name="mail" />ارسال ایمیل</a>
            <button class="btn btn-sm contact-copy" type="button" :data-done="copied.email ? '' : undefined" @click="copy('email', data.contact.email)"><Icon name="copy" /><span>{{ copied.email || 'کپی' }}</span></button>
          </div>
        </div>
      </section>
      <section class="card contact-guide" aria-labelledby="guide-h">
        <h2 id="guide-h">هنگام گزارش مشکل بنویسید</h2>
        <ul class="contact-steps"><li v-for="s in steps" :key="s"><Icon name="check" /><span>{{ s }}</span></li></ul>
        <p class="contact-privacy"><Icon name="shield" /><span>نام و مشخصات بیماران را در پیام ننویسید. کد بیمار، مثل <bdi class="mono">P-000123</bdi>، کافی است.</span></p>
      </section>
    </div>
  </component>
</template>
