import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { User } from '../types/auth';
import { AccountModal } from './AccountModal';

const user = { id: 'u1', telegram_user_id: 42, username: 'owner', first_name: 'Max', last_name: null } as unknown as User;

function renderModal(onClose = vi.fn()) {
  render(
    <I18nProvider>
      <AccountModal user={user} isDevAuth={false} onClose={onClose} />
    </I18nProvider>,
  );
  return { onClose };
}

describe('AccountModal — camera diagnostics entry (Stage 14E.9 spike)', () => {
  beforeEach(() => localStorage.clear());

  it('opens the diagnostics screen from its own button', () => {
    renderModal();
    expect(screen.queryByRole('dialog', { name: 'Diagnostyka kamery' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostyka kamery' }));
    expect(screen.getByRole('dialog', { name: 'Diagnostyka kamery' })).toBeInTheDocument();
  });

  it('a tap inside the diagnostics screen does not close the account window', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostyka kamery' }));
    fireEvent.click(screen.getByTestId('camera-report'));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Diagnostyka kamery' })).toBeInTheDocument();
  });

  it('Escape closes only the diagnostics screen first, then the account window', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostyka kamery' }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Diagnostyka kamery' })).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('the screen closes through its own close button and leaves the account window open', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostyka kamery' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Diagnostyka kamery' })).getByRole('button', { name: 'Zamknij' }));
    expect(screen.queryByRole('dialog', { name: 'Diagnostyka kamery' })).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Dane użytkownika' })).toBeInTheDocument();
  });

  it('is available in Russian too', () => {
    localStorage.setItem('locale', 'ru');
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Диагностика камеры' }));
    expect(screen.getByRole('dialog', { name: 'Диагностика камеры' })).toBeInTheDocument();
  });
});
