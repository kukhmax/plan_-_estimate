import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as authApi from '../api/auth';
import { useAuth } from './useAuth';

vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth');
  return { ...actual, fetchAuthConfig: vi.fn(), fetchCurrentUser: vi.fn(), loginWithPassword: vi.fn(), loginWithTelegram: vi.fn() };
});
let telegram = { isAvailable: false, initData: '' };
vi.mock('./useTelegramWebApp', () => ({ useTelegramWebApp: () => telegram }));
vi.mock('./usePhotoStorage', () => ({ refreshPhotoStorage: vi.fn() }));
vi.mock('../offline/readCache', async () => {
  const actual = await vi.importActual<typeof import('../offline/readCache')>('../offline/readCache');
  return { ...actual, setOfflineOwner: vi.fn(async () => undefined) };
});

const USER = { id: 'web-1', telegram_user_id: -1, username: 'jan@example.pl', first_name: 'Jan', last_name: null, language_code: null, created_at: '', updated_at: '' };

describe('signing in without Telegram (V2-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    telegram = { isAvailable: false, initData: '' };
    vi.mocked(authApi.fetchAuthConfig).mockResolvedValue({ password_login: true });
  });

  it('outside Telegram, with the sign-in by password on, asks for the e-mail and the password', async () => {
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loginRequired).toBe(true);
    expect(result.current.user).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('with the sign-in by password off, the old message stays', async () => {
    vi.mocked(authApi.fetchAuthConfig).mockResolvedValue({ password_login: false });
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loginRequired).toBe(false);
    expect(result.current.error).toBe('telegram_unavailable');
  });

  it('inside Telegram the server is not even asked and nothing changes', async () => {
    telegram = { isAvailable: true, initData: '' };
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(authApi.fetchAuthConfig).not.toHaveBeenCalled();
    expect(result.current.error).toBe('telegram_init_data_missing');
  });

  it('signs in, keeps the token, and the answer of the server is the user', async () => {
    vi.mocked(authApi.loginWithPassword).mockResolvedValue({ access_token: 'tok', token_type: 'bearer', user: USER, is_dev_auth: false });
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.loginRequired).toBe(true));
    await act(async () => {
      await result.current.signInWithPassword('jan@example.pl', 'a long password');
    });
    expect(authApi.loginWithPassword).toHaveBeenCalledWith('jan@example.pl', 'a long password');
    expect(localStorage.getItem('access_token')).toBe('tok');
    expect(result.current.user?.id).toBe('web-1');
    expect(result.current.loginRequired).toBe(false);
  });

  it('a refusal is thrown to the screen and nothing is kept', async () => {
    vi.mocked(authApi.loginWithPassword).mockRejectedValue(new authApi.PasswordLoginError('INVALID_CREDENTIALS', 401));
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.loginRequired).toBe(true));
    await expect(result.current.signInWithPassword('jan@example.pl', 'wrong')).rejects.toBeInstanceOf(authApi.PasswordLoginError);
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it('a session kept from the last time opens the application without asking again', async () => {
    localStorage.setItem('access_token', 'kept');
    vi.mocked(authApi.fetchCurrentUser).mockResolvedValue(USER);
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.user?.id).toBe('web-1'));
    expect(authApi.fetchCurrentUser).toHaveBeenCalledWith('kept');
    expect(result.current.loginRequired).toBe(false);
  });

  it('a session that is no longer good is dropped and the sign-in is asked for', async () => {
    localStorage.setItem('access_token', 'old');
    vi.mocked(authApi.fetchCurrentUser).mockRejectedValue(new Error('401'));
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.loginRequired).toBe(true));
    expect(localStorage.getItem('access_token')).toBeNull();
  });
});
