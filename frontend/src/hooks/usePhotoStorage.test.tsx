import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoStorageStatus } from '../types/photo';
import { refreshPhotoStorage, resetPhotoStorage, usePhotoStorage } from './usePhotoStorage';

vi.mock('../api/photos', () => ({ fetchPhotoStorage: vi.fn() }));
import { fetchPhotoStorage } from '../api/photos';

const status = (over: Partial<PhotoStorageStatus> = {}): PhotoStorageStatus => ({
  uploads_enabled: true,
  media_available: true,
  used_bytes: 0,
  warning_bytes: 8,
  soft_cap_bytes: 10,
  state: 'OK',
  ...over,
});

describe('usePhotoStorage', () => {
  beforeEach(() => {
    vi.mocked(fetchPhotoStorage).mockReset();
    resetPhotoStorage();
  });

  it('loads the status once and exposes the derived flags', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(status());
    const { result } = renderHook(() => usePhotoStorage());
    expect(result.current.status).toBe('loading');
    expect(result.current.uploadsEnabled).toBe(false); // unknown until the answer arrives
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current).toMatchObject({ uploadsEnabled: true, mediaAvailable: true, state: 'OK' });
  });

  it('is one shared fetch for every section on the screen', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(status());
    const first = renderHook(() => usePhotoStorage());
    const second = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(first.result.current.status).toBe('ready'));
    expect(second.result.current.status).toBe('ready');
    expect(fetchPhotoStorage).toHaveBeenCalledTimes(1);
    const third = renderHook(() => usePhotoStorage()); // mounted later: reuses the snapshot
    expect(third.result.current.status).toBe('ready');
    expect(fetchPhotoStorage).toHaveBeenCalledTimes(1);
  });

  it('hides upload controls when the gate is closed or the soft cap is reached', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(status({ uploads_enabled: false }));
    const closed = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(closed.result.current.status).toBe('ready'));
    expect(closed.result.current.uploadsEnabled).toBe(false);

    closed.unmount();
    resetPhotoStorage();
    vi.mocked(fetchPhotoStorage).mockResolvedValue(status({ state: 'FULL' }));
    const full = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(full.result.current.state).toBe('FULL'));
    expect(full.result.current.uploadsEnabled).toBe(false);
  });

  it('keeps uploads enabled in the WARNING state', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValue(status({ state: 'WARNING' }));
    const { result } = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(result.current.state).toBe('WARNING'));
    expect(result.current.uploadsEnabled).toBe(true);
  });

  it('treats a failed request as "uploads unavailable" (safe default)', async () => {
    vi.mocked(fetchPhotoStorage).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current).toMatchObject({ uploadsEnabled: false, mediaAvailable: false, data: null });
  });

  it('refresh refetches and keeps the last good data when the refetch fails', async () => {
    vi.mocked(fetchPhotoStorage).mockResolvedValueOnce(status({ used_bytes: 1 }));
    const { result } = renderHook(() => usePhotoStorage());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    vi.mocked(fetchPhotoStorage).mockResolvedValueOnce(status({ used_bytes: 2 }));
    await act(() => result.current.refresh());
    expect(result.current.data?.used_bytes).toBe(2);

    vi.mocked(fetchPhotoStorage).mockRejectedValueOnce(new Error('offline'));
    await act(() => refreshPhotoStorage());
    expect(result.current.status).toBe('error');
    expect(result.current.data?.used_bytes).toBe(2);
  });

  it('joins a refresh already in flight instead of sending a second request', async () => {
    let release: (value: PhotoStorageStatus) => void = () => undefined;
    vi.mocked(fetchPhotoStorage).mockReturnValue(new Promise((resolve) => (release = resolve)));
    const first = refreshPhotoStorage();
    const second = refreshPhotoStorage();
    expect(fetchPhotoStorage).toHaveBeenCalledTimes(1);
    release(status());
    await Promise.all([first, second]);
  });
});
