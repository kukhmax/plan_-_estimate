/** V2-7 — the languages of the screens: Polish (the default of the Polish market), Russian, Ukrainian and English. */
export const LOCALES = ['pl', 'ru', 'uk', 'en'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'pl';

/** What the list of languages shows: the name in its own language. */
export const LOCALE_NAMES: Record<Locale, string> = { pl: 'Polski', ru: 'Русский', uk: 'Українська', en: 'English' };

/** BCP 47 tags of the formatters of dates, numbers and plurals. */
export const LOCALE_TAGS: Record<Locale, string> = { pl: 'pl-PL', ru: 'ru-RU', uk: 'uk-UA', en: 'en-GB' };

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

export function localeTag(locale: string): string {
  return isLocale(locale) ? LOCALE_TAGS[locale] : locale;
}

/** The first language of a new user: the language of Telegram (uk-UA, en-GB, ru ... → the same screens), anything else → Polish. */
export function localeFromTelegramCode(code: string | null | undefined): Locale {
  const base = (code ?? '').toLowerCase().split(/[-_]/)[0];
  return isLocale(base) ? base : DEFAULT_LOCALE;
}
