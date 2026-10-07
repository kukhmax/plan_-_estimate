// Minimal, read-only EXIF reader for JPEG files: the capture time (DateTimeOriginal, else DateTimeDigitized, else DateTime).
// It exists for one purpose — telling whether a file picked through the camera button was really taken a moment ago
// (hosts such as Telegram on Android ignore `capture` and copy the picked file, so the file's own modification time says
// nothing about when the photo was taken). Everything is bounds-checked; anything unreadable returns null.

const HEAD_BYTES = 131072; // the EXIF block sits at the very start of a JPEG (APP1 is at most 64 KB)

const TAG_DATE_TIME = 0x0132; // IFD0
const TAG_EXIF_IFD = 0x8769; // IFD0 -> pointer to the Exif sub-IFD
const TAG_DATE_TIME_ORIGINAL = 0x9003; // Exif IFD
const TAG_DATE_TIME_DIGITIZED = 0x9004; // Exif IFD
const TYPE_ASCII = 2;
const TYPE_LONG = 4;

const EXIF_DATE = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$/;

async function readHead(file: Blob): Promise<ArrayBuffer> {
  const head = file.slice(0, HEAD_BYTES);
  if (typeof head.arrayBuffer === 'function') return head.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(head);
  });
}

interface Tiff {
  view: DataView;
  start: number; // offset of the TIFF header inside the view; all IFD offsets are relative to it
  little: boolean;
}

function u16(t: Tiff, at: number): number | null {
  return at >= 0 && at + 2 <= t.view.byteLength ? t.view.getUint16(at, t.little) : null;
}

function u32(t: Tiff, at: number): number | null {
  return at >= 0 && at + 4 <= t.view.byteLength ? t.view.getUint32(at, t.little) : null;
}

/** The entries of one IFD as tag -> position of its 12-byte entry (absolute in the view). */
function entries(t: Tiff, ifdOffset: number): Map<number, number> {
  const found = new Map<number, number>();
  const base = t.start + ifdOffset;
  const count = u16(t, base);
  if (count === null) return found;
  for (let i = 0; i < count && i < 512; i += 1) {
    const at = base + 2 + i * 12;
    const tag = u16(t, at);
    if (tag === null) break;
    found.set(tag, at);
  }
  return found;
}

function asciiValue(t: Tiff, entryAt: number): string | null {
  if (u16(t, entryAt + 2) !== TYPE_ASCII) return null;
  const length = u32(t, entryAt + 4);
  if (length === null || length < 19 || length > 64) return null;
  const valueAt = length <= 4 ? entryAt + 8 : t.start + (u32(t, entryAt + 8) ?? -1);
  if (valueAt < 0 || valueAt + length > t.view.byteLength) return null;
  let text = '';
  for (let i = 0; i < length; i += 1) {
    const code = t.view.getUint8(valueAt + i);
    if (code === 0) break;
    text += String.fromCharCode(code);
  }
  return text;
}

function toDate(text: string | null): Date | null {
  const match = text ? EXIF_DATE.exec(text) : null;
  if (!match) return null;
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  if (year < 1990 || month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 59) return null;
  // EXIF carries camera-local time without a zone: it is read as the device's local time, like the rest of the app does.
  return new Date(year, month - 1, day, hour, minute, second);
}

function locateTiff(view: DataView): Tiff | null {
  if (view.byteLength < 4 || view.getUint16(0, false) !== 0xffd8) return null; // not a JPEG
  let at = 2;
  while (at + 4 <= view.byteLength) {
    if (view.getUint8(at) !== 0xff) return null;
    const marker = view.getUint8(at + 1);
    if (marker === 0xda || marker === 0xd9) return null; // image data / end: no EXIF before it
    const size = view.getUint16(at + 2, false);
    if (size < 2) return null;
    if (marker === 0xe1 && at + 10 <= view.byteLength) {
      const isExif =
        view.getUint32(at + 4, false) === 0x45786966 && // "Exif"
        view.getUint16(at + 8, false) === 0x0000;
      if (isExif) {
        const start = at + 10;
        if (start + 8 > view.byteLength) return null;
        const order = view.getUint16(start, false);
        if (order !== 0x4949 && order !== 0x4d4d) return null;
        const little = order === 0x4949;
        if (view.getUint16(start + 2, little) !== 0x002a) return null;
        return { view, start, little };
      }
    }
    at += 2 + size;
  }
  return null;
}

/** The capture time written by the camera, or null when the file has none (screenshots, downloads, stripped files, non-JPEG). */
export async function readExifCaptureTime(file: Blob): Promise<Date | null> {
  const view = new DataView(await readHead(file));
  const tiff = locateTiff(view);
  if (!tiff) return null;
  const ifd0Offset = u32(tiff, tiff.start + 4);
  if (ifd0Offset === null) return null;
  const ifd0 = entries(tiff, ifd0Offset);

  const exifPointerAt = ifd0.get(TAG_EXIF_IFD);
  if (exifPointerAt !== undefined && u16(tiff, exifPointerAt + 2) === TYPE_LONG) {
    const exifOffset = u32(tiff, exifPointerAt + 8);
    if (exifOffset !== null) {
      const exif = entries(tiff, exifOffset);
      for (const tag of [TAG_DATE_TIME_ORIGINAL, TAG_DATE_TIME_DIGITIZED]) {
        const at = exif.get(tag);
        const date = at === undefined ? null : toDate(asciiValue(tiff, at));
        if (date) return date;
      }
    }
  }
  const dateTimeAt = ifd0.get(TAG_DATE_TIME);
  return dateTimeAt === undefined ? null : toDate(asciiValue(tiff, dateTimeAt));
}
