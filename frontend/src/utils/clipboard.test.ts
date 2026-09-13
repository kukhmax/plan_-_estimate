import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyTextToClipboard } from './clipboard';

describe('copyTextToClipboard (Stage 8C)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    });
  });

  it('uses navigator.clipboard.writeText when available and resolves true', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    await expect(copyTextToClipboard('Hello')).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith('Hello');
  });

  it('falls back to the legacy input copy when the Clipboard API rejects', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    if (typeof document.execCommand !== 'function') {
      Object.defineProperty(document, 'execCommand', {
        value: () => false,
        configurable: true,
      });
    }
    const exec = vi.spyOn(document, 'execCommand').mockReturnValue(true);
    await expect(copyTextToClipboard('Hello')).resolves.toBe(true);
    expect(exec).toHaveBeenCalledWith('copy');
  });

  it('falls back to the legacy input copy when the Clipboard API is missing', async () => {
    if (typeof document.execCommand !== 'function') {
      Object.defineProperty(document, 'execCommand', {
        value: () => false,
        configurable: true,
      });
    }
    const exec = vi.spyOn(document, 'execCommand').mockReturnValue(true);
    await expect(copyTextToClipboard('Hello')).resolves.toBe(true);
    expect(exec).toHaveBeenCalledWith('copy');
  });

  it('never throws and returns false when every copy path fails', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    if (typeof document.execCommand !== 'function') {
      Object.defineProperty(document, 'execCommand', {
        value: () => false,
        configurable: true,
      });
    }
    vi.spyOn(document, 'execCommand').mockReturnValue(false);
    await expect(copyTextToClipboard('Hello')).resolves.toBe(false);
  });
});