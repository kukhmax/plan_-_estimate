import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SyncStrip } from './components/SyncStrip';
import { I18nProvider } from './hooks/useI18n';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './hooks/usePhotoUploadQueue';
import { reportNetworkFailure, resetConnectionForTests } from './offline/connection';
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

describe('SyncStrip: the way to the screen of what waits, and the photos (Stage 19E)', () => {
  beforeEach(() => {
    localStorage.clear();
    resetSyncStateForTests();
    resetConnectionForTests();
    resetPhotoUploadQueue();
  });
  afterEach(() => resetPhotoUploadQueue());

  const open = vi.fn();
  const viewWithOpen = () => render(<I18nProvider><SyncStrip onOpen={open} /></I18nProvider>);

  it('has no "Szczegóły" while nothing waits, and has it as soon as something does', () => {
    viewWithOpen();
    expect(screen.queryByLabelText('sync-open')).toBeNull();
    act(() => setOutboxCounts({ pending: 1, failed: 0 }));
    fireEvent.click(screen.getByLabelText('sync-open'));
    expect(open).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('sync-open')).toHaveTextContent('Szczegóły');
    expect(screen.getByLabelText('sync-open').className).toMatch(/min-h-11/);
  });

  it('also for a refused change alone', () => {
    viewWithOpen();
    act(() => setOutboxCounts({ pending: 0, failed: 1 }));
    expect(screen.getByLabelText('sync-open')).toBeInTheDocument();
  });

  it('counts the photos that wait on the phone, and offers the way to them', () => {
    reportNetworkFailure();
    viewWithOpen();
    act(() => {
      getPhotoUploadQueue().enqueue([new File(['x'], 'a.jpg', { type: 'image/jpeg' }), new File(['x'], 'b.jpg', { type: 'image/jpeg' })], { projectId: 'p', context: 'SURFACE', surfaceId: 's' }, 'GALLERY');
    });
    expect(screen.getByLabelText('sync-photos')).toHaveTextContent('Zdjęcia czekające na wysłanie: 2.');
    expect(screen.getByLabelText('sync-open')).toBeInTheDocument();
  });

  it('offers no way in just to say "sent" or "sign in again": there is nothing to look at then', () => {
    viewWithOpen();
    act(() => setSyncInfo({ lastSent: { at: Date.now(), count: 2 }, needsLogin: true }));
    expect(screen.getByLabelText('sync-sent')).toBeInTheDocument();
    expect(screen.queryByLabelText('sync-open')).toBeNull();
  });

  it('without a way to open it (the old use) draws no button', () => {
    view();
    act(() => setOutboxCounts({ pending: 2, failed: 0 }));
    expect(screen.queryByLabelText('sync-open')).toBeNull();
  });
});
