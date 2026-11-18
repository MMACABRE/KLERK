<script setup lang="ts">
// Patient form layout editor (D52, D53): order cards, place and size boxes, move a box to another card, hide or show
// it, mark it required, rename custom cards; create, delete and edit custom boxes. One draft, one save; undo and reset.
// Cards move by pointer drag or keyboard on their grips (useDragList). Inside a card the boxes sit on a 4-column
// home-screen grid like the dashboard (owner decision 2026-11-17; FormCardGrid, lib/gridEditor.ts); a box moves to
// another card through its card list and lands in that card's first free cell.
import { computed, ref } from 'vue';
import Icon from '../../components/Icon.vue';
import GripButton from '../../components/GripButton.vue';
import FormCardGrid from '../../components/FormCardGrid.vue';
import { firstFree, ROWS } from '../../lib/grid-math';
import type { Item } from '../../lib/grid-math';
import { useDragList } from '../../lib/dragList';
import ConfirmDelete from '../../components/ConfirmDelete.vue';
import { api } from '../../api/client';
import { setTitle } from '../../lib/session';
import { useAction, useLoad } from '../../lib/usePage';

setTitle('چیدمان فرم بیمار');
type Box = { id: string; req?: boolean; x: number; y: number; w: number; h: number };
type Card = { id: string; label?: string; boxes: Box[] };
const draft = ref<Card[]>([]);
const act = useAction();
const boxAct = useAction();
const newBox = ref({ type: 'short_text', label: '', choices: '' });
const choiceText = ref<Record<number, string>>({});
// A card saved before the grid (no cells) gets them in its old order: a full-width box (long text) takes the whole
// row, the others half of it, each at the first free cell, so the form looks as it did.
const FORM_COLS = 4;
const isFull = (d: any, id: string) => (id.startsWith('c:') ? d?.customBoxes.find((b: any) => `c:${b.id}` === id) : d?.catalogue.boxes.find((b: any) => b.id === id))?.full === true;
const sizeFor = (id: string, d: any = data.value) => ({ w: isFull(d, id) ? FORM_COLS : 2, h: 1 });
function placeIn(boxes: Box[], b: { id: string; req?: boolean }, size: { w: number; h: number } = sizeFor(b.id)): Box {
  const spot = firstFree({ id: b.id, ...size }, boxes, FORM_COLS, ROWS * 2)!;
  return { ...b, ...spot };
}
function withCells(card: any, d: any): Card {
  if (card.boxes.every((b: any) => Number.isInteger(b.x))) return card;
  const boxes: Box[] = [];
  for (const b of card.boxes) boxes.push(placeIn(boxes, { id: b.id, ...(b.req ? { req: true } : {}) }, sizeFor(b.id, d)));
  return { ...card, boxes };
}
let initial = '';
const { data, load } = useLoad(async () => {
  const d = await api.get('/patients/layout');
  draft.value = d.layout.cards.map((c: any) => withCells(c, d));
  initial = JSON.stringify(draft.value);
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
const dirty = computed(() => Boolean(data.value) && JSON.stringify(draft.value) !== initial);
const typeLabel = (t: string) => data.value?.catalogue.types.find((x: any) => x.id === t)?.label ?? t;

const live = ref('');
const say = (t: string) => { live.value = t; };
const dragCard = useDragList<Card>({
  ns: 'card', groups: () => [{ key: 'cards', items: draft.value }], idOf: (c) => c.id,
  label: (id) => { const c = draft.value.find((x) => x.id === id); return c ? cardTitle(c) : id; }, say,
});
function moveTo(ci: number, id: string, target: string) {
  const bi = draft.value[ci].boxes.findIndex((b) => b.id === id);
  const [box] = draft.value[ci].boxes.splice(bi, 1);
  const into = draft.value.find((c) => c.id === target)!;
  into.boxes.push(placeIn(into.boxes, box, { w: box.w, h: box.h }));
  say(`«${boxLabel(id)}» به «${cardTitle(into)}» رفت.`);
}
const hideBox = (ci: number, id: string) => { draft.value[ci].boxes = draft.value[ci].boxes.filter((b) => b.id !== id); };
function showBox(id: string) {
  const into = draft.value[0];
  if (into) into.boxes.push(placeIn(into.boxes, { id }));
}
// FormCardGrid sends every box's new cell; req and the order of the list stay as they were.
function setCells(card: Card, items: Item[]) {
  const at = new Map(items.map((i) => [i.id, i]));
  card.boxes = card.boxes.map((b) => ({ ...b, ...at.get(b.id)!, id: b.id }));
}
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
  const into = draft.value[0];
  if (into) for (const b of card.boxes) into.boxes.push(placeIn(into.boxes, b, { w: b.w, h: b.h }));
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
  <div class="page-head"><div><h1>چیدمان فرم بیمار</h1><p>کارت‌ها را مرتب کنید و کادرهای هر کارت را مثل صفحه‌ی گوشی هر جا که می‌خواهید بگذارید و اندازه‌شان را تغییر دهید؛ کادری را پنهان یا الزامی کنید و کادر تازه بسازید. نام و نام خانوادگی همیشه در فرم و الزامی‌اند.</p></div></div>
  <div v-if="act.notice.value" class="info-box" role="status">{{ act.notice.value }}</div>
  <div v-if="act.error.value" class="info-box" role="alert">{{ act.error.value }}</div>
  <template v-if="data">
    <p id="pl-help" class="sr-only">برای جابه‌جایی با صفحه‌کلید: فاصله یا Enter را بزنید، با کلیدهای جهت جابه‌جا کنید، Enter برای گذاشتن و Esc برای لغو. با Shift و کلیدهای جهت اندازه‌ی کادر را تغییر دهید.</p>
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
      <p v-if="!card.boxes.length" class="muted card-body">کادری در این کارت نیست.</p>
      <FormCardGrid :items="card.boxes" :label="boxLabel" :say="say" @update="setCells(card, $event)">
        <template #default="{ id, keydown, blur }">
          <div class="fl-box">
            <div class="fl-head">
              <GripButton :label="`جابه‌جایی کادر «${boxLabel(id)}»`" @keydown="keydown" @blur="blur" />
              <b>{{ boxLabel(id) }}</b>
              <span v-if="id.startsWith('c:')" class="chip chip-plain chip-mute">{{ typeLabel(customById[id]?.type) }}</span>
            </div>
            <div class="fl-tools">
              <label class="check"><input type="checkbox" :checked="Boolean(card.boxes.find((b) => b.id === id)?.req)" :disabled="NAMES.includes(id)" @change="toggleReq(card.boxes.find((b) => b.id === id)!)"><span>الزامی</span></label>
              <select class="select select-sm" :aria-label="`کارت ${boxLabel(id)}`" :value="card.id" @change="moveTo(ci, id, ($event.target as HTMLSelectElement).value)">
                <option v-for="c in draft" :key="c.id" :value="c.id">{{ cardTitle(c) }}</option>
              </select>
              <button v-if="!NAMES.includes(id)" class="btn btn-sm btn-ghost" type="button" @click="hideBox(ci, id)">پنهان</button>
            </div>
          </div>
        </template>
      </FormCardGrid>
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
