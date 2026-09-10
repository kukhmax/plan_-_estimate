import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TelegramBackButton, TelegramWebApp } from '../types/telegram';
import { useTelegramBackButton, useTelegramWebApp } from './useTelegramWebApp';

describe('useTelegramWebApp', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.Telegram;
    document.documentElement.removeAttribute('style');
    document.documentElement.removeAttribute('data-color-scheme');
  });

  it('supports a browser without the Telegram WebApp runtime', () => {
    const { result } = renderHook(() => useTelegramWebApp());

    expect(result.current).toEqual({
      isAvailable: false,
      initData: '',
      colorScheme: 'light',
      themeParams: {},
      viewportHeight: 0,
      viewportStableHeight: 0,
      isExpanded: false,
    });
    expect(document.documentElement.style.getPropertyValue('--tg-theme-bg-color')).toBe('#f8fafc');
    expect(document.documentElement.style.getPropertyValue('--tg-theme-text-color')).toBe('#0f172a');
  });

  it('exposes initData and initializes the available Telegram WebApp', () => {
    const ready = vi.fn();
    const expand = vi.fn();
    const webApp: TelegramWebApp = {
      initData: 'query_id=123&hash=valid_hash',
      initDataUnsafe: {},
      version: '8.0',
      platform: 'web',
      colorScheme: 'light',
      themeParams: {},
      isExpanded: false,
      viewportHeight: 800,
      viewportStableHeight: 800,
      ready,
      expand,
      close: vi.fn(),
    };
    window.Telegram = { WebApp: webApp };

    const { result } = renderHook(() => useTelegramWebApp());

    expect(result.current).toEqual({
      isAvailable: true,
      initData: 'query_id=123&hash=valid_hash',
      colorScheme: 'light',
      themeParams: {},
      viewportHeight: 800,
      viewportStableHeight: 800,
      isExpanded: false,
    });
    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
    expect(document.documentElement.style.getPropertyValue('--tg-viewport-height')).toBe('800px');
  });

  it('applies Telegram theme parameters and falls back safely for missing ones', () => {
    const webApp: TelegramWebApp = {
      initData: '',
      initDataUnsafe: {},
      version: '8.0',
      platform: 'tdesktop',
      colorScheme: 'dark',
      themeParams: {
        bg_color: '#101010',
        text_color: '#f0f0f0',
      },
      isExpanded: true,
      viewportHeight: 900,
      viewportStableHeight: 900,
      ready: vi.fn(),
      expand: vi.fn(),
      close: vi.fn(),
    };
    window.Telegram = { WebApp: webApp };

    renderHook(() => useTelegramWebApp());

    expect(document.documentElement.style.getPropertyValue('--tg-theme-bg-color')).toBe('#101010');
    expect(document.documentElement.style.getPropertyValue('--tg-theme-text-color')).toBe('#f0f0f0');
    // Missing param falls back to dark default
    expect(document.documentElement.style.getPropertyValue('--tg-theme-secondary-bg-color')).toBe('#232e3c');
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('dark');
  });

  it('responds to themeChanged events and updates CSS custom properties without reload', () => {
    const listeners: Record<string, () => void> = {};
    const onEvent = vi.fn((event: string, handler: () => void) => {
      listeners[event] = handler;
    });
    const offEvent = vi.fn();

    const webApp: TelegramWebApp = {
      initData: '',
      initDataUnsafe: {},
      version: '8.0',
      platform: 'ios',
      colorScheme: 'light',
      themeParams: { bg_color: '#ffffff', text_color: '#000000' },
      isExpanded: true,
      viewportHeight: 600,
      viewportStableHeight: 600,
      ready: vi.fn(),
      expand: vi.fn(),
      close: vi.fn(),
      onEvent,
      offEvent,
    };
    window.Telegram = { WebApp: webApp };

    const { result } = renderHook(() => useTelegramWebApp());

    expect(onEvent).toHaveBeenCalledWith('themeChanged', expect.any(Function));
    expect(document.documentElement.style.getPropertyValue('--tg-theme-bg-color')).toBe('#ffffff');

    // Simulate themeChanged event
    webApp.colorScheme = 'dark';
    webApp.themeParams = { bg_color: '#202020', text_color: '#ffffff' };
    act(() => {
      listeners['themeChanged']?.();
    });

    expect(result.current.colorScheme).toBe('dark');
    expect(result.current.themeParams).toEqual({ bg_color: '#202020', text_color: '#ffffff' });
    expect(document.documentElement.style.getPropertyValue('--tg-theme-bg-color')).toBe('#202020');
    expect(document.documentElement.style.getPropertyValue('--tg-theme-text-color')).toBe('#ffffff');
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('dark');
  });

  it('responds to viewportChanged events and cleans up listeners on unmount', () => {
    const listeners: Record<string, () => void> = {};
    const onEvent = vi.fn((event: string, handler: () => void) => {
      listeners[event] = handler;
    });
    const offEvent = vi.fn();

    const webApp: TelegramWebApp = {
      initData: '',
      initDataUnsafe: {},
      version: '8.0',
      platform: 'android',
      colorScheme: 'light',
      themeParams: {},
      isExpanded: false,
      viewportHeight: 500,
      viewportStableHeight: 500,
      ready: vi.fn(),
      expand: vi.fn(),
      close: vi.fn(),
      onEvent,
      offEvent,
    };
    window.Telegram = { WebApp: webApp };

    const { result, unmount } = renderHook(() => useTelegramWebApp());

    expect(onEvent).toHaveBeenCalledWith('viewportChanged', expect.any(Function));

    // Simulate viewportChanged event
    webApp.viewportHeight = 750;
    webApp.viewportStableHeight = 750;
    webApp.isExpanded = true;
    act(() => {
      listeners['viewportChanged']?.();
    });

    expect(result.current.viewportHeight).toBe(750);
    expect(result.current.viewportStableHeight).toBe(750);
    expect(result.current.isExpanded).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--tg-viewport-height')).toBe('750px');

    unmount();

    expect(offEvent).toHaveBeenCalledWith('themeChanged', expect.any(Function));
    expect(offEvent).toHaveBeenCalledWith('viewportChanged', expect.any(Function));
  });
});

describe('useTelegramBackButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.Telegram;
  });

  it('supports a browser without Telegram WebApp runtime safely', () => {
    const onBack = vi.fn();
    expect(() => {
      renderHook(() => useTelegramBackButton(true, onBack));
    }).not.toThrow();
  });

  it('hides BackButton when visible is false', () => {
    const backButton: TelegramBackButton = {
      isVisible: true,
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
      offClick: vi.fn(),
    };
    window.Telegram = {
      WebApp: {
        initData: '',
        initDataUnsafe: {},
        version: '8.0',
        platform: 'web',
        colorScheme: 'light',
        themeParams: {},
        isExpanded: false,
        viewportHeight: 800,
        viewportStableHeight: 800,
        ready: vi.fn(),
        expand: vi.fn(),
        close: vi.fn(),
        BackButton: backButton,
      },
    };

    renderHook(() => useTelegramBackButton(false, vi.fn()));

    expect(backButton.hide).toHaveBeenCalledTimes(1);
    expect(backButton.show).not.toHaveBeenCalled();
    expect(backButton.onClick).not.toHaveBeenCalled();
  });

  it('shows BackButton, handles clicks, avoids duplicate registrations, and cleans up on unmount', () => {
    let clickHandler: (() => void) | undefined;
    const backButton: TelegramBackButton = {
      isVisible: false,
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb) => {
        clickHandler = cb;
      }),
      offClick: vi.fn(),
    };
    window.Telegram = {
      WebApp: {
        initData: '',
        initDataUnsafe: {},
        version: '8.0',
        platform: 'web',
        colorScheme: 'light',
        themeParams: {},
        isExpanded: false,
        viewportHeight: 800,
        viewportStableHeight: 800,
        ready: vi.fn(),
        expand: vi.fn(),
        close: vi.fn(),
        BackButton: backButton,
      },
    };

    const onBack1 = vi.fn();
    const onBack2 = vi.fn();

    const { rerender, unmount } = renderHook(
      ({ cb }) => useTelegramBackButton(true, cb),
      { initialProps: { cb: onBack1 } }
    );

    expect(backButton.show).toHaveBeenCalledTimes(1);
    expect(backButton.onClick).toHaveBeenCalledTimes(1);

    // Click triggers onBack1
    clickHandler?.();
    expect(onBack1).toHaveBeenCalledTimes(1);

    // Rerender with new callback does not duplicate handler registration
    rerender({ cb: onBack2 });
    expect(backButton.onClick).toHaveBeenCalledTimes(1);

    // Clicking now invokes the updated callback
    clickHandler?.();
    expect(onBack2).toHaveBeenCalledTimes(1);

    // Unmount removes the listener and hides BackButton
    unmount();
    expect(backButton.offClick).toHaveBeenCalledTimes(1);
    expect(backButton.hide).toHaveBeenCalledTimes(1);
  });
});
