import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';

type Locale = 'pl' | 'ru';
type LocaleData = typeof pl;

const locales: Record<Locale, LocaleData> = { pl, ru };

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
  const [locale, setLocaleState] = useState<Locale>(() => {
    const stored = localStorage.getItem('locale') as Locale | null;
    return stored && stored in locales ? stored : 'pl';
  });

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem('locale', next);
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
