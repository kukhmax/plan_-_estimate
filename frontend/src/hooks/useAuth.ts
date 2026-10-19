import { useEffect, useState, useCallback } from 'react';
import { User } from '../types/auth';
import { setOfflineOwner } from '../offline/readCache';
import { restorePhotoQueue } from './usePhotoUploadQueue';
import { loginWithTelegram, TelegramAuthRequestError } from '../api/auth';
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
  });

  const authenticate = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null, accessContact: null }));

    try {
      let authenticationData = initData;
      const isDevelopmentMockEnabled =
        import.meta.env.DEV && import.meta.env.VITE_DEV_MOCK_AUTH === 'true';

      if (!authenticationData && isDevelopmentMockEnabled) {
        authenticationData = 'mock';
      }

      if (!authenticationData) {
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
      });
    };
    window.addEventListener(ACCESS_LOST_EVENT, onLost);
    return () => window.removeEventListener(ACCESS_LOST_EVENT, onLost);
  }, []);

  return {
    ...state,
    retry: authenticate,
  };
}
