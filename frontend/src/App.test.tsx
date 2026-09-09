import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as api from './api/auth';

vi.mock('./api/auth', async () => {
  const actual = await vi.importActual<typeof import('./api/auth')>('./api/auth');
  return {
    ...actual,
    loginWithTelegram: vi.fn(),
    fetchCurrentUser: vi.fn(),
  };
});

// Mock clients API to prevent fetch errors in tests
vi.mock('./api/clients', () => ({
  fetchClients: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createClient: vi.fn(),
  archiveClient: vi.fn(),
  restoreClient: vi.fn(),
}));

describe('App authentication component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
    vi.stubEnv('DEV', true);
    vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');
    delete (window as any).Telegram;
    localStorage.clear();
  });

  it('displays DEV AUTH banner when in dev mock mode', async () => {
    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'mock-jwt-token',
      token_type: 'bearer',
      is_dev_auth: true,
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        telegram_user_id: 999999999,
        username: 'dev_contractor',
        first_name: 'Jan',
        last_name: 'Kowalski',
        language_code: 'pl',
        created_at: '2026-09-08T12:00:00Z',
        updated_at: '2026-09-08T12:00:00Z',
      },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert', { name: 'dev-auth-banner' })).toBeInTheDocument();
    });

    expect(screen.getByText(/DEV AUTH MODE/i)).toBeInTheDocument();
    expect(screen.getByText('Jan Kowalski')).toBeInTheDocument();
    expect(screen.getByText('@dev_contractor')).toBeInTheDocument();
    expect(screen.getByText('999999999')).toBeInTheDocument();
    expect(api.loginWithTelegram).toHaveBeenCalledWith('mock');
    expect(localStorage.getItem('access_token')).toBe('mock-jwt-token');
  });

  it('submits raw Telegram initData unchanged and stores the returned JWT', async () => {
    const ready = vi.fn();
    const expand = vi.fn();
    const initData = 'query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A12345678%7D&auth_date=1788991000&hash=valid%2Bhash';
    (window as any).Telegram = {
      WebApp: {
        initData,
        ready,
        expand,
      },
    };

    vi.mocked(api.loginWithTelegram).mockResolvedValueOnce({
      access_token: 'valid-jwt-token',
      token_type: 'bearer',
      is_dev_auth: false,
      user: {
        id: '22222222-2222-2222-2222-222222222222',
        telegram_user_id: 12345678,
        username: 'real_contractor',
        first_name: 'Adam',
        last_name: 'Nowak',
        language_code: 'pl',
        created_at: '2026-09-08T12:00:00Z',
        updated_at: '2026-09-08T12:00:00Z',
      },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Adam Nowak')).toBeInTheDocument();
    });

    expect(screen.queryByRole('alert', { name: 'dev-auth-banner' })).not.toBeInTheDocument();
    expect(screen.getByText('Telegram Verified')).toBeInTheDocument();
    expect(screen.getByText('@real_contractor')).toBeInTheDocument();
    expect(api.loginWithTelegram).toHaveBeenCalledWith(initData);
    expect(localStorage.getItem('access_token')).toBe('valid-jwt-token');
    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
  });

  it('reauthenticates with the same Telegram data after remount', async () => {
    const initData = 'query_id=reload&auth_date=1788991000&hash=valid';
    (window as any).Telegram = {
      WebApp: {
        initData,
        ready: vi.fn(),
        expand: vi.fn(),
      },
    };
    const authResponse = {
      access_token: 'first-jwt-token',
      token_type: 'bearer' as const,
      is_dev_auth: false,
      user: {
        id: '22222222-2222-2222-2222-222222222222',
        telegram_user_id: 12345678,
        username: 'real_contractor',
        first_name: 'Adam',
        last_name: 'Nowak',
        language_code: 'pl',
        created_at: '2026-09-10T00:00:00Z',
        updated_at: '2026-09-10T00:00:00Z',
      },
    };
    vi.mocked(api.loginWithTelegram)
      .mockResolvedValueOnce(authResponse)
      .mockResolvedValueOnce({ ...authResponse, access_token: 'second-jwt-token' });

    const firstRender = render(<App />);
    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBe('first-jwt-token');
    });
    firstRender.unmount();

    render(<App />);
    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBe('second-jwt-token');
    });
    expect(api.loginWithTelegram).toHaveBeenNthCalledWith(1, initData);
    expect(api.loginWithTelegram).toHaveBeenNthCalledWith(2, initData);
  });

  it('fails safely when Telegram is available without initData', async () => {
    vi.stubEnv('VITE_DEV_MOCK_AUTH', 'false');
    (window as any).Telegram = {
      WebApp: {
        initData: '',
        ready: vi.fn(),
        expand: vi.fn(),
      },
    };

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText('Telegram nie przekazał danych logowania. Zamknij i otwórz aplikację ponownie.'),
      ).toBeInTheDocument();
    });
    expect(api.loginWithTelegram).not.toHaveBeenCalled();
  });

  it('does not enable browser mock authentication outside development', async () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_DEV_MOCK_AUTH', 'true');

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText('Otwórz aplikację w Telegramie lub włącz jawnie tryb deweloperski.'),
      ).toBeInTheDocument();
    });
    expect(api.loginWithTelegram).not.toHaveBeenCalled();
  });

  it('localizes an invalid Telegram signature without exposing backend details', async () => {
    vi.mocked(api.loginWithTelegram).mockRejectedValueOnce(
      new api.TelegramAuthRequestError('INVALID_TELEGRAM_SIGNATURE', 401),
    );

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText('Nie udało się potwierdzić autentyczności danych Telegram.'),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/signature/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'lang-ru' }));
    expect(
      screen.getByText('Не удалось подтвердить подлинность данных Telegram.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /повторить/i })).toBeInTheDocument();
  });

  it.each([
    [
      new api.TelegramAuthRequestError('TELEGRAM_AUTH_EXPIRED', 401),
      'Dane logowania Telegram wygasły. Otwórz aplikację ponownie.',
    ],
    [
      new api.TelegramAuthRequestError(null, 503),
      'Serwer autoryzacji jest niedostępny. Spróbuj ponownie później.',
    ],
    [new Error('Unexpected response'), 'Nie udało się zalogować. Spróbuj ponownie.'],
  ])('displays a localized authentication failure for %s', async (failure, message) => {
    vi.mocked(api.loginWithTelegram).mockRejectedValueOnce(failure);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(message)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /ponów próbę/i })).toBeInTheDocument();
  });
});
