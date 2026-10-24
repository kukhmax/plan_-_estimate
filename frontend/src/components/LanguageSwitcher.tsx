import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { LOCALES, LOCALE_NAMES } from '../utils/locale';

/**
 * V2-7 — the language of the screens: one small button with the code of the current language that opens a list of the four
 * (PL, RU, UK, EN), each named in its own language. Closes on a choice, on a tap outside and on Escape.
 */
export function LanguageSwitcher() {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event: Event) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={box} className="relative shrink-0">
      <button
        type="button"
        aria-label="language-switch"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="min-h-11 min-w-11 px-2 text-xs rounded-lg font-semibold uppercase flex items-center justify-center gap-0.5"
        style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', color: 'var(--tg-theme-text-color)' }}
      >
        {locale}
        <span aria-hidden="true" className="text-[10px]">▾</span>
      </button>
      {open && (
        <div
          role="group"
          aria-label="language-list"
          className="absolute right-0 top-full mt-1 z-50 min-w-[10rem] rounded-xl p-1 shadow-lg border"
          style={{
            backgroundColor: 'var(--tg-theme-bg-color)',
            borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))',
          }}
        >
          {LOCALES.map((code) => (
            <button
              key={code}
              type="button"
              aria-label={`lang-${code}`}
              aria-pressed={locale === code}
              onClick={() => {
                setLocale(code);
                setOpen(false);
              }}
              className="min-h-11 w-full px-3 text-sm rounded-lg flex items-center justify-between gap-3 text-left"
              style={
                locale === code
                  ? { backgroundColor: 'var(--tg-theme-button-color)', color: 'var(--tg-theme-button-text-color)' }
                  : { color: 'var(--tg-theme-text-color)' }
              }
            >
              <span className="font-semibold uppercase">{code}</span>
              <span className="break-words">{LOCALE_NAMES[code]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
