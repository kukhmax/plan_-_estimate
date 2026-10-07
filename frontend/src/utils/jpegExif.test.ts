import { describe, expect, it } from 'vitest';
import { exifText, jpegFile, jpegWithExif } from '../test/jpegFixtures';
import { readExifCaptureTime } from './jpegExif';

const when = new Date(2026, 9, 7, 1, 53, 21); // local time

describe('readExifCaptureTime', () => {
  it('reads DateTimeOriginal as device-local time (little-endian)', async () => {
    const date = await readExifCaptureTime(jpegFile('a.jpg', jpegWithExif({ original: when })));
    expect(date?.getTime()).toBe(when.getTime());
  });

  it('reads big-endian EXIF too', async () => {
    const date = await readExifCaptureTime(jpegFile('b.jpg', jpegWithExif({ original: when, bigEndian: true })));
    expect(date?.getTime()).toBe(when.getTime());
  });

  it('prefers DateTimeOriginal over DateTimeDigitized over DateTime', async () => {
    const other = new Date(2020, 0, 2, 3, 4, 5);
    const all = await readExifCaptureTime(jpegFile('c.jpg', jpegWithExif({ original: when, digitized: other, dateTime: other })));
    expect(all?.getTime()).toBe(when.getTime());
    const digitized = await readExifCaptureTime(jpegFile('d.jpg', jpegWithExif({ digitized: when, dateTime: other })));
    expect(digitized?.getTime()).toBe(when.getTime());
    const plain = await readExifCaptureTime(jpegFile('e.jpg', jpegWithExif({ dateTime: when })));
    expect(plain?.getTime()).toBe(when.getTime());
  });

  it('returns null for a JPEG without EXIF (screenshots, downloads)', async () => {
    expect(await readExifCaptureTime(jpegFile('f.jpg', jpegWithExif()))).toBeNull();
  });

  it('returns null for non-JPEG, empty and truncated input', async () => {
    const png = new File([Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])], 'g.png', { type: 'image/png' });
    expect(await readExifCaptureTime(png)).toBeNull();
    expect(await readExifCaptureTime(new File([], 'empty.jpg'))).toBeNull();
    const bytes = jpegWithExif({ original: when });
    for (const cut of [3, 11, 20, 40, bytes.length - 30]) {
      expect(await readExifCaptureTime(new File([bytes.slice(0, cut)], 'cut.jpg'))).toBeNull();
    }
  });

  it('returns null for garbage dates and impossible values', async () => {
    for (const text of ['0000:00:00 00:00:00', '2026:13:40 25:61:61', 'not a date at all!!', '2026-10-07 01:53:21 ']) {
      expect(await readExifCaptureTime(jpegFile('h.jpg', jpegWithExif({}, { original: text })))).toBeNull();
    }
  });

  it('does not throw on random bytes after a JPEG header', async () => {
    const noise = new Uint8Array(600).map((_, i) => (i * 37 + 11) % 256);
    noise[0] = 0xff;
    noise[1] = 0xd8;
    await expect(readExifCaptureTime(new File([noise], 'noise.jpg'))).resolves.toBeNull();
  });

  it('formats and parses the same text (fixture sanity)', () => {
    expect(exifText(when)).toBe('2026:10:07 01:53:21');
  });
});
