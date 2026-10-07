// Read-only JPEG helpers for the in-app camera (Stage 14E.10): the pixel size of a photo (to see whether the camera really
// gave a 4:3 frame) and carrying the EXIF block over to a re-encoded crop (so the capture time survives a digital zoom).
// Everything is bounds-checked; anything unreadable returns null / the input unchanged.

const HEAD_BYTES = 1024 * 1024; // the headers (EXIF, ICC, XMP, MakerNote) of a phone JPEG come before the frame header
const TAG_ORIENTATION = 0x0112;
const TYPE_SHORT = 3;

async function readBytes(blob: Blob): Promise<Uint8Array<ArrayBuffer>> {
  if (typeof blob.arrayBuffer === 'function') return new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

export interface JpegSize {
  width: number;
  height: number;
}

/** Start frame (SOFn) markers; C4 (DHT), C8 (JPG) and CC (DAC) share the range but are not frame headers. */
const isFrameMarker = (marker: number) => marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;

/** The stored pixel size of a JPEG (before EXIF orientation), or null when it cannot be read from the file head. */
export async function readJpegSize(file: Blob): Promise<JpegSize | null> {
  const bytes = await readBytes(file.slice(0, HEAD_BYTES));
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.byteLength < 4 || view.getUint16(0, false) !== 0xffd8) return null;
  let at = 2;
  while (at + 4 <= view.byteLength) {
    if (view.getUint8(at) !== 0xff) return null;
    const marker = view.getUint8(at + 1);
    if (marker === 0xff) {
      at += 1; // fill byte
      continue;
    }
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      at += 2; // markers without a length
      continue;
    }
    if (marker === 0xd9 || marker === 0xda) return null; // end / image data before any frame header
    const size = view.getUint16(at + 2, false);
    if (size < 2) return null;
    if (isFrameMarker(marker)) {
      if (at + 9 > view.byteLength) return null;
      const height = view.getUint16(at + 5, false);
      const width = view.getUint16(at + 7, false);
      return width > 0 && height > 0 ? { width, height } : null;
    }
    at += 2 + size;
  }
  return null;
}

/** The EXIF segment (marker, length and payload) and where its TIFF header starts inside the file head. */
function findExifSegment(bytes: Uint8Array): { start: number; end: number; tiff: number } | null {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.byteLength < 4 || view.getUint16(0, false) !== 0xffd8) return null;
  let at = 2;
  while (at + 4 <= view.byteLength) {
    if (view.getUint8(at) !== 0xff) return null;
    const marker = view.getUint8(at + 1);
    if (marker === 0xda || marker === 0xd9) return null;
    const size = view.getUint16(at + 2, false);
    if (size < 2) return null;
    const end = at + 2 + size;
    if (marker === 0xe1 && end <= view.byteLength && size >= 8 + 6) {
      if (view.getUint32(at + 4, false) === 0x45786966 && view.getUint16(at + 8, false) === 0x0000) {
        return { start: at, end, tiff: at + 10 };
      }
    }
    at = end;
  }
  return null;
}

/** Sets the EXIF Orientation of the copied block to 1 (the pixels of the crop are already upright). Silent when absent. */
function resetOrientation(segment: Uint8Array, tiffAt: number): void {
  const view = new DataView(segment.buffer, segment.byteOffset, segment.byteLength);
  if (tiffAt + 8 > view.byteLength) return;
  const order = view.getUint16(tiffAt, false);
  if (order !== 0x4949 && order !== 0x4d4d) return;
  const little = order === 0x4949;
  if (view.getUint16(tiffAt + 2, little) !== 0x002a) return;
  const ifd0 = tiffAt + view.getUint32(tiffAt + 4, little);
  if (ifd0 + 2 > view.byteLength) return;
  const count = Math.min(view.getUint16(ifd0, little), 512);
  for (let i = 0; i < count; i += 1) {
    const entry = ifd0 + 2 + i * 12;
    if (entry + 12 > view.byteLength) return;
    if (view.getUint16(entry, little) === TAG_ORIENTATION && view.getUint16(entry + 2, little) === TYPE_SHORT) {
      view.setUint16(entry + 8, 1, little);
      return;
    }
  }
}

/**
 * `target` (a re-encoded crop, upright) with the EXIF block of `source` (the original shot) put right after its start marker,
 * Orientation reset to 1. Without an EXIF block in `source`, or when `target` is not a JPEG, `target` is returned unchanged.
 */
export async function copyExifUpright(source: Blob, target: Blob): Promise<Blob> {
  const head = await readBytes(source.slice(0, HEAD_BYTES));
  const found = findExifSegment(head);
  if (!found) return target;
  const segment = head.slice(found.start, found.end); // a copy: the original bytes are not touched
  resetOrientation(segment, found.tiff - found.start);
  const body = await readBytes(target);
  if (body.length < 2 || body[0] !== 0xff || body[1] !== 0xd8) return target;
  // canvas encoders write a JFIF block (APP0) first; EXIF goes after it, as cameras do
  let insertAt = 2;
  if (body.length >= 6 && body[2] === 0xff && body[3] === 0xe0) {
    const jfifEnd = 4 + ((body[4] << 8) | body[5]);
    if (jfifEnd <= body.length) insertAt = jfifEnd;
  }
  return new Blob([body.subarray(0, insertAt), segment, body.subarray(insertAt)], { type: target.type || 'image/jpeg' });
}
