// Image shrinking before upload (legacy app.js shrinkImage, D21): JPG/PNG over 3 MB are redrawn as JPEG, long edge
// at most 2560 px, quality then size stepped down until the file fits. Redrawing drops EXIF (GPS). If anything fails
// the original file is uploaded unchanged; the server still checks type and 30 MB.
import { fa } from './fmt';

export const SHRINK_LIMIT = 3 * 1024 * 1024;
export const MULTI_LIMIT = 30 * 1024 * 1024;
const MAX_EDGE = 2560;

export const isShrinkable = (f: File) => /^image\/(jpeg|png)$/.test(f.type) || /\.(jpe?g|png)$/i.test(f.name);
export const mbText = (n: number) => fa((n / 1048576).toFixed(1)).replace('.', '٫') + ' مگابایت';

export async function shrinkImage(file: File): Promise<File> {
  if (file.size <= SHRINK_LIMIT || !isShrinkable(file)) return file;
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d')!;
  let scale = Math.min(1, MAX_EDGE / Math.max(bmp.width, bmp.height));
  try {
    for (let round = 0; round < 8; round++) {
      canvas.width = Math.max(1, Math.round(bmp.width * scale));
      canvas.height = Math.max(1, Math.round(bmp.height * scale));
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
      for (const q of [0.9, 0.8, 0.7, 0.6]) {
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', q));
        if (blob && blob.size <= SHRINK_LIMIT) {
          const name = file.name.replace(/\.(jpe?g|png)$/i, '') + '.jpg';
          return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
        }
      }
      scale *= 0.8;
    }
  } finally {
    bmp.close();
  }
  return file;
}

export async function prepareFiles(files: File[]): Promise<File[]> {
  const out: File[] = [];
  for (const f of files) {
    try { out.push(await shrinkImage(f)); } catch { out.push(f); }
  }
  return out;
}
