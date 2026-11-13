<script setup lang="ts">
// «عیب‌یابی» (ADR-0013): the protected owner switches the diagnostics feed on and off. The token is shown once.
import { ref } from 'vue';
import Icon from '../../components/Icon.vue';
import { api } from '../../api/client';
import { refreshMe, setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('عیب‌یابی');
const token = ref('');
const copied = ref(false);
const act = useAction();
const { data, load } = useLoad(() => api.get('/diagnostics/token'));

async function after(out: any) {
  if (out === undefined) return;
  await load();
  await refreshMe();
}
async function switchOn() {
  copied.value = false;
  const out = await act.run(() => api.post('/diagnostics/token'));
  if (out) token.value = out.token;
  await after(out);
}
async function renew() { await after(await act.run(() => api.put('/diagnostics/token'))); }
async function switchOff() {
  token.value = '';
  await after(await act.run(() => api.del('/diagnostics/token')));
}
async function copy() {
  try { await navigator.clipboard.writeText(token.value); copied.value = true; } catch { copied.value = false; }
}
</script>

<template>
  <div class="breadcrumb"><RouterLink to="/admin/users">مدیریت کاربران</RouterLink> / عیب‌یابی</div>
  <div class="page-head"><div><h1>عیب‌یابی</h1><p>با روشن کردن عیب‌یابی، پشتیبان می‌تواند گزارش خطاها و وضعیت سرور را بخواند. اطلاعات بیماران فرستاده نمی‌شود.</p></div></div>
  <div v-if="act.error.value" class="callout callout-crit" role="alert"><Icon name="alert" /><span>{{ act.error.value }}</span></div>
  <section v-if="data" class="card" aria-labelledby="diag-h">
    <div class="card-head"><h2 id="diag-h">عیب‌یابی</h2>
      <span class="chip" :class="data.on ? 'chip-terra' : 'chip-mute'">{{ data.on ? 'روشن' : 'خاموش' }}</span>
    </div>
    <div class="card-body stack-lg">
      <dl v-if="data.on" class="kv">
        <dt>پایان اعتبار</dt><dd class="mono">{{ data.expiresText }}</dd>
        <dt>آخرین خواندن</dt><dd><template v-if="data.lastRead"><span class="mono">{{ data.lastRead.atText }}</span> · <span class="mono" dir="ltr">{{ data.lastRead.ip }}</span></template><template v-else>—</template></dd>
      </dl>
      <div v-if="token" class="field">
        <label for="diag-token">کلید (فقط یک بار نمایش داده می‌شود)</label>
        <input id="diag-token" class="input mono" dir="ltr" type="text" readonly :value="token">
        <div class="form-actions"><button class="btn" type="button" @click="copy"><Icon name="copy" />رونوشت</button><span v-if="copied" class="hint" role="status">✓</span></div>
      </div>
      <div class="form-actions">
        <button v-if="!data.on" class="btn btn-primary" type="button" :disabled="act.busy.value" @click="switchOn"><Icon name="check" />روشن کردن</button>
        <template v-else>
          <button class="btn" type="button" :disabled="act.busy.value" @click="renew">تمدید ۳۰ روز</button>
          <button class="btn btn-danger" type="button" :disabled="act.busy.value" @click="switchOff">خاموش کردن</button>
        </template>
      </div>
    </div>
  </section>
</template>
