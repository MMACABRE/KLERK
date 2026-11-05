<script setup lang="ts">
// Patient form layout editor (D52, D53): order cards and boxes, move a box to another card, hide or show it, mark it
// required, rename custom cards; create, delete and edit custom boxes. One draft, one save; undo and reset.
// Cards and boxes move by pointer drag or by keyboard on their grips (useDragList); a box also moves to another card
// through its card list, which is easier on a phone.
import { computed, ref } from 'vue';
import Icon from '../../components/Icon.vue';
import GripButton from '../../components/GripButton.vue';
import { useDragList } from '../../lib/dragList';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('چیدمان فرم بیمار');
type Box = { id: string; req?: boolean };
type Card = { id: string; label?: string; boxes: Box[] };
const draft = ref<Card[]>([]);
const act = useAction();
const boxAct = useAction();
const newBox = ref({ type: 'short_text', label: '', choices: '' });
const choiceText = ref<Record<number, string>>({});
const { data, load } = useLoad(async () => {
  const d = await api.get('/patients/layout');
  draft.value = JSON.parse(JSON.stringify(d.layout.cards));
  return d;
});
const NAMES = ['first_name', 'last_name'];
const builtinCard = (id: string) => data.value?.catalogue.cards.find((c: any) => c.id === id);
const cardTitle = (c: Card) => c.label ?? builtinCard(c.id)?.label ?? c.id;
const customById = computed<Record<string, any>>(() => Object.fromEntries((data.value?.customBoxes ?? []).map((b: any) => [`c:${b.id}`, b])));
function boxLabel(id: string) {
  if (id.startsWith('c:')) return customById.value[id]?.label ?? id;
  return data.value?.catalogue.boxes.find((b: any) => b.id === id)?.label ?? id;
}
const placed = computed(() => new Set(draft.value.flatMap((c) => c.boxes.map((b) => b.id))));
const hidden = computed(() => [
  ...(data.value?.catalogue.boxes ?? []).map((b: any) => b.id),
  ...(data.value?.customBoxes ?? []).map((b: any) => `c:${b.id}`),
].filter((id: string) => !placed.value.has(id)));
const dirty = computed(() => data.value && JSON.stringify(draft.value) !== JSON.stringify(data.value.layout.cards));
const typeLabel = (t: string) => data.value?.catalogue.types.find((x: any) => x.id === t)?.label ?? t;

const live = ref('');
const say = (t: string) => { live.value = t; };
const dragCard = useDragList<Card>({
  ns: 'card', groups: () => [{ key: 'cards', items: draft.value }], idOf: (c) => c.id,
  label: (id) => { const c = draft.value.find((x) => x.id === id); return c ? cardTitle(c) : id; }, say,
});
const dragBox = useDragList<Box>({
  ns: 'box', groups: () => draft.value.map((c) => ({ key: c.id, items: c.boxes })), idOf: (b) => b.id,
  label: boxLabel, say,
});
function moveTo(ci: number, bi: number, target: string) {
  const [box] = draft.value[ci].boxes.splice(bi, 1);
  draft.value.find((c) => c.id === target)!.boxes.push(box);
}
const hideBox = (ci: number, bi: number) => draft.value[ci].boxes.splice(bi, 1);
const showBox = (id: string) => draft.value[0]?.boxes.push({ id });
function toggleReq(b: Box) {
  if (NAMES.includes(b.id)) return;
  if (b.req) delete b.req; else b.req = true;
}
function addCard() {
  const used = draft.value.map((c) => /^card:(\d+)$/.exec(c.id)?.[1]).filter(Boolean).map(Number);
  const n = Math.max(0, ...used) + 1;
  draft.value.push({ id: `card:${n}`, label: `کارت ${n}`, boxes: [] });
}
function removeCard(ci: number) {
  const [card] = draft.value.splice(ci, 1);
  draft.value[0]?.boxes.push(...card.boxes);
}

async function save() {
  if (await act.run(() => api.put('/patients/layout', { layout: { v: 1, cards: draft.value } }), 'چیدمان ذخیره شد.')) load();
}
async function undo() {
  const out = await act.run(() => api.post('/patients/layout/undo'));
  if (out) { act.notice.value = out.undone ? 'چیدمان قبلی برگشت.' : 'چیدمان قبلی وجود ندارد.'; load(); }
}
async function reset() {
  if (await act.run(() => api.post('/patients/layout/reset'), 'چیدمان به پیش‌فرض برگشت.')) load();
}
async function createBox() {
  if (await boxAct.run(() => api.post('/patients/layout/boxes', newBox.value), 'کادر ساخته شد؛ آن را از «کادرهای پنهان» به فرم بیاورید.')) {
    newBox.value = { type: 'short_text', label: '', choices: '' };
    const keep = draft.value;
    await load();
    draft.value = keep;
  }
}
async function boxOp(id: number, body: Record<string, string>) {
  if (await boxAct.run(() => api.post(`/patients/layout/boxes/${id}/choices`, body), 'ذخیره شد.')) {
    choiceText.value[id] = '';
    const keep = draft.value;
    await load();
    draft.value = keep;
  }
}
async function deleteBox(id: number) {
  if (await boxAct.run(() => api.del(`/patients/layout/boxes/${id}`), 'کادر حذف شد.')) {
    draft.value.forEach((c) => { c.boxes = c.boxes.filter((b) => b.id !== `c:${id}`); });
    const keep = draft.value;
    await load();
    draft.value = keep;
  }
}
</script>

<template>
  <div class="breadcrumb"><RouterLink to="/patients" lang="en">Patients</RouterLink> / چیدمان فرم</div>
  <div class="page-head"><div><h1>چیدمان فرم بیمار</h1><p>کارت‌ها و کادرهای فرم ثبت بیمار را مرتب کنید، کادری را پنهان یا الزامی کنید و کادر تازه بسازید. نام و نام خانوادگی همیشه در فرم و الزامی‌اند.</p></div></div>
  <div v-if="act.notice.value" class="info-box" role="status">{{ act.notice.value }}</div>
  <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
  <template v-if="data">
    <p id="pl-help" class="sr-only">برای جابه‌جایی با صفحه‌کلید: فاصله یا Enter را بزنید، با کلیدهای جهت جابه‌جا کنید، Enter برای گذاشتن و Esc برای لغو.</p>
    <div class="sr-only" aria-live="polite">{{ live }}</div>
    <div class="pl-cards mb-4" data-card-group="cards">
    <section v-for="(card, ci) in draft" :key="card.id" class="card" :class="{ 'pl-ph': dragCard.lifted.value === card.id, 'is-kb': dragCard.carried.value === card.id }" :data-card-id="card.id">
      <div class="card-head">
        <div class="inline-form">
          <GripButton :label="`جابه‌جایی کارت «${cardTitle(card)}»`" @pointerdown="dragCard.down($event, card.id)" @keydown="dragCard.key($event, card.id)" @blur="dragCard.blur()" />
          <input v-if="card.id.startsWith('card:')" v-model="card.label" class="input" type="text" maxlength="40" aria-label="نام کارت">
          <h2 v-else>{{ cardTitle(card) }}</h2>
        </div>
        <div class="user-actions">
          <button v-if="card.id.startsWith('card:')" class="btn btn-sm btn-ghost" type="button" @click="removeCard(ci)">حذف کارت</button>
        </div>
      </div>
      <ul class="edit-list" :data-box-group="card.id">
        <li v-if="!card.boxes.length" class="muted">کادری در این کارت نیست.</li>
        <li v-for="(b, bi) in card.boxes" :key="b.id" :class="{ 'pl-ph': dragBox.lifted.value === b.id, 'is-kb': dragBox.carried.value === b.id }" :data-box-id="b.id">
          <GripButton :label="`جابه‌جایی کادر «${boxLabel(b.id)}»`" @pointerdown="dragBox.down($event, b.id)" @keydown="dragBox.key($event, b.id)" @blur="dragBox.blur()" />
          <b>{{ boxLabel(b.id) }}</b>
          <span v-if="b.id.startsWith('c:')" class="chip chip-plain chip-mute">{{ typeLabel(customById[b.id]?.type) }}</span>
          <label class="check"><input type="checkbox" :checked="Boolean(b.req)" :disabled="NAMES.includes(b.id)" @change="toggleReq(b)"><span>الزامی</span></label>
          <span class="user-actions">
            <select class="select select-sm" :aria-label="`کارت ${boxLabel(b.id)}`" :value="card.id" @change="moveTo(ci, bi, ($event.target as HTMLSelectElement).value)">
              <option v-for="c in draft" :key="c.id" :value="c.id">{{ cardTitle(c) }}</option>
            </select>
            <button v-if="!NAMES.includes(b.id)" class="btn btn-sm btn-ghost" type="button" @click="hideBox(ci, bi)">پنهان</button>
          </span>
        </li>
      </ul>
    </section>
    </div>
    <div class="form-actions mb-4"><button class="btn" type="button" @click="addCard"><Icon name="plus" />کارت تازه</button></div>

    <section class="card mb-4">
      <div class="card-head"><div><h2>کادرهای پنهان</h2><p>این کادرها در فرم نیستند؛ مقدارهای ذخیره‌شده‌شان می‌ماند.</p></div></div>
      <ul class="pl-chips card-body">
        <li v-if="!hidden.length" class="muted">همه‌ی کادرها در فرم هستند.</li>
        <li v-for="id in hidden" :key="id"><button class="pl-chip" type="button" @click="showBox(id)"><Icon name="plus" /><span>{{ boxLabel(id) }}</span></button></li>
      </ul>
    </section>

    <div class="pl-draft">
      <span class="pl-draft-state">{{ dirty ? 'تغییرات ذخیره نشده' : 'بدون تغییر' }}</span>
      <span class="pl-draft-btns">
        <button class="btn btn-ghost pl-wide" type="button" :disabled="act.busy.value" @click="reset">بازگشت به پیش‌فرض</button>
        <button class="btn btn-ghost pl-wide" type="button" :disabled="!data.hasPrevious || act.busy.value" @click="undo">چیدمان قبلی</button>
        <button class="btn btn-primary" type="button" :disabled="!dirty || act.busy.value" @click="save"><Icon name="check" />ذخیره</button>
      </span>
    </div>
    <!-- Under 900 px the draft bar keeps only Save; these two move here (legacy .pl-foot). -->
    <div class="pl-foot">
      <button class="btn" type="button" :disabled="act.busy.value" @click="reset">بازگشت به پیش‌فرض</button>
      <button class="btn" type="button" :disabled="!data.hasPrevious || act.busy.value" @click="undo">چیدمان قبلی</button>
    </div>

    <section class="card mt-6">
      <div class="card-head"><div><h2>کادرهای سفارشی</h2><p>کادری که مقدار دارد حذف نمی‌شود؛ آن را از فرم پنهان کنید.</p></div></div>
      <div v-if="boxAct.notice.value" class="card-body"><p class="info-box" role="status">{{ boxAct.notice.value }}</p></div>
      <div v-if="boxAct.error.value" class="card-body"><p class="field-error" role="alert">{{ boxAct.error.value }}</p></div>
      <ul class="edit-list">
        <li v-for="b in data.customBoxes" :key="b.id">
          <b>{{ b.label }}</b> <span class="chip chip-plain chip-mute">{{ typeLabel(b.type) }}</span>
          <template v-if="b.type === 'choice'">
            <span v-for="c in b.choices" :key="c.id" class="chip chip-plain" :class="c.hidden ? 'chip-mute' : 'chip-info'">
              {{ c.label }}
              <button class="btn btn-sm btn-ghost" type="button" @click="boxOp(b.id, { op: c.hidden ? 'show' : 'hide', choice: String(c.id) })">{{ c.hidden ? 'نمایش' : 'پنهان' }}</button>
              <button v-if="!(data.usedChoices[String(b.id)] ?? []).includes(String(c.id))" class="btn btn-sm btn-ghost" type="button" @click="boxOp(b.id, { op: 'remove', choice: String(c.id) })">حذف</button>
            </span>
            <form class="inline-form" @submit.prevent="boxOp(b.id, { op: 'add', text: choiceText[b.id] ?? '' })">
              <input v-model="choiceText[b.id]" class="input" type="text" placeholder="گزینه‌ی تازه (با ویرگول جدا کنید)" aria-label="گزینه‌ی تازه">
              <button class="btn btn-sm" type="submit">افزودن گزینه</button>
            </form>
          </template>
          <ConfirmDelete v-if="!data.usedBoxes.includes(b.id)" :question="`کادر «${b.label}» حذف شود؟`" @confirm="deleteBox(b.id)" />
        </li>
      </ul>
      <form class="card-body form-grid form-grid-3" @submit.prevent="createBox">
        <h3 class="span-all">کادر تازه</h3>
        <div class="field"><label for="nb-type">نوع</label><select id="nb-type" v-model="newBox.type" class="select"><option v-for="t in data.catalogue.types" :key="t.id" :value="t.id">{{ t.label }}</option></select></div>
        <div class="field"><label for="nb-label">نام کادر</label><input id="nb-label" v-model="newBox.label" class="input" type="text" maxlength="60" required></div>
        <div v-if="newBox.type === 'choice'" class="field"><label for="nb-choices">گزینه‌ها</label><input id="nb-choices" v-model="newBox.choices" class="input" type="text" placeholder="با ویرگول جدا کنید"></div>
        <div class="form-actions span-all"><button class="btn btn-primary" type="submit" :disabled="boxAct.busy.value"><Icon name="plus" />ساخت کادر</button></div>
      </form>
    </section>
  </template>
</template>
