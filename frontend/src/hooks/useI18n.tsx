import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import uk from '../locales/uk.json';
import en from '../locales/en.json';
import { isLocale, localeFromTelegramCode, type Locale } from '../utils/locale';

type LocaleData = typeof pl;

const locales: Record<Locale, LocaleData> = { pl, ru, uk, en };

function firstLocale(): Locale {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem('locale');
  } catch {
    stored = null;
  }
  if (isLocale(stored)) return stored;
  // V2-7: a new user starts in the language of Telegram; the choice made by hand is kept afterwards
  return localeFromTelegramCode(window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code ?? null);
}

interface I18nContextValue {
  locale: Locale;
  t: LocaleData;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'pl',
  t: pl,
  setLocale: () => undefined,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(firstLocale);

  const setLocale = useCallback((next: Locale) => {
    try {
      localStorage.setItem('locale', next);
    } catch {
      // the language still changes for this visit
    }
    setLocaleState(next);
  }, []);

  return (
    <I18nContext.Provider value={{ locale, t: locales[locale], setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
