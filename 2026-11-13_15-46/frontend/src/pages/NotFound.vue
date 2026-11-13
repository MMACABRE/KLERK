<script setup lang="ts">
import { setTitle } from '../lib/session';

setTitle('خطا');
</script>

<template>
  <main class="main">
    <div class="card">
      <h1>۴۰۴</h1>
      <p class="muted">صفحه‌ی مورد نظر پیدا نشد.</p>
      <p><RouterLink class="btn" to="/">بازگشت به صفحه‌ی اصلی</RouterLink></p>
    </div>
  </main>
</template>
