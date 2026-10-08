import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { AccountModal } from './AccountModal';

vi.mock('../api/executorProfile', async () => {
  const actual = await vi.importActual<typeof import('../api/executorProfile')>('../api/executorProfile');
  return { ...actual, fetchExecutorProfile: vi.fn().mockResolvedValue(null), saveExecutorProfile: vi.fn() };
});

const USER = {
  id: '11111111-1111-1111-1111-111111111111', telegram_user_id: 1, username: 'u', first_name: 'Jan', last_name: 'K',
  language_code: 'pl', created_at: '2026-10-08T10:00:00Z', updated_at: '2026-10-08T10:00:00Z',
};

describe('AccountModal — Telegram BackButton (Stage 15C)', () => {
  let press: () => void = () => undefined;
  const backButton = {
    isVisible: false,
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn((handler: () => void) => { press = handler; }),
    offClick: vi.fn(),
  };

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    window.Telegram = {
      WebApp: {
        initData: '', initDataUnsafe: {}, version: '8.0', platform: 'web', colorScheme: 'light', themeParams: {},
        isExpanded: false, viewportHeight: 800, viewportStableHeight: 800, ready: vi.fn(), expand: vi.fn(), close: vi.fn(),
        BackButton: backButton,
      },
    };
  });
  afterEach(() => { delete window.Telegram; });

  it('BackButton closes the profile first and the dialog second', async () => {
    const onClose = vi.fn();
    render(<I18nProvider><AccountModal user={USER} isDevAuth={false} onClose={onClose} /></I18nProvider>);
    expect(backButton.show).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Profil wykonawcy' }));
    await screen.findByRole('dialog', { name: 'Profil wykonawcy' });
    act(() => press());
    expect(screen.queryByRole('dialog', { name: 'Profil wykonawcy' })).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    act(() => press());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('a click inside the profile screen does not close the account dialog', async () => {
    const onClose = vi.fn();
    render(<I18nProvider><AccountModal user={USER} isDevAuth={false} onClose={onClose} /></I18nProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Profil wykonawcy' }));
    fireEvent.click(await screen.findByLabelText('NIP'));
    fireEvent.click(screen.getByRole('dialog', { name: 'Profil wykonawcy' }));
    expect(onClose).not.toHaveBeenCalled();
  });
});
