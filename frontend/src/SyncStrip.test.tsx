import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SyncStrip } from './components/SyncStrip';
import { I18nProvider } from './hooks/useI18n';
import { resetSyncStateForTests, setOutboxCounts, setSyncInfo } from './offline/outboxState';

const view = () => render(<I18nProvider><SyncStrip /></I18nProvider>);

describe('SyncStrip (Stage 19C)', () => {
  beforeEach(() => {
    localStorage.clear();
    resetSyncStateForTests();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows nothing while nothing waits', () => {
    view();
    expect(screen.queryByLabelText('sync-strip')?.children.length ?? 0).toBe(0);
  });

  it('says how many changes wait, and that they are being sent', () => {
    view();
    act(() => setOutboxCounts({ pending: 3, failed: 0 }));
    expect(screen.getByLabelText('sync-pending')).toHaveTextContent('Zmiany czekające na wysłanie: 3.');
    act(() => setSyncInfo({ running: true }));
    expect(screen.getByLabelText('sync-pending')).toHaveTextContent('Wysyłam zmiany z telefonu…');
  });

  it('says what the server refused, as an alert', () => {
    view();
    act(() => setOutboxCounts({ pending: 0, failed: 2 }));
    expect(screen.getByLabelText('sync-failed')).toHaveTextContent('Serwer odrzucił zmiany: 2. Wymagają uwagi.');
    expect(screen.getByLabelText('sync-failed')).toHaveAttribute('role', 'alert');
  });

  it('says the owner has to sign in again', () => {
    view();
    act(() => setSyncInfo({ needsLogin: true }));
    expect(screen.getByLabelText('sync-login')).toHaveTextContent('Zaloguj się ponownie');
  });

  it('after the sending shows the count and a button that reloads, for a minute', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    const reload = vi.fn();
    Object.defineProperty(window, 'location', { configurable: true, value: { ...window.location, reload } });
    view();
    act(() => setSyncInfo({ lastSent: { at: Date.now(), count: 4 } }));
    expect(screen.getByLabelText('sync-sent')).toHaveTextContent('Wysłano zmian: 4.');

    fireEvent.click(screen.getByLabelText('sync-refresh'));
    expect(reload).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(61_000);
    });
    expect(screen.queryByLabelText('sync-sent')).toBeNull();
  });

  it('does not say "sent" while other changes still wait', () => {
    view();
    act(() => {
      setSyncInfo({ lastSent: { at: Date.now(), count: 1 } });
      setOutboxCounts({ pending: 2, failed: 0 });
    });
    expect(screen.queryByLabelText('sync-sent')).toBeNull();
    expect(screen.getByLabelText('sync-pending')).toBeInTheDocument();
  });

  it('speaks Russian, and its lines wrap', () => {
    localStorage.setItem('locale', 'ru');
    view();
    act(() => setOutboxCounts({ pending: 1, failed: 1 }));
    expect(screen.getByLabelText('sync-pending')).toHaveTextContent('Изменения, ожидающие отправки: 1.');
    expect(screen.getByLabelText('sync-failed')).toHaveTextContent('Сервер отклонил изменений: 1.');
    expect(screen.getByLabelText('sync-pending').className).toContain('break-words');
  });
});
