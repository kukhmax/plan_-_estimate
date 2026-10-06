import { afterEach, describe, expect, it, vi } from 'vitest';
import { hapticNotify } from './telegramHaptics';

afterEach(() => {
  delete window.Telegram;
});

describe('hapticNotify', () => {
  it('does nothing without the Telegram runtime or without haptics', () => {
    expect(() => hapticNotify('success')).not.toThrow();
    window.Telegram = { WebApp: {} } as unknown as typeof window.Telegram;
    expect(() => hapticNotify('error')).not.toThrow();
  });

  it('forwards the notification type to Telegram', () => {
    const notificationOccurred = vi.fn();
    window.Telegram = { WebApp: { HapticFeedback: { notificationOccurred } } } as unknown as typeof window.Telegram;
    hapticNotify('success');
    hapticNotify('error');
    expect(notificationOccurred.mock.calls).toEqual([['success'], ['error']]);
  });
});
