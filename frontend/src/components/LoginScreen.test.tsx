import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PasswordLoginError } from '../api/auth';
import { I18nProvider } from '../hooks/useI18n';
import { LoginScreen } from './LoginScreen';

function view(onSubmit: (email: string, password: string) => Promise<void> = vi.fn(async () => undefined)) {
  render(<I18nProvider><LoginScreen onSubmit={onSubmit} /></I18nProvider>);
  return onSubmit as ReturnType<typeof vi.fn>;
}
const fill = (email: string, password: string) => {
  fireEvent.change(screen.getByLabelText('login-email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('login-password'), { target: { value: password } });
};

describe('LoginScreen (V2-1)', () => {
  beforeEach(() => localStorage.clear());

  it('asks for an e-mail and a password with mobile keyboards and 44 px controls; the button waits for both', () => {
    view();
    const email = screen.getByLabelText('login-email');
    expect(email).toHaveAttribute('type', 'email');
    expect(email).toHaveAttribute('autocomplete', 'username');
    expect(screen.getByLabelText('login-password')).toHaveAttribute('autocomplete', 'current-password');
    for (const label of ['login-email', 'login-password', 'login-password-toggle', 'login-submit']) {
      expect(screen.getByLabelText(label).className).toContain('min-h-11');
    }
    expect(screen.getByLabelText('login-submit')).toBeDisabled();
    fill('jan@example.pl', 'a long password');
    expect(screen.getByLabelText('login-submit')).toBeEnabled();
  });

  it('shows and hides the password', () => {
    view();
    const toggle = screen.getByLabelText('login-password-toggle');
    expect(screen.getByLabelText('login-password')).toHaveAttribute('type', 'password');
    fireEvent.click(toggle);
    expect(screen.getByLabelText('login-password')).toHaveAttribute('type', 'text');
    fireEvent.click(toggle);
    expect(screen.getByLabelText('login-password')).toHaveAttribute('type', 'password');
  });

  it('sends the e-mail without the spaces around it and the password as typed', async () => {
    const onSubmit = view();
    fill('  jan@example.pl ', ' pass with spaces ');
    fireEvent.click(screen.getByLabelText('login-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('jan@example.pl', ' pass with spaces '));
  });

  it.each([
    ['INVALID_CREDENTIALS', 401, null, 'Błędny e-mail lub hasło.'],
    ['ACCOUNT_LOCKED', 429, 840, 'Zbyt wiele prób. Spróbuj ponownie za 14 min.'],
    ['PASSWORD_LOGIN_DISABLED', 403, null, 'Logowanie hasłem jest wyłączone.'],
    ['ACCESS_BLOCKED', 403, null, 'zablokowany'],
    [null, 0, null, 'Serwer jest niedostępny'],
    [null, 500, null, 'Serwer jest niedostępny'],
  ])('tells a refusal %s in words and clears the password', async (code, status, retry, expected) => {
    const onSubmit = vi.fn(async (): Promise<void> => {
      throw new PasswordLoginError(code, status, retry);
    });
    view(onSubmit);
    fill('jan@example.pl', 'wrong password');
    fireEvent.click(screen.getByLabelText('login-submit'));
    expect(await screen.findByLabelText('login-error')).toHaveTextContent(expected);
    expect(screen.getByLabelText('login-password')).toHaveValue('');
    expect(screen.getByLabelText('login-email')).toHaveValue('jan@example.pl');
  });

  it('speaks Russian', async () => {
    localStorage.setItem('locale', 'ru');
    const onSubmit = vi.fn(async (): Promise<void> => {
      throw new PasswordLoginError('INVALID_CREDENTIALS', 401);
    });
    view(onSubmit);
    expect(screen.getByLabelText('login-submit')).toHaveTextContent('Войти');
    fill('jan@example.pl', 'wrong password');
    fireEvent.click(screen.getByLabelText('login-submit'));
    expect(await screen.findByLabelText('login-error')).toHaveTextContent('Неверный e-mail или пароль.');
  });
});
