import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/trades';
import type { TradesResponse } from '../types/trades';
import { CATALOG } from '../test/tradesFixture';
import { refreshTrades, resetTrades, useTrades } from './useTrades';

vi.mock('../api/trades', () => ({ fetchTrades: vi.fn(), saveTrades: vi.fn() }));

describe('useTrades (V2-13)', () => {
  beforeEach(() => {
    resetTrades();
    vi.clearAllMocks();
  });
  afterEach(() => resetTrades());

  it('hides nothing until the server has answered, and when it cannot answer', async () => {
    let finish: (value: TradesResponse) => void = () => undefined;
    vi.mocked(api.fetchTrades).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const { result } = renderHook(() => useTrades());
    expect(result.current.known).toBe(false);
    expect(result.current.categoryVisible('ELECTRICAL')).toBe(true);
    expect(result.current.packageVisible('PLUMBING')).toBe(true);
    expect(result.current.anyHidden).toBe(false);
    await act(async () => finish({ ...CATALOG, enabled: ['TILE'] }));
    expect(result.current.known).toBe(true);
    expect(result.current.categoryVisible('ELECTRICAL')).toBe(false);

    resetTrades();
    vi.mocked(api.fetchTrades).mockRejectedValue(new Error('offline'));
    const failed = renderHook(() => useTrades());
    await waitFor(() => expect(api.fetchTrades).toHaveBeenCalledTimes(2));
    expect(failed.result.current.known).toBe(false);
    expect(failed.result.current.categoryVisible('ELECTRICAL')).toBe(true);
  });

  it('every trade on hides nothing', async () => {
    vi.mocked(api.fetchTrades).mockResolvedValue(CATALOG);
    const { result } = renderHook(() => useTrades());
    await waitFor(() => expect(result.current.known).toBe(true));
    expect(result.current.anyHidden).toBe(false);
    for (const c of ['PREPARATION', 'DRYWALL', 'MICROCEMENT', 'TILE', 'ELECTRICAL', 'PLUMBING', 'POINTS_ROUTES']) expect(result.current.categoryVisible(c)).toBe(true);
  });

  it('hides the categories and the packages of the trades that are off, never the universal ones', async () => {
    vi.mocked(api.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'TILE'] });
    const { result } = renderHook(() => useTrades());
    await waitFor(() => expect(result.current.known).toBe(true));
    expect(result.current.anyHidden).toBe(true);
    expect(['PAINTING', 'TILE', 'POINTS_ROUTES', 'MATERIAL', 'OTHER'].map(result.current.categoryVisible)).toEqual([true, true, true, true, true]);
    expect(['DRYWALL', 'MICROCEMENT', 'ELECTRICAL', 'PLUMBING'].map(result.current.categoryVisible)).toEqual([false, false, false, false]);
    expect(['TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING'].map(result.current.packageVisible)).toEqual([true, false, false, false]);
    expect(result.current.isEnabled('TILE')).toBe(true);
    expect(result.current.isEnabled('PLUMBING')).toBe(false);
  });

  it('an empty choice hides every trade; saving replaces what every screen sees', async () => {
    vi.mocked(api.fetchTrades).mockResolvedValue({ ...CATALOG, enabled: [] });
    vi.mocked(api.saveTrades).mockResolvedValue({ ...CATALOG, enabled: ['PLUMBING'] });
    const { result } = renderHook(() => useTrades());
    await waitFor(() => expect(result.current.known).toBe(true));
    expect(result.current.categoryVisible('PAINTING')).toBe(false);
    await act(async () => result.current.save(['PLUMBING']));
    expect(api.saveTrades).toHaveBeenCalledWith(['PLUMBING']);
    expect(result.current.categoryVisible('PLUMBING')).toBe(true);
    expect(result.current.categoryVisible('PAINTING')).toBe(false);
  });

  it('keeps the last good answer when a refresh fails', async () => {
    vi.mocked(api.fetchTrades).mockResolvedValueOnce({ ...CATALOG, enabled: ['TILE'] });
    const { result } = renderHook(() => useTrades());
    await waitFor(() => expect(result.current.known).toBe(true));
    vi.mocked(api.fetchTrades).mockRejectedValueOnce(new Error('offline'));
    await act(async () => refreshTrades());
    expect(result.current.known).toBe(true);
    expect(result.current.categoryVisible('ELECTRICAL')).toBe(false);
  });
});
