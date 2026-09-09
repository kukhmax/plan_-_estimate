import { useEffect, useState, useCallback } from 'react';
import { User } from '../types/auth';
import { loginWithTelegram } from '../api/auth';
import { useTelegramWebApp } from './useTelegramWebApp';

interface AuthState {
  user: User | null;
  token: string | null;
  isDevAuth: boolean;
  isLoading: boolean;
  error: string | null;
}

export function useAuth() {
  const { initData } = useTelegramWebApp();
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

      // Development fallback when running outside Telegram Mini App client
      if (!authenticationData && (import.meta.env.DEV || import.meta.env.VITE_DEV_MOCK_AUTH === 'true')) {
        authenticationData = 'mock';
      }

      if (!authenticationData) {
        throw new Error('Telegram Mini App initData is not available. Please open inside Telegram.');
      }

      const response = await loginWithTelegram(authenticationData);
      localStorage.setItem('access_token', response.access_token);

      setState({
        user: response.user,
        token: response.access_token,
        isDevAuth: response.is_dev_auth,
        isLoading: false,
        error: null,
      });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown authentication error';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
    }
  }, [initData]);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  return {
    ...state,
    retry: authenticate,
  };
}
