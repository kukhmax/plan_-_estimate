import { useEffect } from 'react';
import { TelegramWebApp } from '../types/telegram';

interface TelegramWebAppState {
  isAvailable: boolean;
  initData: string;
}

export function useTelegramWebApp(): TelegramWebAppState {
  const webApp: TelegramWebApp | undefined = window.Telegram?.WebApp;

  useEffect(() => {
    if (!webApp) return;
    webApp.ready();
    webApp.expand();
  }, [webApp]);

  return {
    isAvailable: webApp !== undefined,
    initData: webApp?.initData ?? '',
  };
}
