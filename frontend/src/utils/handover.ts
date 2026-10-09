import type { PremisesRequirement } from '../types/contractCatalog';
import type { MeasuredValue } from '../types/handover';

/** A number as the owner typed it ("12,5" -> 12.5); null for an empty or unreadable text. */
export function parseNumber(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

export function numberText(value: unknown): string {
  return typeof value === 'number' ? String(value).replace('.', ',') : '';
}

/** What a requirement asks for, as shown beside it: a yes / no, a number with its unit, or a range ("od 5 do 25 °C"). */
export function formatRequired(
  requirement: PremisesRequirement,
  value: MeasuredValue | boolean | undefined,
  words: { yes: string; no: string; from: string; to: string },
  unit: string | null,
): string | null {
  if (value === undefined || value === null) return null;
  const suffix = unit ? ` ${unit}` : '';
  if (typeof value === 'boolean') return value ? words.yes : words.no;
  if (typeof value === 'number') return `${numberText(value)}${suffix}`;
  if (requirement.value_kind === 'NUMBER_RANGE') return `${words.from} ${numberText(value.min)} ${words.to} ${numberText(value.max)}${suffix}`;
  return null;
}
