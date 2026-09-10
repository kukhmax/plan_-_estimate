import { useEffect, useRef, useState } from 'react';
import {
  TelegramBackButton,
  TelegramThemeParams,
  TelegramWebApp,
} from '../types/telegram';

export const DEFAULT_LIGHT_THEME: Record<string, string> = {
  '--tg-theme-bg-color': '#f8fafc',
  '--tg-theme-secondary-bg-color': '#ffffff',
  '--tg-theme-text-color': '#0f172a',
  '--tg-theme-hint-color': '#64748b',
  '--tg-theme-link-color': '#2563eb',
  '--tg-theme-button-color': '#0f172a',
  '--tg-theme-button-text-color': '#ffffff',
  '--tg-theme-header-bg-color': '#f8fafc',
  '--tg-theme-accent-text-color': '#2563eb',
  '--tg-theme-section-bg-color': '#ffffff',
  '--tg-theme-section-header-text-color': '#64748b',
  '--tg-theme-subtitle-text-color': '#64748b',
  '--tg-theme-destructive-text-color': '#dc2626',
};

export const DEFAULT_DARK_THEME: Record<string, string> = {
  '--tg-theme-bg-color': '#17212b',
  '--tg-theme-secondary-bg-color': '#232e3c',
  '--tg-theme-text-color': '#f5f5f5',
  '--tg-theme-hint-color': '#708499',
  '--tg-theme-link-color': '#6ab2f2',
  '--tg-theme-button-color': '#5288c1',
  '--tg-theme-button-text-color': '#ffffff',
  '--tg-theme-header-bg-color': '#17212b',
  '--tg-theme-accent-text-color': '#6ab2f2',
  '--tg-theme-section-bg-color': '#232e3c',
  '--tg-theme-section-header-text-color': '#708499',
  '--tg-theme-subtitle-text-color': '#708499',
  '--tg-theme-destructive-text-color': '#ef5350',
};

export function applyTelegramTheme(
  themeParams?: TelegramThemeParams,
  colorScheme?: 'light' | 'dark',
  viewport?: { viewportHeight?: number; viewportStableHeight?: number }
): void {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  const isDark = colorScheme === 'dark';
  const defaults = isDark ? DEFAULT_DARK_THEME : DEFAULT_LIGHT_THEME;

  root.setAttribute('data-color-scheme', colorScheme ?? 'light');

  const themeMap: Record<string, string | undefined> = {
    '--tg-theme-bg-color': themeParams?.bg_color,
    '--tg-theme-secondary-bg-color': themeParams?.secondary_bg_color,
    '--tg-theme-text-color': themeParams?.text_color,
    '--tg-theme-hint-color': themeParams?.hint_color,
    '--tg-theme-link-color': themeParams?.link_color,
    '--tg-theme-button-color': themeParams?.button_color,
    '--tg-theme-button-text-color': themeParams?.button_text_color,
    '--tg-theme-header-bg-color': themeParams?.header_bg_color,
    '--tg-theme-accent-text-color': themeParams?.accent_text_color,
    '--tg-theme-section-bg-color': themeParams?.section_bg_color,
    '--tg-theme-section-header-text-color': themeParams?.section_header_text_color,
    '--tg-theme-subtitle-text-color': themeParams?.subtitle_text_color,
    '--tg-theme-destructive-text-color': themeParams?.destructive_text_color,
  };

  for (const [prop, fallback] of Object.entries(defaults)) {
    const value = themeMap[prop] || fallback;
    root.style.setProperty(prop, value);
  }

  if (typeof viewport?.viewportHeight === 'number' && viewport.viewportHeight > 0) {
    root.style.setProperty('--tg-viewport-height', `${viewport.viewportHeight}px`);
  } else {
    root.style.setProperty('--tg-viewport-height', '100vh');
  }

  if (typeof viewport?.viewportStableHeight === 'number' && viewport.viewportStableHeight > 0) {
    root.style.setProperty('--tg-viewport-stable-height', `${viewport.viewportStableHeight}px`);
  } else {
    root.style.setProperty('--tg-viewport-stable-height', '100vh');
  }
}

export interface TelegramWebAppState {
  isAvailable: boolean;
  initData: string;
  colorScheme: 'light' | 'dark';
  themeParams: TelegramThemeParams;
  viewportHeight: number;
  viewportStableHeight: number;
  isExpanded: boolean;
}

export function useTelegramWebApp(): TelegramWebAppState {
  const webApp: TelegramWebApp | undefined = window.Telegram?.WebApp;

  const [themeState, setThemeState] = useState<{
    colorScheme: 'light' | 'dark';
    themeParams: TelegramThemeParams;
  }>(() => ({
    colorScheme: webApp?.colorScheme ?? 'light',
    themeParams: webApp?.themeParams ?? {},
  }));

  const [viewportState, setViewportState] = useState<{
    viewportHeight: number;
    viewportStableHeight: number;
    isExpanded: boolean;
  }>(() => ({
    viewportHeight: webApp?.viewportHeight ?? 0,
    viewportStableHeight: webApp?.viewportStableHeight ?? 0,
    isExpanded: webApp?.isExpanded ?? false,
  }));

  useEffect(() => {
    if (!webApp) {
      applyTelegramTheme(undefined, 'light');
      return;
    }

    webApp.ready();
    webApp.expand();

    applyTelegramTheme(webApp.themeParams, webApp.colorScheme, {
      viewportHeight: webApp.viewportHeight,
      viewportStableHeight: webApp.viewportStableHeight,
    });

    const handleThemeChange = () => {
      const newColorScheme = webApp.colorScheme ?? 'light';
      const newThemeParams = webApp.themeParams ?? {};
      setThemeState({
        colorScheme: newColorScheme,
        themeParams: newThemeParams,
      });
      applyTelegramTheme(newThemeParams, newColorScheme, {
        viewportHeight: webApp.viewportHeight,
        viewportStableHeight: webApp.viewportStableHeight,
      });
    };

    const handleViewportChange = () => {
      const newHeight = webApp.viewportHeight ?? 0;
      const newStableHeight = webApp.viewportStableHeight ?? 0;
      const newIsExpanded = webApp.isExpanded ?? false;
      setViewportState({
        viewportHeight: newHeight,
        viewportStableHeight: newStableHeight,
        isExpanded: newIsExpanded,
      });
      applyTelegramTheme(webApp.themeParams, webApp.colorScheme, {
        viewportHeight: newHeight,
        viewportStableHeight: newStableHeight,
      });
    };

    webApp.onEvent?.('themeChanged', handleThemeChange);
    webApp.onEvent?.('viewportChanged', handleViewportChange);

    return () => {
      webApp.offEvent?.('themeChanged', handleThemeChange);
      webApp.offEvent?.('viewportChanged', handleViewportChange);
    };
  }, [webApp]);

  return {
    isAvailable: webApp !== undefined,
    initData: webApp?.initData ?? '',
    colorScheme: themeState.colorScheme,
    themeParams: themeState.themeParams,
    viewportHeight: viewportState.viewportHeight,
    viewportStableHeight: viewportState.viewportStableHeight,
    isExpanded: viewportState.isExpanded,
  };
}

export function useTelegramBackButton(visible: boolean, onBack?: () => void): void {
  const onBackRef = useRef(onBack);

  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  useEffect(() => {
    const webApp: TelegramWebApp | undefined = window.Telegram?.WebApp;
    const backButton: TelegramBackButton | undefined = webApp?.BackButton;
    if (!backButton) return;

    if (!visible || !onBack) {
      backButton.hide?.();
      return;
    }

    const handleClick = () => {
      onBackRef.current?.();
    };

    backButton.show?.();
    backButton.onClick?.(handleClick);

    return () => {
      backButton.offClick?.(handleClick);
      backButton.hide?.();
    };
  }, [visible, Boolean(onBack)]);
}