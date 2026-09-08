import { useEffect, useState, useCallback } from 'react';
import { User } from '../types/auth';
import { loginWithTelegram } from '../api/auth';
import '../types/telegram';

interface AuthState {
  user: User | null;
  token: string | null;
  isDevAuth: boolean;
  isLoading: boolean;
  error: string | null;
}

export function useAuth() {
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
      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
      }

      let initData = tg?.initData || '';

      // Development fallback when running outside Telegram Mini App client
      if (!initData && (import.meta.env.DEV || import.meta.env.VITE_DEV_MOCK_AUTH === 'true')) {
        initData = 'mock';
      }

      if (!initData) {
        throw new Error('Telegram Mini App initData is not available. Please open inside Telegram.');
      }

      const response = await loginWithTelegram(initData);

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
  }, []);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  return {
    ...state,
    retry: authenticate,
  };
}
