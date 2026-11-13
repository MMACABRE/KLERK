<script setup lang="ts">
// User management (legacy views/admin/users.ejs). Owner rules are enforced by the server.
import { ref } from 'vue';
import Icon from '../../components/Icon.vue';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import PasswordInput from '../../components/PasswordInput.vue';
import { api } from '../../api/client';
import { has, session, setTitle } from '../../lib/session';
import { fa } from '../../lib/fmt';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('مدیریت کاربران');
const form = ref({ username: '', displayName: '', preset: 'staff', password: '' });
const newPw = ref<Record<number, string>>({});
const act = useAction();
const { data, error, load } = useLoad(() => api.get('/users'));

async function doing(fn: () => Promise<any>) {
  const out = await act.run(fn);
  if (out) { act.notice.value = out.notice ?? ''; await load(); }
  return out;
}
async function create() {
  if (await doing(() => api.post('/users', form.value))) form.value = { username: '', displayName: '', preset: 'staff', password: '' };
}
async function setPw(id: number) {
  if (await doing(() => api.post(`/users/${id}/password`, { password: newPw.value[id] ?? '' }))) newPw.value[id] = '';
}
const toggle = (u: any) => doing(() => api.post(`/users/${u.id}/${u.active ? 'deactivate' : 'activate'}`));
const remove = (id: number) => doing(() => api.del(`/users/${id}`));
</script>

<template>
  <div class="page-head">
    <div>
      <div class="breadcrumb"><span lang="en" dir="ltr">User Management</span></div>
      <h1>مدیریت کاربران</h1>
      <p>کاربران را بسازید، دسترسی هر نفر را تنظیم کنید، رمزشان را عوض کنید یا حسابشان را ببندید. ثبت‌نام عمومی وجود ندارد.</p>
    </div>
    <RouterLink v-if="has('manage_users')" class="btn btn-danger" to="/admin/wipe"><Icon name="trash" />حذف داده‌ها</RouterLink>
  </div>
  <div v-if="act.notice.value" class="callout callout-info" role="status"><Icon name="check" /><span>{{ act.notice.value }}</span></div>
  <div v-if="act.error.value || error" class="info-box" role="alert">{{ act.error.value || error }}</div>
  <section v-if="has('manage_users')" class="card" aria-labelledby="new-h">
    <div class="card-head"><h2 id="new-h">کاربر جدید</h2></div>
    <form class="card-body stack-lg" autocomplete="off" @submit.prevent="create">
      <div class="form-grid">
        <div class="field"><label for="u-name">نام کاربری</label><input id="u-name" v-model="form.username" class="input" type="text" dir="ltr" maxlength="32" required autocomplete="off"><span class="hint">۳ تا ۳۲ نویسه‌ی لاتین، عدد، نقطه، خط تیره یا زیرخط</span></div>
        <div class="field"><label for="u-display">نام نمایشی</label><input id="u-display" v-model="form.displayName" class="input" type="text" maxlength="80" required></div>
        <div class="field"><label for="u-preset">قالب دسترسی</label>
          <select id="u-preset" v-model="form.preset" class="select"><option value="staff">کارمند</option><option value="admin">مدیر</option></select>
          <span class="hint">بعد از ساخت، از «دسترسی‌ها» می‌توانید جزئیات را تغییر دهید.</span></div>
        <div class="field"><label for="u-pass">رمز عبور</label><PasswordInput id="u-pass" v-model="form.password" autocomplete="new-password" required /><span class="hint">دست‌کم ۱۰ نویسه</span></div>
      </div>
      <div><button class="btn btn-primary" type="submit" :disabled="act.busy.value"><Icon name="plus" />ساخت کاربر</button></div>
    </form>
  </section>
  <section v-if="data" class="card mt-6" aria-labelledby="list-h">
    <div class="card-head"><div><h2 id="list-h">کاربران</h2><p>{{ fa(data.data.length) }} کاربر</p></div></div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th scope="col">کاربر</th><th scope="col">دسترسی</th><th scope="col">وضعیت</th><th scope="col">تاریخ ساخت</th><template v-if="has('manage_users')"><th scope="col">رمز جدید</th><th scope="col"><span class="sr-only">اقدام</span></th></template></tr></thead>
        <tbody>
          <tr v-for="u in data.data" :key="u.id">
            <td data-label="کاربر"><b>{{ u.displayName }}</b><br><span class="mono text-xs-subtle">{{ u.username }}</span></td>
            <td data-label="دسترسی"><span class="chip" :class="u.owner ? 'chip-info' : 'chip-plain'">{{ u.label }}</span></td>
            <td data-label="وضعیت"><span class="chip" :class="u.active ? 'chip-ok' : 'chip-mute'">{{ u.active ? 'فعال' : 'غیرفعال' }}</span></td>
            <td data-label="تاریخ ساخت">{{ u.createdAtJalali.split(' ')[0] }}</td>
            <template v-if="has('manage_users')">
              <td data-label="رمز جدید">
                <form v-if="!u.owner || session.me?.owner" class="flex-row" autocomplete="off" @submit.prevent="setPw(u.id)">
                  <input v-model="newPw[u.id]" class="input" type="password" dir="ltr" minlength="10" maxlength="256" placeholder="رمز جدید" :aria-label="`رمز جدید برای ${u.username}`" required autocomplete="new-password">
                  <button class="btn btn-sm" type="submit">تنظیم</button>
                </form>
                <span v-else class="muted">فقط خود مالک</span>
              </td>
              <td data-label="اقدام">
                <div v-if="u.id !== session.me?.id && !u.owner" class="user-actions">
                  <RouterLink class="btn btn-sm" :to="`/admin/users/${u.id}/permissions`"><Icon name="key" />دسترسی‌ها</RouterLink>
                  <button class="btn btn-sm" :class="{ 'btn-primary': !u.active }" type="button" @click="toggle(u)">{{ u.active ? 'غیرفعال‌سازی' : 'فعال‌سازی' }}</button>
                  <ConfirmDelete :question="`حساب «${u.displayName}» برای همیشه حذف شود؟ سوابق فعالیت او می‌ماند.`" @confirm="remove(u.id)" />
                </div>
                <span v-else class="muted">{{ u.id === session.me?.id ? 'حساب شما' : 'مالک سامانه' }}</span>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
