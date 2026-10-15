import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { freshIndexedDb } from '../test/fakeIdb';
import { getConnectionState, resetConnectionForTests } from '../offline/connection';
import { loadRead, setOfflineOwner } from '../offline/readCache';
import { ApiError, READ_TIMEOUT_MS, apiRequest } from './http';

const P = '11111111-1111-1111-1111-111111111111';
const ROOMS = `/api/projects/${P}/rooms`;
const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('apiRequest and the copies kept on the phone (Stage 19B)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetConnectionForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps the answer of a read of the kept kinds and shows the next one from the server while it answers', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [{ id: 'r1' }], total: 1 }));
    expect(await apiRequest(ROOMS)).toEqual({ items: [{ id: 'r1' }], total: 1 });
    await flush();
    expect((await loadRead(ROOMS))?.data).toEqual({ items: [{ id: 'r1' }], total: 1 });

    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    expect(await apiRequest(ROOMS)).toEqual({ items: [], total: 0 }); // the server wins, never the copy
    expect(getConnectionState()).toEqual({ offline: false, servedFrom: null });
  });

  it('without a signal gives the saved copy back and says so', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [{ id: 'r1' }], total: 1 }));
    await apiRequest(ROOMS);
    await flush();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const data = await apiRequest(ROOMS);

    expect(data).toEqual({ items: [{ id: 'r1' }], total: 1 });
    const state = getConnectionState();
    expect(state.offline).toBe(true);
    expect(state.servedFrom).toBeGreaterThan(0);
  });

  it('without a signal and without a copy the failure is the same as before', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(apiRequest(ROOMS)).rejects.toBeInstanceOf(TypeError);
    expect(getConnectionState().offline).toBe(true);
    expect(getConnectionState().servedFrom).toBeNull();
  });

  it('the first answer of the server after the signal returns clears the marks', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    await apiRequest(ROOMS);
    await flush();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('x'));
    await apiRequest(ROOMS);
    expect(getConnectionState().offline).toBe(true);

    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    await apiRequest(ROOMS);

    expect(getConnectionState()).toEqual({ offline: false, servedFrom: null });
  });

  it('an error answer of the server is shown as it is, never replaced by a copy (the server is reachable)', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    await apiRequest(ROOMS);
    await flush();
    vi.mocked(fetch).mockResolvedValueOnce(json({ detail: 'Room not found' }, 404));

    await expect(apiRequest(ROOMS)).rejects.toMatchObject({ status: 404 });
    expect(getConnectionState().offline).toBe(false);
    expect((await loadRead(ROOMS))?.data).toEqual({ items: [], total: 0 }); // and the failure did not overwrite the copy
  });

  it('keeps only the kinds of reads meant for work on site', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ items: [], total: 0 }));
    await apiRequest(`/api/projects/${P}/photos/counts`);
    await apiRequest(`/api/projects/${P}/estimates`);
    await apiRequest('/api/calendar');
    await flush();
    expect(await loadRead(`/api/projects/${P}/photos/counts`)).toBeNull();
    expect(await loadRead(`/api/projects/${P}/estimates`)).toBeNull();
    expect(await loadRead('/api/calendar')).toBeNull();

    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('x'));
    await expect(apiRequest('/api/calendar')).rejects.toBeInstanceOf(TypeError); // needs the server
  });

  it('never keeps or serves a write', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ id: 'r2' }, 201));
    await apiRequest(ROOMS, { method: 'POST', body: '{}' });
    await flush();
    expect(await loadRead(ROOMS)).toBeNull();

    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    await apiRequest(ROOMS);
    await flush();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('x'));
    await expect(apiRequest(ROOMS, { method: 'POST', body: '{}' })).rejects.toBeInstanceOf(TypeError);
  });

  it('a read that does not answer in time gives the saved copy (a weak signal hangs instead of failing)', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [{ id: 'r1' }], total: 1 }));
    await apiRequest(ROOMS);
    await flush();
    vi.useFakeTimers();
    vi.mocked(fetch).mockImplementationOnce(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          (init?.signal as AbortSignal).addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    );

    const pending = apiRequest(ROOMS);
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS + 1);

    expect(await pending).toEqual({ items: [{ id: 'r1' }], total: 1 });
    expect(getConnectionState().offline).toBe(true);
  });

  it('a read with its own signal gets no timer of ours', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    const own = new AbortController();
    await apiRequest(ROOMS, { signal: own.signal });
    expect(vi.mocked(fetch).mock.calls[0][1]?.signal).toBe(own.signal);
  });

  it('is unchanged without an owner: nothing is kept', async () => {
    localStorage.removeItem('offline_owner');
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    await apiRequest(ROOMS);
    await flush();
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('x'));
    await expect(apiRequest(ROOMS)).rejects.toBeInstanceOf(TypeError);
  });

  it('still raises ApiError for a failed write answer with its code', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ detail: { code: 'X', message: 'no' } }, 422));
    await expect(apiRequest(ROOMS, { method: 'POST', body: '{}' })).rejects.toMatchObject({ status: 422, code: 'X' });
    await expect(Promise.reject(new ApiError('a', 1))).rejects.toBeInstanceOf(ApiError);
  });
});
