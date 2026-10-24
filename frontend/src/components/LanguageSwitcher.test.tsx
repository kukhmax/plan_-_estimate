import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider, useI18n } from '../hooks/useI18n';
import { LanguageSwitcher } from './LanguageSwitcher';

function Probe() {
  const { locale, t } = useI18n();
  return <p aria-label="probe">{locale}:{t.common.save}</p>;
}

function renderSwitcher() {
  return render(
    <I18nProvider>
      <LanguageSwitcher />
      <Probe />
    </I18nProvider>,
  );
}

describe('LanguageSwitcher (V2-7)', () => {
  beforeEach(() => {
    localStorage.clear();
    delete window.Telegram;
  });

  it('shows the current language and a closed list', () => {
    renderSwitcher();
    expect(screen.getByRole('button', { name: 'language-switch' })).toHaveTextContent('pl');
    expect(screen.getByRole('button', { name: 'language-switch' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: 'lang-ru' })).toBeNull();
  });

  it('lists the four languages with touch-sized rows, each in its own language', () => {
    renderSwitcher();
    fireEvent.click(screen.getByRole('button', { name: 'language-switch' }));
    for (const [code, name] of [['pl', 'Polski'], ['ru', 'Русский'], ['uk', 'Українська'], ['en', 'English']]) {
      const row = screen.getByRole('button', { name: `lang-${code}` });
      expect(row).toHaveTextContent(name);
      expect(row.className).toContain('min-h-11');
    }
    expect(screen.getByRole('button', { name: 'lang-pl' })).toHaveAttribute('aria-pressed', 'true');
  });

  it.each(['ru', 'uk', 'en'])('chooses %s, closes the list and keeps the choice', (code) => {
    renderSwitcher();
    fireEvent.click(screen.getByRole('button', { name: 'language-switch' }));
    fireEvent.click(screen.getByRole('button', { name: `lang-${code}` }));
    expect(screen.getByLabelText('probe').textContent?.startsWith(`${code}:`)).toBe(true);
    expect(screen.queryByRole('button', { name: 'lang-pl' })).toBeNull();
    expect(localStorage.getItem('locale')).toBe(code);
  });

  it('closes on Escape and on a tap outside', () => {
    renderSwitcher();
    const open = () => fireEvent.click(screen.getByRole('button', { name: 'language-switch' }));
    open();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('group', { name: 'language-list' })).toBeNull();
    open();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('group', { name: 'language-list' })).toBeNull();
  });
});

describe('the first language (V2-7)', () => {
  beforeEach(() => {
    localStorage.clear();
    delete window.Telegram;
  });

  const withTelegram = (code: string | undefined) => {
    window.Telegram = { WebApp: { initDataUnsafe: { user: { id: 1, language_code: code } } } } as unknown as typeof window.Telegram;
  };

  it.each([['uk', 'uk'], ['en', 'en'], ['en-GB', 'en'], ['ru', 'ru'], ['de', 'pl'], ['pl', 'pl'], [undefined, 'pl']])(
    'Telegram language %s → %s',
    (code, expected) => {
      withTelegram(code as string | undefined);
      renderSwitcher();
      expect(screen.getByLabelText('probe').textContent?.startsWith(`${expected}:`)).toBe(true);
    },
  );

  it('the choice made by hand wins over the language of Telegram', () => {
    withTelegram('uk');
    localStorage.setItem('locale', 'en');
    renderSwitcher();
    expect(screen.getByLabelText('probe').textContent?.startsWith('en:')).toBe(true);
  });

  it('a stored language that does not exist falls back to the language of Telegram', () => {
    withTelegram('ru');
    localStorage.setItem('locale', 'de');
    renderSwitcher();
    expect(screen.getByLabelText('probe').textContent?.startsWith('ru:')).toBe(true);
  });
});
