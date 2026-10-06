import { PhotoAssetRead, PhotoCaptureSource } from '../types/photo';

// Pure helpers for the caption line under every photo (owner clarification C-2, contract §3a):
//   `location → date (time) · source`, e.g. `Salon → Ściana 1 → 23.06.2026 (10:15) · zrobione w aplikacji`.

/** The slice of `t.photos.caption` these helpers need (kept structural so tests need no locale import). */
export interface PhotoCaptionStrings {
  added_prefix: string;
  source_camera: string;
  source_gallery: string;
  project_label: string;
  unknown_location: string;
}

export const PATH_SEPARATOR = ' → ';
const DAY_MS = 24 * 60 * 60 * 1000;

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** `DD.MM.YYYY (HH:mm)` from local date parts. */
export function formatDateTime(day: number, month: number, year: number, hour: number, minute: number): string {
  return `${pad(day)}.${pad(month)}.${year} (${pad(hour)}:${pad(minute)})`;
}

// EXIF DateTimeOriginal arrives as a naive ISO string (`2026-06-23T10:15:00`): camera-local wall-clock time.
// It is shown AS IS — never converted through Date, which would shift it by the viewer's timezone.
const NAIVE_ISO = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/;

export function formatCapturedAt(value: string): string | null {
  const match = NAIVE_ISO.exec(value);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  return formatDateTime(Number(day), Number(month), Number(year), Number(hour), Number(minute));
}

function parseUtcInstant(value: string): Date | null {
  // A timestamp without an offset is treated as UTC (the backend stores UTC).
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(hasOffset ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** UTC instant → `DD.MM.YYYY (HH:mm)` in the device's local time. */
export function formatUploadedAt(value: string): string | null {
  const date = parseUtcInstant(value);
  if (!date) return null;
  return formatDateTime(date.getDate(), date.getMonth() + 1, date.getFullYear(), date.getHours(), date.getMinutes());
}

export interface PhotoMoment {
  kind: 'captured' | 'uploaded';
  /** `DD.MM.YYYY (HH:mm)`; for an upload time it is prefixed with the localized "added" marker. */
  text: string;
}

/** Captured time when EXIF has one, otherwise the upload time (marked as added). Null if neither parses. */
export function photoMoment(asset: Pick<PhotoAssetRead, 'captured_at' | 'uploaded_at'>, strings: PhotoCaptionStrings): PhotoMoment | null {
  const captured = asset.captured_at ? formatCapturedAt(asset.captured_at) : null;
  if (captured) return { kind: 'captured', text: captured };
  const uploaded = formatUploadedAt(asset.uploaded_at);
  return uploaded ? { kind: 'uploaded', text: `${strings.added_prefix} ${uploaded}` } : null;
}

/** `DD.MM.YYYY` of the photo (captured date when known, else the local upload date) for day grouping. */
export function photoDayLabel(asset: Pick<PhotoAssetRead, 'captured_at' | 'uploaded_at'>): string {
  const text = (asset.captured_at ? formatCapturedAt(asset.captured_at) : null) ?? formatUploadedAt(asset.uploaded_at);
  return text ? text.slice(0, 10) : '';
}

export function sourceLabel(source: PhotoCaptureSource | null | undefined, strings: PhotoCaptionStrings): string | null {
  if (source === 'CAMERA') return strings.source_camera;
  if (source === 'GALLERY') return strings.source_gallery;
  return null; // unknown (uploaded before the field existed): the part is omitted
}

/**
 * Location path from the names the host already has (room → surface → opening). A segment that cannot be
 * resolved (target archived / not loaded) shows the localized dash; an empty list is the project itself.
 */
export function buildLocationPath(
  segments: ReadonlyArray<string | null | undefined>,
  strings: PhotoCaptionStrings,
): string {
  if (segments.length === 0) return strings.project_label;
  return segments
    .map((segment) => (segment && segment.trim() !== '' ? segment.trim() : strings.unknown_location))
    .join(PATH_SEPARATOR);
}

/** The full caption line: `location → date (time) · source`; the source part is omitted when unknown. */
export function buildCaptionLine(
  locationLabel: string,
  asset: Pick<PhotoAssetRead, 'captured_at' | 'uploaded_at' | 'capture_source'>,
  strings: PhotoCaptionStrings,
): string {
  const moment = photoMoment(asset, strings);
  const path = moment ? `${locationLabel}${PATH_SEPARATOR}${moment.text}` : locationLabel;
  const source = sourceLabel(asset.capture_source, strings);
  return source ? `${path} · ${source}` : path;
}

/**
 * True when the photo was taken more than one day before it was added (viewer hint). The captured time has no
 * timezone, so it is compared as if it were UTC; a timezone offset is under a day, so the hint can be off only
 * within a few hours of the one-day boundary, which is irrelevant for a hint.
 */
export function isCapturedMuchOlderThanUpload(
  asset: Pick<PhotoAssetRead, 'captured_at' | 'uploaded_at'>,
): boolean {
  if (!asset.captured_at) return false;
  const captured = NAIVE_ISO.exec(asset.captured_at);
  const uploaded = parseUtcInstant(asset.uploaded_at);
  if (!captured || !uploaded) return false;
  const [, year, month, day, hour, minute] = captured;
  const capturedMs = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  return uploaded.getTime() - capturedMs > DAY_MS;
}
