/**
 * Stage 13H.5 — execution display helpers.
 *
 * Server timestamps are UTC ISO 8601 (PostgreSQL: with `Z`). They are shown
 * in the device's time zone with the UI locale; a value without an offset is
 * treated as UTC (the server's semantics), never as local time.
 */
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { resolveKey } from './i18nKeys';

const LOCALE_TAGS: Record<string, string> = { pl: 'pl-PL', ru: 'ru-RU' };

export function formatRecordedDateTime(iso: string, locale: string): string {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const date = new Date(hasOffset ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(LOCALE_TAGS[locale] ?? locale, { dateStyle: 'short', timeStyle: 'short' });
}

type NameTexts = Parameters<typeof resolveKey>[0];

/** Owner/custom names verbatim; seeded names through the locale dictionary;
 * otherwise the Price Book code (never an empty label). */
export function priceItemLabel(
  t: NameTexts,
  item: Pick<SurfacePriceItemSummaryRead, 'display_name' | 'name_key' | 'code'> | null,
  fallback: string,
): string {
  if (!item) return fallback;
  if (item.display_name) return item.display_name;
  if (item.name_key) {
    const localized = resolveKey(t, item.name_key);
    if (localized !== item.name_key) return localized;
  }
  return item.code || fallback;
}

type PluralForms = { one: string; few: string; many: string; other: string };

/** Pick a CLDR plural form (pl/ru one/few/many/other) and fill {count}. */
export function pluralCount(forms: PluralForms, locale: string, count: number): string {
  const category = new Intl.PluralRules(LOCALE_TAGS[locale] ?? locale).select(count) as keyof PluralForms;
  return (forms[category] ?? forms.other).replace('{count}', String(count));
}
