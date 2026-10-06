import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoDetailResponse, PhotoUploadResponse } from '../types/photo';
import {
  getPhotoUploadQueue,
  resetPhotoUploadQueue,
  subscribePhotoUploadDone,
  subscribePhotoUploadRefetch,
  usePhotoUploadQueue,
} from './usePhotoUploadQueue';

vi.mock('../api/photos', async () => {
  const actual = await vi.importActual<typeof import('../api/photos')>('../api/photos');
  return { ...actual, uploadPhoto: vi.fn(), fetchPhoto: vi.fn() };
});
vi.mock('./usePhotoStorage', () => ({ refreshPhotoStorage: vi.fn() }));
import { PhotoUploadError, fetchPhoto, uploadPhoto } from '../api/photos';
import { refreshPhotoStorage } from './usePhotoStorage';

const file = (name = 'a.jpg') => new File(['x'], name, { type: 'image/jpeg' });
const response = (id: string) => ({ asset: { id }, attachment: null, thumbnail_url: 't', display_url: 'd', urls_expire_at: 'x', storage: { state: 'OK' } }) as unknown as PhotoUploadResponse;

let pending: Array<{ resolve: (v: PhotoUploadResponse) => void; reject: (e: unknown) => void }>;

describe('usePhotoUploadQueue', () => {
  beforeEach(() => {
    pending = [];
    vi.mocked(uploadPhoto).mockReset().mockImplementation(
      () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
    );
    vi.mocked(fetchPhoto).mockReset();
    vi.mocked(refreshPhotoStorage).mockReset();
    resetPhotoUploadQueue();
  });
  afterEach(() => resetPhotoUploadQueue());

  it('shares one queue across hook instances and drives uploads through the real transport functions', async () => {
    const a = renderHook(() => usePhotoUploadQueue('p1'));
    const b = renderHook(() => usePhotoUploadQueue('p1'));
    await act(async () => {
      a.result.current.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'CAMERA');
    });
    expect(uploadPhoto).toHaveBeenCalledTimes(1);
    expect(vi.mocked(uploadPhoto).mock.calls[0][0]).toMatchObject({ projectId: 'p1', context: 'PROJECT', source: 'CAMERA' });
    expect(a.result.current.items).toHaveLength(1);
    expect(b.result.current.items).toHaveLength(1);
    expect(b.result.current.items[0].state).toBe('uploading');
  });

  it('shows only the items of its project', async () => {
    const p1 = renderHook(() => usePhotoUploadQueue('p1'));
    const p2 = renderHook(() => usePhotoUploadQueue('p2'));
    const all = renderHook(() => usePhotoUploadQueue());
    await act(async () => {
      p1.result.current.enqueue([file('1.jpg')], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
      p2.result.current.enqueue([file('2.jpg')], { projectId: 'p2', context: 'PROJECT' }, 'GALLERY');
    });
    expect(p1.result.current.items.map((i) => i.file.name)).toEqual(['1.jpg']);
    expect(p2.result.current.items.map((i) => i.file.name)).toEqual(['2.jpg']);
    expect(all.result.current.items).toHaveLength(2);
  });

  it('notifies the host when an item is done', async () => {
    const onDone = vi.fn();
    const unsubscribe = subscribePhotoUploadDone(onDone);
    const { result } = renderHook(() => usePhotoUploadQueue('p1'));
    await act(async () => {
      result.current.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
    });
    await act(async () => pending[0].resolve(response('A')));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(result.current.items[0].state).toBe('done');
    unsubscribe();
    await act(async () => {
      result.current.enqueue([file('2.jpg')], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
    });
    await act(async () => pending[1].resolve(response('B')));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('refreshes the shared storage status when the server stops the queue', async () => {
    const { result } = renderHook(() => usePhotoUploadQueue('p1'));
    await act(async () => {
      result.current.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
    });
    await act(async () => pending[0].reject(new PhotoUploadError('d', 503, 'PHOTO_UPLOADS_DISABLED')));
    expect(refreshPhotoStorage).toHaveBeenCalledTimes(1);
  });

  it('relays refetch requests (vanished target) to the host', async () => {
    const onRefetch = vi.fn();
    subscribePhotoUploadRefetch(onRefetch);
    const { result } = renderHook(() => usePhotoUploadQueue('p1'));
    await act(async () => {
      result.current.enqueue([file()], { projectId: 'p1', context: 'ROOM', roomId: 'r' }, 'GALLERY');
    });
    await act(async () => pending[0].reject(new PhotoUploadError('nf', 404, 'ROOM_NOT_FOUND')));
    expect(onRefetch).toHaveBeenCalledWith('parent', expect.objectContaining({ state: 'failed' }));
  });

  it('exposes cancel / retry / dismiss', async () => {
    const { result } = renderHook(() => usePhotoUploadQueue('p1'));
    await act(async () => {
      result.current.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
    });
    const id = result.current.items[0].id;
    await act(async () => pending[0].reject(new PhotoUploadError('x', 500, 'PHOTO_STORAGE_ERROR')));
    expect(result.current.items[0].state).toBe('failed');
    await act(async () => result.current.retry(id));
    expect(result.current.items[0].state).toBe('uploading');
    await act(async () => result.current.cancel(id));
    expect(result.current.items[0].state).toBe('canceled');
    act(() => result.current.dismiss(id));
    expect(result.current.items).toHaveLength(0);
  });

  describe('foreground reconcile', () => {
    async function withActiveUpload() {
      vi.mocked(fetchPhoto).mockResolvedValue({ asset: { id: 'x' }, attachments: [] } as unknown as PhotoDetailResponse);
      const hook = renderHook(() => usePhotoUploadQueue('p1'));
      await act(async () => {
        hook.result.current.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
      });
      return hook;
    }

    it('reconciles when the page becomes visible', async () => {
      await withActiveUpload();
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
      await act(async () => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(fetchPhoto).toHaveBeenCalledTimes(1);
    });

    it('does not reconcile when the page becomes hidden', async () => {
      await withActiveUpload();
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      await act(async () => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(fetchPhoto).not.toHaveBeenCalled();
    });

    it('reconciles when the network comes back', async () => {
      await withActiveUpload();
      await act(async () => {
        window.dispatchEvent(new Event('online'));
      });
      expect(fetchPhoto).toHaveBeenCalledTimes(1);
    });

    it('stops listening after unmount', async () => {
      const hook = await withActiveUpload();
      hook.unmount();
      await act(async () => {
        window.dispatchEvent(new Event('online'));
      });
      expect(fetchPhoto).not.toHaveBeenCalled();
    });
  });

  it('resetPhotoUploadQueue gives the next caller a fresh, empty queue', async () => {
    const first = getPhotoUploadQueue();
    first.enqueue([file()], { projectId: 'p1', context: 'PROJECT' }, 'GALLERY');
    resetPhotoUploadQueue();
    const second = getPhotoUploadQueue();
    expect(second).not.toBe(first);
    expect(second.getItems()).toEqual([]);
  });
});
