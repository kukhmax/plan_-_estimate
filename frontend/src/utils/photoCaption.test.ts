import { afterEach, describe, expect, it, vi } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import {
  buildCaptionLine,
  buildLocationPath,
  formatCapturedAt,
  formatUploadedAt,
  isCapturedMuchOlderThanUpload,
  photoMoment,
  sourceLabel,
} from './photoCaption';

const PL = pl.photos.caption;
const RU = ru.photos.caption;

describe('photoCaption', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The upload instant is shown in the device's local time. The tests must not depend on the machine's timezone,
  // so the "device local time" is pinned by stubbing the local-time getters of Date (UTC getters stay real).
  function pinDeviceLocalTime(day: number, month: number, year: number, hour: number, minute: number) {
    vi.spyOn(Date.prototype, 'getDate').mockReturnValue(day);
    vi.spyOn(Date.prototype, 'getMonth').mockReturnValue(month - 1);
    vi.spyOn(Date.prototype, 'getFullYear').mockReturnValue(year);
    vi.spyOn(Date.prototype, 'getHours').mockReturnValue(hour);
    vi.spyOn(Date.prototype, 'getMinutes').mockReturnValue(minute);
  }

  it('shows the EXIF captured time exactly as stored — no timezone conversion', () => {
    expect(formatCapturedAt('2026-06-23T10:15:00')).toBe('23.06.2026 (10:15)');
    expect(formatCapturedAt('2026-01-05T00:07:59')).toBe('05.01.2026 (00:07)');
    expect(formatCapturedAt('garbage')).toBeNull();
  });

  it('converts the UTC upload time to the device local time', () => {
    pinDeviceLocalTime(23, 6, 2026, 10, 15); // the device clock reads 10:15 whatever the UTC instant is
    expect(formatUploadedAt('2026-01-01T00:00:00Z')).toBe('23.06.2026 (10:15)');
    expect(formatUploadedAt('nope')).toBeNull();
  });

  it('treats an upload timestamp without an offset as UTC', () => {
    const spy = vi.spyOn(Date.prototype, 'getHours').mockReturnValue(0);
    vi.spyOn(Date.prototype, 'getMinutes').mockReturnValue(0);
    // Same instant with and without an explicit offset parses to the same time value.
    const parsed: number[] = [];
    vi.spyOn(Date.prototype, 'getDate').mockImplementation(function (this: Date) {
      parsed.push(this.getTime());
      return 1;
    });
    formatUploadedAt('2026-06-23T08:15:00');
    formatUploadedAt('2026-06-23T08:15:00Z');
    formatUploadedAt('2026-06-23T10:15:00+02:00');
    expect(new Set(parsed).size).toBe(1);
    expect(spy).toHaveBeenCalled();
  });

  it('prefers the captured time and marks an upload time as "added"', () => {
    const both = { captured_at: '2026-06-23T10:15:00', uploaded_at: '2026-06-24T08:00:00Z' };
    expect(photoMoment(both, PL)).toEqual({ kind: 'captured', text: '23.06.2026 (10:15)' });
    const uploadedOnly = { captured_at: null, uploaded_at: '2026-06-24T08:00:00Z' };
    pinDeviceLocalTime(24, 6, 2026, 10, 0);
    expect(photoMoment(uploadedOnly, PL)).toEqual({ kind: 'uploaded', text: 'dodano 24.06.2026 (10:00)' });
    expect(photoMoment(uploadedOnly, RU)).toEqual({ kind: 'uploaded', text: 'добавлено 24.06.2026 (10:00)' });
    expect(photoMoment({ captured_at: null, uploaded_at: 'bad' }, PL)).toBeNull();
  });

  it('labels the declared source and omits an unknown one', () => {
    expect(sourceLabel('CAMERA', PL)).toBe('zrobione w aplikacji');
    expect(sourceLabel('GALLERY', PL)).toBe('dodane z galerii');
    expect(sourceLabel('CAMERA', RU)).toBe('снято в приложении');
    expect(sourceLabel('GALLERY', RU)).toBe('добавлено из галереи');
    expect(sourceLabel(null, PL)).toBeNull();
    expect(sourceLabel(undefined, PL)).toBeNull();
  });

  it('builds the location path from names, with the dash for an unresolved segment', () => {
    expect(buildLocationPath(['Salon', 'Ściana 1'], PL)).toBe('Salon → Ściana 1');
    expect(buildLocationPath(['Salon', null, 'Okno'], PL)).toBe('Salon → — → Okno');
    expect(buildLocationPath(['  ', 'Ściana 1'], PL)).toBe('— → Ściana 1');
    expect(buildLocationPath([], PL)).toBe('Obiekt');
    expect(buildLocationPath([], RU)).toBe('Объект');
  });

  it('builds the full line `location → date (time) · source` (owner example)', () => {
    const asset = { captured_at: '2026-06-23T10:15:00', uploaded_at: '2026-06-23T10:20:00Z', capture_source: 'CAMERA' as const };
    expect(buildCaptionLine('Salon → Ściana 1', asset, PL)).toBe('Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji');
    const gallery = { ...asset, capture_source: 'GALLERY' as const };
    expect(buildCaptionLine('Salon → Ściana 1', gallery, RU)).toBe('Salon → Ściana 1 → 23.06.2026 (10:15) · добавлено из галереи');
  });

  it('omits the source part for photos uploaded before the field existed, and falls back to the add time', () => {
    const legacy = { captured_at: null, uploaded_at: '2026-06-23T08:15:00Z', capture_source: null };
    pinDeviceLocalTime(23, 6, 2026, 10, 15);
    expect(buildCaptionLine('Obiekt', legacy, PL)).toBe('Obiekt → dodano 23.06.2026 (10:15)');
  });

  it('keeps the location alone when no time can be derived', () => {
    expect(buildCaptionLine('Salon', { captured_at: null, uploaded_at: 'bad', capture_source: null }, PL)).toBe('Salon');
  });

  it('flags a photo taken more than a day before it was added', () => {
    const base = { uploaded_at: '2026-06-25T12:00:00Z' };
    expect(isCapturedMuchOlderThanUpload({ ...base, captured_at: '2026-06-23T10:00:00' })).toBe(true);
    expect(isCapturedMuchOlderThanUpload({ ...base, captured_at: '2026-06-25T09:00:00' })).toBe(false);
    expect(isCapturedMuchOlderThanUpload({ ...base, captured_at: '2026-06-24T11:00:00' })).toBe(true);
    expect(isCapturedMuchOlderThanUpload({ ...base, captured_at: null })).toBe(false);
  });
});
