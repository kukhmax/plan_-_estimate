import { OpeningType, OpeningTypeValue } from '../types/opening';

/** One row of the compact surface-card opening summary (13E.5B). */
export interface OpeningSummaryRow {
  openingType: OpeningTypeValue;
  /** Normalized 3-decimal metre strings, e.g. "0.900" (grouping key). */
  width: string;
  height: string;
  /** SUM(Opening.quantity) of the grouped active openings. */
  count: number;
}

const TYPE_ORDER: Record<OpeningTypeValue, number> = { DOOR: 0, WINDOW: 1, OTHER: 2 };

/** Stable 3-decimal representation of a backend decimal (string or number). */
function normalize(value: string | number): string {
  return Number(value).toFixed(3);
}

/**
 * Groups ACTIVE openings by type + width + height (SUM of quantity).
 * Archived openings are excluded. Deterministic order: DOOR, WINDOW, OTHER,
 * then width, then height ascending. Read-only presentation: never used for
 * area, deduction or reveal calculations.
 */
export function summarizeOpenings(openings: OpeningType[] | undefined | null): OpeningSummaryRow[] {
  const groups = new Map<string, OpeningSummaryRow>();
  for (const opening of openings ?? []) {
    if (opening.is_archived) continue;
    const width = normalize(opening.width);
    const height = normalize(opening.height);
    const key = `${opening.opening_type}|${width}|${height}`;
    const row = groups.get(key);
    const quantity = opening.quantity ?? 1;
    if (row) row.count += quantity;
    else groups.set(key, { openingType: opening.opening_type, width, height, count: quantity });
  }
  return [...groups.values()].sort(
    (a, b) =>
      TYPE_ORDER[a.openingType] - TYPE_ORDER[b.openingType] ||
      Number(a.width) - Number(b.width) ||
      Number(a.height) - Number(b.height),
  );
}

/** "0.900" -> "0,90" (two decimals, PL/RU decimal comma). */
export function formatOpeningDimension(value: string): string {
  return Number(value).toFixed(2).replace('.', ',');
}
