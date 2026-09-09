import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TelegramWebApp } from '../types/telegram';
import { useTelegramWebApp } from './useTelegramWebApp';

describe('useTelegramWebApp', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.Telegram;
  });

  it('supports a browser without the Telegram WebApp runtime', () => {
    const { result } = renderHook(() => useTelegramWebApp());

    expect(result.current).toEqual({
      isAvailable: false,
      initData: '',
    });
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
    });
    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
  });
});
