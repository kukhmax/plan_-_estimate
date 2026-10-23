import { useEffect, useState, useCallback } from 'react';
import { User } from '../types/auth';
import { setOfflineOwner } from '../offline/readCache';
import { restorePhotoQueue } from './usePhotoUploadQueue';
import { fetchAuthConfig, fetchCurrentUser, loginWithPassword, loginWithTelegram, TelegramAuthRequestError } from '../api/auth';
import { ACCESS_LOST_EVENT } from '../api/http';
import { useTelegramWebApp } from './useTelegramWebApp';

export type AuthErrorCode =
  | 'telegram_unavailable'
  | 'telegram_init_data_missing'
  | 'telegram_signature_invalid'
  | 'telegram_auth_expired'
  | 'backend_unavailable'
  | 'access_denied'
  | 'access_blocked'
  | 'request_failed';

interface AuthState {
  user: User | null;
  token: string | null;
  isDevAuth: boolean;
  isLoading: boolean;
  error: AuthErrorCode | null;
  /** closed registration: the contact text for a refused person */
  accessContact: string | null;
  /** V2-1: opened outside Telegram and the sign-in by password is on: the screen of the e-mail and the password is shown */
  loginRequired: boolean;
}

class AuthFlowError extends Error {
  constructor(public readonly code: AuthErrorCode) {
    super(code);
  }
}

function getAuthErrorCode(error: unknown): AuthErrorCode {
  if (error instanceof AuthFlowError) return error.code;

  if (error instanceof TelegramAuthRequestError) {
    if (error.code === 'INVALID_TELEGRAM_SIGNATURE') return 'telegram_signature_invalid';
    if (error.code === 'TELEGRAM_AUTH_EXPIRED') return 'telegram_auth_expired';
    if (error.code === 'MISSING_TELEGRAM_DATA') return 'telegram_init_data_missing';
    if (error.code === 'ACCESS_DENIED') return 'access_denied';
    if (error.code === 'ACCESS_BLOCKED') return 'access_blocked';
    if (error.status === 0 || error.status >= 500) return 'backend_unavailable';
  }

  return 'request_failed';
}

export function useAuth() {
  const { isAvailable, initData } = useTelegramWebApp();
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isDevAuth: false,
    isLoading: true,
    error: null,
    accessContact: null,
    loginRequired: false,
  });

  const authenticate = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null, accessContact: null, loginRequired: false }));

    try {
      let authenticationData = initData;
      const isDevelopmentMockEnabled =
        import.meta.env.DEV && import.meta.env.VITE_DEV_MOCK_AUTH === 'true';

      if (!authenticationData && isDevelopmentMockEnabled) {
        authenticationData = 'mock';
      }

      if (!authenticationData) {
        // V2-1: outside Telegram an account with a password may sign in; a session kept from the last time is tried first
        const kept = localStorage.getItem('access_token');
        if (kept) {
          try {
            const profile = await fetchCurrentUser(kept);
            await setOfflineOwner(profile.id);
            void restorePhotoQueue();
            setState({ user: profile, token: kept, isDevAuth: false, isLoading: false, error: null, accessContact: null, loginRequired: false });
            return;
          } catch {
            localStorage.removeItem('access_token'); // expired, blocked or not an account of this kind: the screen of the sign-in decides below
          }
        }
        if (!isAvailable && (await fetchAuthConfig()).password_login) {
          setState({ user: null, token: null, isDevAuth: false, isLoading: false, error: null, accessContact: null, loginRequired: true });
          return;
        }
        throw new AuthFlowError(
          isAvailable ? 'telegram_init_data_missing' : 'telegram_unavailable',
        );
      }

      const response = await loginWithTelegram(authenticationData);
      localStorage.setItem('access_token', response.access_token);
      // the copies kept for work without a signal belong to this owner (another owner's are removed first)
      await setOfflineOwner(response.user.id);
      void restorePhotoQueue(); // Stage 19D: the photos kept on the phone go on being sent

      setState({
        user: response.user,
        token: response.access_token,
        isDevAuth: response.is_dev_auth,
        isLoading: false,
        error: null,
        accessContact: null,
        loginRequired: false,
      });
    } catch (err: unknown) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getAuthErrorCode(err),
        accessContact: err instanceof TelegramAuthRequestError ? err.contact : null,
      }));
    }
  }, [initData, isAvailable]);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  // Closed registration: a request made with the token was refused (the administrator blocked this account or closed the registration)
  useEffect(() => {
    const onLost = (event: Event) => {
      const { code, contact } = (event as CustomEvent<{ code: string; contact: string }>).detail;
      localStorage.removeItem('access_token');
      setState({
        user: null,
        token: null,
        isDevAuth: false,
        isLoading: false,
        error: code === 'ACCESS_BLOCKED' ? 'access_blocked' : 'access_denied',
        accessContact: contact || null,
        loginRequired: false,
      });
    };
    window.addEventListener(ACCESS_LOST_EVENT, onLost);
    return () => window.removeEventListener(ACCESS_LOST_EVENT, onLost);
  }, []);

  /** V2-1: the sign-in by password; a refusal is thrown to the screen of the sign-in. */
  const signInWithPassword = useCallback(async (email: string, password: string) => {
    const response = await loginWithPassword(email, password);
    localStorage.setItem('access_token', response.access_token);
    await setOfflineOwner(response.user.id);
    void restorePhotoQueue();
    setState({
      user: response.user,
      token: response.access_token,
      isDevAuth: false,
      isLoading: false,
      error: null,
      accessContact: null,
      loginRequired: false,
    });
  }, []);

  /** V2-1: leaves a session of the kind that has no Telegram to sign in again with; the screen starts again from the beginning. */
  const signOut = useCallback(() => {
    localStorage.removeItem('access_token');
    window.location.reload();
  }, []);

  return {
    ...state,
    retry: authenticate,
    signInWithPassword,
    signOut,
  };
}
