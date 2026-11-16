<script lang="ts">
// One queue for every preview on the page: images are drawn one at a time (SPEC §14.5.2).
let chain: Promise<void> = Promise.resolve();
const enqueue = (job: () => Promise<void>) => { chain = chain.then(job, job); };
</script>

<script setup lang="ts">
// Preview of a chosen file before upload (SPEC §14.5.2). JPG and PNG are drawn in the browser: the file becomes an
// ImageBitmap scaled into a canvas of at most 960 px on the long side, then the bitmap is closed. Nothing goes to the
// server and no blob URL is made, so the CSP does not change. PDF and DICOM show the type badge of DocTile.
import { onBeforeUnmount, onMounted, ref } from 'vue';
import Icon from './Icon.vue';

const props = defineProps<{ file: File; kind: string }>();
const canvas = ref<HTMLCanvasElement | null>(null);
const MAX = 960;
let gone = false;

async function draw() {
  const el = canvas.value;
  if (gone || !el) return;
  try {
    const bmp = await createImageBitmap(props.file, { imageOrientation: 'from-image' });
    try {
      const scale = Math.min(1, MAX / Math.max(bmp.width, bmp.height));
      el.width = Math.max(1, Math.round(bmp.width * scale));
      el.height = Math.max(1, Math.round(bmp.height * scale));
      el.getContext('2d')?.drawImage(bmp, 0, 0, el.width, el.height);
    } finally {
      bmp.close();
    }
  } catch { /* an unreadable image keeps the empty frame; the server still checks the file */ }
}
onMounted(() => { if (props.kind === 'image') enqueue(draw); });
onBeforeUnmount(() => { gone = true; });
</script>

<template>
  <canvas v-if="kind === 'image'" ref="canvas" class="up-canvas" role="img" :aria-label="file.name"></canvas>
  <span v-else class="doc-type up-badge"><Icon name="file" /><b>{{ kind === 'pdf' ? 'PDF' : 'DICOM' }}</b></span>
</template>
