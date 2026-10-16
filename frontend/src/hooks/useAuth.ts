import { useEffect, useState, useCallback } from 'react';
import { User } from '../types/auth';
import { setOfflineOwner } from '../offline/readCache';
import { restorePhotoQueue } from './usePhotoUploadQueue';
import { loginWithTelegram, TelegramAuthRequestError } from '../api/auth';
import { useTelegramWebApp } from './useTelegramWebApp';

export type AuthErrorCode =
  | 'telegram_unavailable'
  | 'telegram_init_data_missing'
  | 'telegram_signature_invalid'
  | 'telegram_auth_expired'
  | 'backend_unavailable'
  | 'request_failed';

interface AuthState {
  user: User | null;
  token: string | null;
  isDevAuth: boolean;
  isLoading: boolean;
  error: AuthErrorCode | null;
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
  });

  const authenticate = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

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
      });
    } catch (err: unknown) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getAuthErrorCode(err),
      }));
    }
  }, [initData, isAvailable]);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  return {
    ...state,
    retry: authenticate,
  };
}
