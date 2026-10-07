// Builds tiny JPEG byte strings with (or without) an EXIF block — only what the EXIF reader looks at.

interface ExifDates {
  original?: Date;
  digitized?: Date;
  dateTime?: Date;
  bigEndian?: boolean;
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0');

/** "YYYY:MM:DD HH:MM:SS" in device-local time, as cameras write it. */
export function exifText(date: Date): string {
  return `${pad(date.getFullYear(), 4)}:${pad(date.getMonth() + 1)}:${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

/** A JPEG (SOI + optional APP1/EXIF + EOI) carrying the given dates, or only SOI + EOI when none is given. */
export function jpegWithExif(dates: ExifDates = {}, rawTexts: { original?: string } = {}): Uint8Array<ArrayBuffer> {
  const little = !dates.bigEndian;
  const originalText = rawTexts.original ?? (dates.original ? exifText(dates.original) : undefined);
  const exifTags: Array<[number, string]> = [];
  if (originalText !== undefined) exifTags.push([0x9003, originalText]);
  if (dates.digitized) exifTags.push([0x9004, exifText(dates.digitized)]);
  const ifd0Tags: Array<[number, string | 'exif']> = [];
  if (dates.dateTime) ifd0Tags.push([0x0132, exifText(dates.dateTime)]);
  if (exifTags.length > 0) ifd0Tags.push([0x8769, 'exif']);
  if (ifd0Tags.length === 0) return new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);

  const ifd0Size = 2 + ifd0Tags.length * 12 + 4;
  const exifSize = exifTags.length > 0 ? 2 + exifTags.length * 12 + 4 : 0;
  const ifd0At = 8;
  const exifAt = ifd0At + ifd0Size;
  const stringsAt = exifAt + exifSize;
  const tiff = new DataView(new ArrayBuffer(stringsAt + 20 * (ifd0Tags.length + exifTags.length)));
  tiff.setUint16(0, little ? 0x4949 : 0x4d4d, false);
  tiff.setUint16(2, 0x002a, little);
  tiff.setUint32(4, ifd0At, little);

  let nextString = stringsAt;
  const writeString = (text: string) => {
    const at = nextString;
    for (let i = 0; i < text.length; i += 1) tiff.setUint8(at + i, text.charCodeAt(i));
    nextString += 20;
    return at;
  };
  const writeEntry = (at: number, tag: number, type: number, count: number, value: number) => {
    tiff.setUint16(at, tag, little);
    tiff.setUint16(at + 2, type, little);
    tiff.setUint32(at + 4, count, little);
    tiff.setUint32(at + 8, value, little);
  };
  tiff.setUint16(ifd0At, ifd0Tags.length, little);
  ifd0Tags.forEach(([tag, value], i) => {
    const at = ifd0At + 2 + i * 12;
    if (value === 'exif') writeEntry(at, tag, 4, 1, exifAt);
    else writeEntry(at, tag, 2, 20, writeString(value));
  });
  if (exifTags.length > 0) {
    tiff.setUint16(exifAt, exifTags.length, little);
    exifTags.forEach(([tag, value], i) => writeEntry(exifAt + 2 + i * 12, tag, 2, 20, writeString(value)));
  }

  const tiffBytes = new Uint8Array(tiff.buffer);
  const app1Length = 2 + 6 + tiffBytes.length;
  const out = new Uint8Array(2 + 2 + app1Length + 2);
  out.set([0xff, 0xd8, 0xff, 0xe1, (app1Length >> 8) & 0xff, app1Length & 0xff, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00], 0);
  out.set(tiffBytes, 12);
  out.set([0xff, 0xd9], out.length - 2);
  return out;
}

export const jpegFile = (name: string, bytes: Uint8Array<ArrayBuffer> = jpegWithExif()) => new File([bytes], name, { type: 'image/jpeg' });

/**
 * A JPEG that declares a pixel size (SOI, optional EXIF with Orientation and DateTimeOriginal, SOF0, EOI), little-endian EXIF.
 * `padApp` adds a filler APP2 segment of that many bytes before the frame header (phone files carry large headers).
 */
export function jpegWithSize(
  width: number,
  height: number,
  options: { orientation?: number; original?: Date; padApp?: number } = {},
): Uint8Array<ArrayBuffer> {
  const parts: number[][] = [[0xff, 0xd8]];
  if (options.orientation !== undefined || options.original) {
    const tiff = new DataView(new ArrayBuffer(76));
    const little = true;
    tiff.setUint16(0, 0x4949, false);
    tiff.setUint16(2, 0x002a, little);
    tiff.setUint32(4, 8, little);
    tiff.setUint16(8, 2, little); // IFD0: Orientation + pointer to the Exif IFD
    tiff.setUint16(10, 0x0112, little);
    tiff.setUint16(12, 3, little);
    tiff.setUint32(14, 1, little);
    tiff.setUint16(18, options.orientation ?? 1, little);
    tiff.setUint16(22, 0x8769, little);
    tiff.setUint16(24, 4, little);
    tiff.setUint32(26, 1, little);
    tiff.setUint32(30, 38, little);
    tiff.setUint16(38, options.original ? 1 : 0, little); // Exif IFD
    if (options.original) {
      tiff.setUint16(40, 0x9003, little);
      tiff.setUint16(42, 2, little);
      tiff.setUint32(44, 20, little);
      tiff.setUint32(48, 56, little);
      const text = exifText(options.original);
      for (let i = 0; i < text.length; i += 1) tiff.setUint8(56 + i, text.charCodeAt(i));
    }
    const payload = [0x45, 0x78, 0x69, 0x66, 0x00, 0x00, ...new Uint8Array(tiff.buffer)];
    const length = payload.length + 2;
    parts.push([0xff, 0xe1, (length >> 8) & 0xff, length & 0xff, ...payload]);
  }
  if (options.padApp) {
    const length = options.padApp + 2;
    parts.push([0xff, 0xe2, (length >> 8) & 0xff, length & 0xff, ...new Array<number>(options.padApp).fill(0)]);
  }
  parts.push([0xff, 0xc0, 0x00, 0x11, 0x08, (height >> 8) & 0xff, height & 0xff, (width >> 8) & 0xff, width & 0xff, 0x03, 0x01, 0x22, 0x00, 0x02, 0x11, 0x01, 0x03, 0x11, 0x01]);
  parts.push([0xff, 0xd9]);
  return new Uint8Array(parts.flat());
}
