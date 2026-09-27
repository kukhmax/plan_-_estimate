/**
 * Stage 13G — technological break (`wait_after_hours`) helpers.
 *
 * The stored value is always whole hours: null = no defined break, otherwise
 * an integer >= 1 (same rule as the backend schema and DB CHECK). A day hint is
 * shown only for exact multiples of 24 h; nothing is ever rounded or persisted
 * in days.
 */

/** Parse an hours input: '' -> null (no break), whole number >= 1 -> number,
 * anything else -> 'invalid' (never submitted). */
export function parseWaitInput(raw: string): number | null | 'invalid' {
  const value = raw.trim();
  if (value === '') return null;
  if (!/^\d+$/.test(value)) return 'invalid';
  const hours = Number(value);
  return hours >= 1 ? hours : 'invalid';
}

type PluralForms = { one: string; few: string; many: string; other: string };

interface WaitTexts {
  work_plan: { wait_hours_value: string; wait_days: PluralForms };
}

/** "24 h · 1 dzień", "36 h", "48 h · 2 dni" (RU: "48 ч · 2 дня"). */
export function formatWaitHours(t: WaitTexts, locale: string, hours: number): string {
  const base = t.work_plan.wait_hours_value.replace('{hours}', String(hours));
  if (hours % 24 !== 0) return base;
  const days = hours / 24;
  const category = new Intl.PluralRules(locale).select(days) as keyof PluralForms;
  const dayText = (t.work_plan.wait_days[category] ?? t.work_plan.wait_days.other).replace('{count}', String(days));
  return `${base} · ${dayText}`;
}
