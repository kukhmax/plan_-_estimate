import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { AccountModal } from './AccountModal';

vi.mock('../api/executorProfile', async () => {
  const actual = await vi.importActual<typeof import('../api/executorProfile')>('../api/executorProfile');
  return { ...actual, fetchExecutorProfile: vi.fn().mockResolvedValue(null), saveExecutorProfile: vi.fn() };
});

const base = {
  id: '11111111-1111-1111-1111-111111111111', username: 'jan@example.pl', first_name: 'Jan', last_name: null,
  language_code: null, created_at: '2026-10-23T10:00:00Z', updated_at: '2026-10-23T10:00:00Z',
};

describe('AccountModal for an account that signs in with a password (V2-1)', () => {
  beforeEach(() => localStorage.clear());

  it('shows the e-mail, not a Telegram id, and a sign-out button of 44 px', () => {
    const onSignOut = vi.fn();
    render(<I18nProvider><AccountModal user={{ ...base, telegram_user_id: -1 }} isDevAuth={false} onClose={() => undefined} onSignOut={onSignOut} /></I18nProvider>);
    expect(screen.getByLabelText('account-email')).toHaveTextContent('jan@example.pl');
    expect(screen.getByText('Konto z hasłem')).toBeInTheDocument();
    expect(screen.queryByText('Telegram User ID')).toBeNull();
    const button = screen.getByLabelText('account-sign-out');
    expect(button.className).toContain('min-h-11');
    fireEvent.click(button);
    expect(onSignOut).toHaveBeenCalled();
  });

  it('is unchanged for a Telegram account: its id, no sign-out', () => {
    render(<I18nProvider><AccountModal user={{ ...base, telegram_user_id: 123456 }} isDevAuth={false} onClose={() => undefined} onSignOut={vi.fn()} /></I18nProvider>);
    expect(screen.getByText('Telegram User ID')).toBeInTheDocument();
    expect(screen.getByText('Telegram zweryfikowany')).toBeInTheDocument();
    expect(screen.queryByLabelText('account-sign-out')).toBeNull();
    expect(screen.queryByLabelText('account-email')).toBeNull();
  });
});
