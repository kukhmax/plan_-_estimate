import { describe, expect, it } from 'vitest';
import { exifText, jpegWithSize } from '../test/jpegFixtures';
import { readExifCaptureTime } from './jpegExif';
import { copyExifUpright, readJpegSize } from './jpegMeta';

const blob = (bytes: Uint8Array<ArrayBuffer>) => new Blob([bytes], { type: 'image/jpeg' });
const bytesOf = (b: Blob) =>
  new Promise<Uint8Array>((resolve, reject) => {
    const reader = new FileReader(); // jsdom's Blob has no arrayBuffer()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(b);
  });

/** The EXIF Orientation value of a JPEG built by the fixture (IFD0 entry 0 at a known place). */
async function orientationOf(b: Blob): Promise<number | null> {
  const bytes = await bytesOf(b);
  for (let at = 2; at + 4 < bytes.length; ) {
    const marker = bytes[at + 1];
    const size = (bytes[at + 2] << 8) | bytes[at + 3];
    if (marker === 0xe1) {
      const tiff = at + 10;
      const view = new DataView(bytes.buffer, bytes.byteOffset);
      const ifd0 = tiff + view.getUint32(tiff + 4, true);
      const count = view.getUint16(ifd0, true);
      for (let i = 0; i < count; i += 1) {
        const entry = ifd0 + 2 + i * 12;
        if (view.getUint16(entry, true) === 0x0112) return view.getUint16(entry + 8, true);
      }
      return null;
    }
    at += 2 + size;
  }
  return null;
}

describe('readJpegSize', () => {
  it('reads the stored size from the frame header', async () => {
    expect(await readJpegSize(blob(jpegWithSize(3472, 3472)))).toEqual({ width: 3472, height: 3472 });
    expect(await readJpegSize(blob(jpegWithSize(1920, 1440)))).toEqual({ width: 1920, height: 1440 });
  });

  it('finds the frame header behind EXIF and big filler segments', async () => {
    const file = blob(jpegWithSize(4624, 3472, { orientation: 6, original: new Date(2026, 9, 7, 12, 0, 0), padApp: 60000 }));
    expect(await readJpegSize(file)).toEqual({ width: 4624, height: 3472 });
  });

  it('returns null for non-JPEG, truncated or header-less files instead of throwing', async () => {
    expect(await readJpegSize(new Blob(['not a jpeg at all']))).toBeNull();
    expect(await readJpegSize(new Blob([]))).toBeNull();
    expect(await readJpegSize(blob(new Uint8Array([0xff, 0xd8, 0xff, 0xd9])))).toBeNull();
    expect(await readJpegSize(blob(jpegWithSize(100, 100).slice(0, 8)))).toBeNull();
    expect(await readJpegSize(blob(jpegWithSize(0, 0)))).toBeNull();
  });
});

describe('copyExifUpright', () => {
  const shot = new Date(2026, 9, 7, 12, 30, 15);

  it('puts the EXIF block of the original into the crop, with Orientation reset to 1 and the capture time kept', async () => {
    const original = blob(jpegWithSize(1920, 1440, { orientation: 6, original: shot }));
    const crop = blob(jpegWithSize(960, 720));
    expect(await readExifCaptureTime(crop)).toBeNull();
    const merged = await copyExifUpright(original, crop);
    expect(await readExifCaptureTime(merged)).toEqual(shot);
    expect(await orientationOf(original)).toBe(6); // the original bytes are untouched
    expect(await orientationOf(merged)).toBe(1);
    expect(await readJpegSize(merged)).toEqual({ width: 960, height: 720 });
    expect(merged.type).toBe('image/jpeg');
  });

  it('goes after a JFIF block when the encoder wrote one', async () => {
    const original = blob(jpegWithSize(10, 10, { orientation: 1, original: shot }));
    const jfif = [0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00];
    const crop = jpegWithSize(5, 5);
    const withJfif = new Uint8Array([...crop.slice(0, 2), ...jfif, ...crop.slice(2)]);
    const bytes = await bytesOf(await copyExifUpright(original, blob(withJfif)));
    expect(Array.from(bytes.slice(2, 4))).toEqual([0xff, 0xe0]); // JFIF stays first
    expect(Array.from(bytes.slice(20, 22))).toEqual([0xff, 0xe1]); // EXIF right behind it
  });

  it('returns the crop unchanged when the original has no EXIF or the crop is not a JPEG', async () => {
    const crop = blob(jpegWithSize(5, 5));
    expect(await copyExifUpright(blob(jpegWithSize(10, 10)), crop)).toBe(crop);
    const png = new Blob(['PNG'], { type: 'image/png' });
    expect(await copyExifUpright(blob(jpegWithSize(10, 10, { orientation: 6, original: shot })), png)).toBe(png);
  });

  it('exposes the fixture text format the EXIF reader expects', () => {
    expect(exifText(shot)).toBe('2026:10:07 12:30:15');
  });
});
