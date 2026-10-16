import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { PhotoUploadError } from '../api/photos';
import { PhotoDetailResponse, PhotoTarget, PhotoUploadResponse } from '../types/photo';
import {
  PhotoQueueOptions,
  PhotoQueueStore,
  PhotoQueueTransport,
  PhotoUploadQueue,
  QueueItem,
  StoredPhoto,
  StoredPhotoPatch,
  queueBytes,
} from './photoUploadQueue';

// Stage 19D: the unfinished photos rest on the phone; the queue waits for the signal and keeps within 200 MB.

const target: PhotoTarget = { projectId: 'p1', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' };

function file(name = 'a.jpg', size = 1000, type = 'image/jpeg'): File {
  const f = new File(['x'], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

const uploaded = (id: string): PhotoUploadResponse => ({
  asset: { id } as PhotoUploadResponse['asset'],
  attachment: { id: `att-${id}` } as PhotoUploadResponse['attachment'],
  thumbnail_url: 't',
  display_url: 'd',
  urls_expire_at: '2099-01-01T00:00:00Z',
  storage: { state: 'OK' },
});

const detailOf = (id: string): PhotoDetailResponse => ({
  asset: { id } as PhotoDetailResponse['asset'],
  attachments: [{ id: `first-${id}` }] as PhotoDetailResponse['attachments'],
  thumbnail_url: 't',
  display_url: 'd',
  urls_expire_at: null,
  annotations: [],
  annotation_limit: 10,
  outline_max_points: 120,
});

/** A store in memory that remembers what was asked of it. */
function fakeStore(over: Partial<PhotoQueueStore> = {}) {
  const records = new Map<string, StoredPhoto>();
  const files = new Map<string, File>();
  const store: PhotoQueueStore = {
    put: vi.fn(async (item: QueueItem, f: File, thumb: string | null) => {
      records.set(item.id, {
        thumb,
        id: item.id, ownerId: 'o', uploadId: item.uploadId, target: item.target, source: item.source, name: f.name, type: f.type,
        lastModified: 0, size: f.size, createdAt: records.size, state: 'queued', attempt: item.attempt, error: item.error,
      });
      files.set(item.id, f);
    }),
    update: vi.fn(async (id: string, patch: StoredPhotoPatch) => {
      const current = records.get(id);
      if (current) records.set(id, { ...current, ...patch });
    }),
    remove: vi.fn(async (id: string) => {
      records.delete(id);
      files.delete(id);
    }),
    loadFile: vi.fn(async (id: string) => files.get(id) ?? null),
    ...over,
  };
  return { store, records, files };
}

function setup(over: Partial<PhotoQueueOptions> = {}) {
  const uploads: Array<{ uploadId: string; resolve: (v: PhotoUploadResponse) => void; reject: (e: unknown) => void }> = [];
  const fetchDetail = vi.fn<[string, string], Promise<PhotoDetailResponse>>();
  const transport: PhotoQueueTransport = {
    upload: (params, options) =>
      new Promise<PhotoUploadResponse>((resolve, reject) => {
        uploads.push({ uploadId: params.uploadId, resolve, reject });
        options.signal?.addEventListener('abort', () => reject(new PhotoUploadError('canceled', 0, 'UPLOAD_ABORTED')));
      }),
    fetchDetail,
  };
  let n = 0;
  const persisted = fakeStore();
  const queue = new PhotoUploadQueue({
    transport,
    previews: { create: () => null, revoke: () => {} },
    newId: () => `id-${(n += 1)}`,
    store: persisted.store,
    ...over,
  });
  return { queue, uploads, fetchDetail, ...persisted };
}

const tick = () => vi.advanceTimersByTimeAsync(0);
const states = (queue: PhotoUploadQueue) => queue.getItems().map((i) => i.state);

describe('PhotoUploadQueue on the phone (Stage 19D)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('keeping the photos', () => {
    it('keeps a photo with its bytes when it is queued, and lets it go when it is sent', async () => {
      const { queue, uploads, store, records, files } = setup();
      queue.enqueue([file('1.jpg')], target, 'CAMERA');
      await tick();
      expect(store.put).toHaveBeenCalledTimes(1);
      expect(records.size).toBe(1);
      expect(files.get(queue.getItems()[0].id)?.name).toBe('1.jpg');

      uploads[0].resolve(uploaded('a'));
      await tick();
      expect(states(queue)).toEqual(['done']);
      expect(records.size).toBe(0);
      expect(files.size).toBe(0);
    });

    it('does not keep a photo the checks refuse at once (wrong format)', async () => {
      const { queue, store, records } = setup();
      queue.enqueue([file('x.gif', 10, 'image/gif')], target, 'GALLERY');
      await tick();
      expect(states(queue)).toEqual(['failed']);
      expect(store.put).not.toHaveBeenCalled();
      expect(records.size).toBe(0);
    });

    it('a canceled or closed photo is removed from the phone', async () => {
      const { queue, records } = setup({ canStart: () => false });
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      expect(records.size).toBe(2);

      queue.cancel(items[0].id);
      await tick();
      expect(records.size).toBe(1);
      queue.dismiss(items[0].id);
      queue.cancel(items[1].id);
      queue.dismiss(items[1].id);
      await tick();
      expect(records.size).toBe(0);
    });

    it('a failure is written down, a manual retry puts the photo back to waiting', async () => {
      const { queue, uploads, records } = setup();
      const { items } = queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      uploads[0].reject(new PhotoUploadError('too big', 413, 'PHOTO_TOO_LARGE'));
      await tick();
      expect(records.get(items[0].id)).toMatchObject({ state: 'failed', error: { code: 'PHOTO_TOO_LARGE' } });
      expect(records.get(items[0].id)?.attempt).toBe(1);
    });

    it('the bytes leave the memory once the photo rests on the phone only', async () => {
      const { queue, uploads } = setup();
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      expect(queue.getItems()[0].file).not.toBeNull(); // being sent
      uploads[0].reject(new PhotoUploadError('storage', 503, 'PHOTO_STORAGE_UNAVAILABLE'));
      await tick();
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', file: null });

      queue.retry(queue.getItems()[0].id); // the bytes come back from the phone
      await tick();
      expect(uploads).toHaveLength(2);
      expect(uploads[1].uploadId).toBe(uploads[0].uploadId);
    });

    it('when the phone cannot keep the photo the row says so and the photo is still sent', async () => {
      vi.spyOn(console, 'warn').mockImplementation(() => {});
      const failing = setup({ store: fakeStore({ put: vi.fn(async () => { throw new Error('full'); }) }).store });
      failing.queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      expect(failing.queue.getItems()[0].saveFailed).toBe(true);
      expect(failing.uploads).toHaveLength(1); // still sent in this session
      expect(failing.queue.getItems()[0].file).not.toBeNull(); // and kept in memory
      failing.uploads[0].resolve(uploaded('a'));
      await tick();
      expect(failing.queue.getItems()[0].state).toBe('done');
    });
  });

  describe('the 200 MB limit', () => {
    const MB = 1024 * 1024;

    it('refuses what would take the waiting photos over the limit and says how many', async () => {
      const { queue } = setup({ canStart: () => false, limitBytes: 10 * MB });
      const first = queue.enqueue([file('1.jpg', 6 * MB), file('2.jpg', 6 * MB), file('3.jpg', 3 * MB)], target, 'GALLERY');
      expect(first.items.map((i) => i.name)).toEqual(['1.jpg', '3.jpg']);
      expect(first.rejected).toBe(1);
      expect(queueBytes(queue.getItems())).toBe(9 * MB);

      const second = queue.enqueue([file('4.jpg', 2 * MB)], target, 'GALLERY');
      expect(second.rejected).toBe(1);
      expect(queue.getItems()).toHaveLength(2);
    });

    it('a photo that was sent gives its room back; a failed one keeps it until it is closed', async () => {
      const { queue, uploads } = setup({ limitBytes: 10 * MB });
      queue.enqueue([file('1.jpg', 6 * MB), file('2.jpg', 4 * MB)], target, 'GALLERY');
      await tick();
      uploads[0].resolve(uploaded('a'));
      await tick();
      expect(queueBytes(queue.getItems())).toBe(4 * MB);

      uploads[1].reject(new PhotoUploadError('bad', 422, 'PHOTO_INVALID_IMAGE'));
      await tick();
      expect(states(queue)).toEqual(['done', 'failed']);
      expect(queueBytes(queue.getItems())).toBe(4 * MB);
      expect(queue.enqueue([file('3.jpg', 7 * MB)], target, 'GALLERY').rejected).toBe(1);

      queue.dismiss(queue.getItems()[1].id);
      expect(queue.enqueue([file('3.jpg', 7 * MB)], target, 'GALLERY').rejected).toBe(0);
    });

    it('a photo the checks refuse does not use up the room', async () => {
      const { queue } = setup({ canStart: () => false, limitBytes: 5 * MB });
      const result = queue.enqueue([file('big.jpg', 30_000_000), file('ok.jpg', 4 * MB)], target, 'GALLERY');
      expect(result.rejected).toBe(0);
      expect(queue.getItems().map((i) => i.state)).toEqual(['failed', 'queued']);
    });
  });

  describe('waiting for the signal', () => {
    it('starts nothing while it cannot start, and starts when kicked', async () => {
      let online = false;
      const { queue, uploads } = setup({ canStart: () => online });
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      expect(uploads).toHaveLength(0);
      expect(states(queue)).toEqual(['queued']);

      online = true;
      queue.kick();
      await tick();
      expect(uploads).toHaveLength(1);
    });

    it('the signal lost in the middle of a photo puts it back to waiting, nothing is counted against it', async () => {
      let online = true;
      const { queue, uploads, fetchDetail } = setup({ canStart: () => online });
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();

      online = false; // the request fails and the server cannot be asked either (apiRequest has noticed the connection is gone)
      fetchDetail.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      uploads[0].reject(new PhotoUploadError('Network error', 0, 'NETWORK_ERROR'));
      await tick();
      expect(queue.getItems()[0]).toMatchObject({ state: 'queued', networkRetries: 0, verify: true, error: null });
      expect(uploads).toHaveLength(1);

      online = true;
      fetchDetail.mockRejectedValueOnce(new ApiError('nf', 404, 'PHOTO_NOT_FOUND')); // the first attempt never arrived
      queue.kick();
      await tick();
      expect(fetchDetail).toHaveBeenCalledTimes(2); // asked first, then sent again with the SAME upload id
      expect(uploads).toHaveLength(2);
      expect(uploads[1].uploadId).toBe(uploads[0].uploadId);
      uploads[1].resolve(uploaded('a'));
      await tick();
      expect(states(queue)).toEqual(['done']);
    });

    it('a photo that did arrive before the signal went is not sent twice', async () => {
      let online = true;
      const { queue, uploads, fetchDetail, onDone } = (() => {
        const onDone = vi.fn();
        return { ...setup({ canStart: () => online, onDone }), onDone };
      })();
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      online = false;
      fetchDetail.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      uploads[0].reject(new PhotoUploadError('Network error', 0, 'NETWORK_ERROR'));
      await tick();

      online = true;
      fetchDetail.mockResolvedValueOnce(detailOf(uploads[0].uploadId));
      queue.kick();
      await tick();
      expect(states(queue)).toEqual(['done']);
      expect(uploads).toHaveLength(1);
      expect(onDone).toHaveBeenCalledTimes(1);
    });
  });

  describe('after the application was closed', () => {
    const record = (over: Partial<StoredPhoto> = {}): StoredPhoto => ({
      id: 'q1-x', ownerId: 'o', uploadId: 'up-1', target, source: 'CAMERA', name: 'IMG.jpg', type: 'image/jpeg', lastModified: 5,
      size: 2000, createdAt: 1, state: 'queued', attempt: 0, error: null, ...over,
    });

    it('puts the photos back without loading their bytes, oldest first, ahead of new ones', async () => {
      const { queue, store } = setup({ canStart: () => false });
      queue.enqueue([file('new.jpg')], target, 'GALLERY');
      queue.restore([record({ id: 'b', createdAt: 20, name: 'b.jpg' }), record({ id: 'a', createdAt: 10, name: 'a.jpg' })]);
      expect(queue.getItems().map((i) => i.name)).toEqual(['a.jpg', 'b.jpg', 'new.jpg']);
      expect(queue.getItems()[0]).toMatchObject({ state: 'queued', file: null, previewUrl: null, size: 2000 });
      expect(store.loadFile).not.toHaveBeenCalled();
      expect(queueBytes(queue.getItems())).toBe(2000 + 2000 + 1000);
    });

    it('sends a restored photo with the bytes read back from the phone, keeping its upload id', async () => {
      const { queue, uploads, files } = setup();
      files.set('q1-x', file('IMG.jpg', 2000));
      queue.restore([record()]);
      await tick();
      expect(uploads).toHaveLength(1);
      expect(uploads[0].uploadId).toBe('up-1');
    });

    it('asks the server first when the photo may already be there (a POST had been started)', async () => {
      const { queue, uploads, fetchDetail, files, records } = setup();
      files.set('q1-x', file());
      records.set('q1-x', record({ attempt: 1 }));
      fetchDetail.mockResolvedValueOnce(detailOf('up-1'));
      queue.restore([record({ attempt: 1 })]);
      await tick();
      expect(fetchDetail).toHaveBeenCalledWith('p1', 'up-1');
      expect(uploads).toHaveLength(0);
      expect(states(queue)).toEqual(['done']);
      expect(records.size).toBe(0);
    });

    it('sends it when the server says it has no such photo', async () => {
      const { queue, uploads, fetchDetail, files } = setup();
      files.set('q1-x', file());
      fetchDetail.mockRejectedValueOnce(new ApiError('nf', 404, 'PHOTO_NOT_FOUND'));
      queue.restore([record({ attempt: 2 })]);
      await tick();
      expect(uploads).toHaveLength(1);
    });

    it('a photo whose bytes are gone from the phone fails with its own message', async () => {
      const { queue, uploads } = setup();
      queue.restore([record()]);
      await tick();
      expect(uploads).toHaveLength(0);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'gone_from_phone' } });
    });

    it('a photo that had failed comes back failed, with its reason', async () => {
      const { queue } = setup({ canStart: () => false });
      queue.restore([
        record({ state: 'failed', error: { code: 'PHOTO_TOO_LARGE', key: 'too_large', retryable: false, retryAsNew: false, stopsQueue: false, uploadsDisabled: false, refetch: null } }),
      ]);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'too_large' } });
    });

    it('does not put back what is already there', () => {
      const { queue } = setup({ canStart: () => false });
      queue.restore([record()]);
      queue.restore([record()]);
      expect(queue.getItems()).toHaveLength(1);
    });
  });

  describe('the session ends while a photo waits', () => {
    it('signs in again once and sends the photo with the new token', async () => {
      const refreshSession = vi.fn(async () => true);
      const { queue, uploads } = setup({ refreshSession });
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      uploads[0].reject(new PhotoUploadError('expired', 401));
      await tick();
      expect(refreshSession).toHaveBeenCalledTimes(1);
      expect(states(queue)).toEqual(['uploading', 'queued']); // the same photo again, the second one still waits
      expect(uploads).toHaveLength(2);
      expect(uploads[1].uploadId).toBe(uploads[0].uploadId);

      uploads[1].resolve(uploaded('a'));
      await tick();
      expect(uploads).toHaveLength(3);
    });

    it('when signing in fails the queue stops with the session message, as before', async () => {
      const { queue, uploads } = setup({ refreshSession: async () => false });
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      uploads[0].reject(new PhotoUploadError('expired', 401));
      await tick();
      expect(states(queue)).toEqual(['failed', 'failed']);
      expect(queue.getItems()[0].error?.key).toBe('session_expired');
    });

    it('does not sign in again in a loop when the new token is refused too', async () => {
      const refreshSession = vi.fn(async () => true);
      const { queue, uploads } = setup({ refreshSession });
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      uploads[0].reject(new PhotoUploadError('expired', 401));
      await tick();
      uploads[1].reject(new PhotoUploadError('expired', 401));
      await tick();
      expect(refreshSession).toHaveBeenCalledTimes(1);
      expect(states(queue)).toEqual(['failed']);
    });
  });
});

describe('the small picture of a waiting photo (Stage 19E)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is drawn when the photo is kept, and the row of a restored photo shows it', async () => {
    const { queue, records } = setup({ canStart: () => false, thumbnail: async () => 'data:image/jpeg;base64,AAAA' });
    const { items } = queue.enqueue([file('1.jpg')], target, 'CAMERA');
    await tick();
    expect(records.get(items[0].id)?.thumb).toBe('data:image/jpeg;base64,AAAA');

    const again = setup({ canStart: () => false });
    again.queue.restore([records.get(items[0].id) as StoredPhoto]);
    expect(again.queue.getItems()[0].previewUrl).toBe('data:image/jpeg;base64,AAAA');
  });

  it('a photo that cannot be drawn is kept all the same, and the restored row has no picture', async () => {
    const { queue, records } = setup({ canStart: () => false, thumbnail: async () => { throw new Error('no canvas'); } });
    const { items } = queue.enqueue([file('1.jpg')], target, 'CAMERA');
    await tick();
    expect(records.get(items[0].id)).toMatchObject({ thumb: null, name: '1.jpg' });
    expect(queue.getItems()[0].saveFailed).toBe(false);

    const again = setup({ canStart: () => false });
    again.queue.restore([records.get(items[0].id) as StoredPhoto]);
    expect(again.queue.getItems()[0].previewUrl).toBeNull();
  });

  it('a photo refused at once is not drawn', async () => {
    const thumbnail = vi.fn(async () => 'data:image/jpeg;base64,AAAA');
    const { queue } = setup({ thumbnail });
    queue.enqueue([file('x.gif', 10, 'image/gif')], target, 'GALLERY');
    await tick();
    expect(thumbnail).not.toHaveBeenCalled();
  });
});
