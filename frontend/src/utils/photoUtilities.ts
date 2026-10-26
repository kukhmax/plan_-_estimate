import type { PhotoAnnotationRead } from '../types/photo';

// V2-12a: the hidden utilities on a photo of a wall before it is closed. A marker may say what lies there (a cable, a pipe...) and where
// (depth in the wall, distance from the floor, from a corner); the colour follows the type, on the picture, in the legend and in the PDFs
// (the PDFs use the same palette, see `backend/app/domain/documents/photo_report_document.py`). The numbers come from the server as they were typed.

export const PHOTO_UTILITIES = ['CABLE', 'WATER_COLD', 'WATER_HOT', 'SEWER', 'HEATING', 'GAS'] as const;
export type PhotoUtility = (typeof PHOTO_UTILITIES)[number];

export const UTILITY_COLORS: Record<PhotoUtility, string> = {
  CABLE: '#ea580c',
  WATER_COLD: '#2563eb',
  WATER_HOT: '#dc2626',
  SEWER: '#6b7280',
  HEATING: '#9333ea',
  GAS: '#a16207',
};

/** The colour of an ordinary marker (no utility). */
export const DEFAULT_MARKER_COLOR = '#dc2626';

export function isPhotoUtility(value: string | null | undefined): value is PhotoUtility {
  return value !== null && value !== undefined && (PHOTO_UTILITIES as readonly string[]).includes(value);
}

export function markerColor(marker: Pick<PhotoAnnotationRead, 'utility'>): string {
  return isPhotoUtility(marker.utility) ? UTILITY_COLORS[marker.utility] : DEFAULT_MARKER_COLOR;
}

/** A distance in cm as a text: no needless zeros, a comma ("30", "2,5"). */
export function cmText(value: number): string {
  return String(Math.round(value * 10) / 10).replace('.', ',');
}

/** What the user typed in a distance field -> the number to send (null: empty; undefined: not a number from 0 to 1000). */
export function parseDistance(raw: string): number | null | undefined {
  const text = raw.trim().replace(',', '.');
  if (text === '') return null;
  if (!/^\d+(\.\d+)?$/.test(text)) return undefined;
  const value = Number(text);
  return value >= 0 && value <= 1000 ? Math.round(value * 10) / 10 : undefined;
}

export function hasUtility(markers: readonly Pick<PhotoAnnotationRead, 'utility'>[]): boolean {
  return markers.some((marker) => isPhotoUtility(marker.utility));
}
