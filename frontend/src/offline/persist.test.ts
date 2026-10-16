import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestPersistentStorage } from './persist';

const withStorage = (storage: unknown) => Object.defineProperty(navigator, 'storage', { configurable: true, value: storage });

describe('asking the browser to keep the data of the phone (Stage 19F)', () => {
  afterEach(() => {
    withStorage(undefined);
  });

  it('asks once and says what the browser answered', async () => {
    const persist = vi.fn(async () => true);
    withStorage({ persist, persisted: async () => false });
    expect(await requestPersistentStorage()).toBe(true);
    expect(persist).toHaveBeenCalledTimes(1);
  });

  it('does not ask again when it is already persistent', async () => {
    const persist = vi.fn(async () => true);
    withStorage({ persist, persisted: async () => true });
    expect(await requestPersistentStorage()).toBe(true);
    expect(persist).not.toHaveBeenCalled();
  });

  it('a refusal is just "false"', async () => {
    withStorage({ persist: async () => false, persisted: async () => false });
    expect(await requestPersistentStorage()).toBe(false);
  });

  it('a WebView without the call, or one that throws, is no trouble', async () => {
    withStorage(undefined);
    expect(await requestPersistentStorage()).toBe(false);
    withStorage({ persist: async () => { throw new Error('denied'); } });
    expect(await requestPersistentStorage()).toBe(false);
  });
});
