import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ConnectionBanner } from './components/ConnectionBanner';
import { I18nProvider } from './hooks/useI18n';
import { reportNetworkFailure, reportNetworkSuccess, reportServedFromCache, resetConnectionForTests } from './offline/connection';

const view = () => render(<I18nProvider><ConnectionBanner /></I18nProvider>);

describe('ConnectionBanner (Stage 19B)', () => {
  beforeEach(() => {
    localStorage.clear();
    resetConnectionForTests();
  });

  it('shows nothing while all is well', () => {
    view();
    expect(screen.queryByLabelText('connection-banner')).toBeNull();
  });

  it('says there is no connection, and that the server-only parts wait', () => {
    view();
    act(() => reportNetworkFailure());
    expect(screen.getByLabelText('connection-banner')).toHaveTextContent('Brak połączenia. To, co wymaga serwera, jest chwilowo niedostępne.');
  });

  it('says the data is from the phone, with the time of the copy', () => {
    view();
    act(() => {
      reportNetworkFailure();
      reportServedFromCache(new Date(2026, 9, 15, 14, 30).getTime());
    });
    expect(screen.getByLabelText('connection-banner')).toHaveTextContent(/Brak połączenia — pokazuję dane zapisane na telefonie \(z 15\.10.*14:30\)\./);
  });

  it('after the signal returns but while a copy is still on the screen, asks to refresh; then goes away', () => {
    view();
    act(() => reportServedFromCache(new Date(2026, 9, 15, 14, 30).getTime()));
    expect(screen.getByLabelText('connection-banner')).toHaveTextContent('Odśwież ekran');
    act(() => reportNetworkSuccess());
    expect(screen.queryByLabelText('connection-banner')).toBeNull();
  });

  it('speaks Russian and wraps (a status strip, not a scrolling line)', () => {
    localStorage.setItem('locale', 'ru');
    view();
    act(() => reportNetworkFailure());
    const banner = screen.getByLabelText('connection-banner');
    expect(banner).toHaveTextContent('Нет связи');
    expect(banner.className).toContain('break-words');
    expect(banner).toHaveAttribute('role', 'status');
  });
});
