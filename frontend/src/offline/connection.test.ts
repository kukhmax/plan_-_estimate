import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getConnectionState,
  reportNetworkFailure,
  reportNetworkSuccess,
  reportServedFromCache,
  resetConnectionForTests,
  useConnection,
} from './connection';
import { PROBE_INTERVAL_MS, probeServer, startConnectionWatch } from './watch';

describe('the connection state (Stage 19B)', () => {
  beforeEach(() => resetConnectionForTests());

  it('starts online with nothing stale', () => {
    expect(getConnectionState()).toEqual({ offline: false, servedFrom: null });
  });

  it('a failure marks it offline; an answer of the server clears everything', () => {
    reportNetworkFailure();
    reportServedFromCache(1000);
    expect(getConnectionState()).toEqual({ offline: true, servedFrom: 1000 });
    reportNetworkSuccess();
    expect(getConnectionState()).toEqual({ offline: false, servedFrom: null });
  });

  it('shows the OLDEST copy served since the last answer', () => {
    reportServedFromCache(5000);
    reportServedFromCache(3000);
    reportServedFromCache(4000);
    expect(getConnectionState().servedFrom).toBe(3000);
  });

  it('the hook follows the state', () => {
    const { result } = renderHook(() => useConnection());
    expect(result.current.offline).toBe(false);
    act(() => reportNetworkFailure());
    expect(result.current.offline).toBe(true);
    act(() => reportNetworkSuccess());
    expect(result.current.offline).toBe(false);
  });
});

describe('watching the connection (Stage 19B)', () => {
  beforeEach(() => {
    resetConnectionForTests();
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('the browser saying "offline" marks it, and "online" looks at the server', async () => {
    const probe = vi.fn().mockResolvedValue(true);
    const stop = startConnectionWatch(probe);
    window.dispatchEvent(new Event('offline'));
    expect(getConnectionState().offline).toBe(true);
    window.dispatchEvent(new Event('online'));
    expect(probe).toHaveBeenCalledTimes(1);
    stop();
  });

  it('while offline it looks at the server every 15 s, and stops looking when online', async () => {
    const probe = vi.fn().mockResolvedValue(false);
    const stop = startConnectionWatch(probe);
    await vi.advanceTimersByTimeAsync(PROBE_INTERVAL_MS * 3);
    expect(probe).not.toHaveBeenCalled(); // online: nothing to look at
    reportNetworkFailure();
    await vi.advanceTimersByTimeAsync(PROBE_INTERVAL_MS * 2);
    expect(probe).toHaveBeenCalledTimes(2);
    stop();
    await vi.advanceTimersByTimeAsync(PROBE_INTERVAL_MS * 2);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('the probe reports the server reachable or not', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true } as Response);
    reportNetworkFailure();
    expect(await probeServer()).toBe(true);
    expect(getConnectionState().offline).toBe(false);

    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('x'));
    expect(await probeServer()).toBe(false);
    expect(getConnectionState().offline).toBe(true);
  });
});
