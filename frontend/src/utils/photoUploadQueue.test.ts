import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { PhotoUploadError } from '../api/photos';
import { PhotoDetailResponse, PhotoTarget, PhotoUploadResponse } from '../types/photo';
import {
  BUSY_RETRY_CAP_SECONDS,
  DEFAULT_BUSY_RETRY_SECONDS,
  MAX_AUTO_RETRIES,
  MAX_FILES_PER_SELECTION,
  PHOTO_MAX_UPLOAD_BYTES,
  PhotoQueueOptions,
  PhotoQueueTransport,
  PhotoUploadQueue,
  generateUploadId,
} from './photoUploadQueue';

const PROJECT = 'p1';
const target: PhotoTarget = { projectId: PROJECT, context: 'ROOM', roomId: 'r1' };

function file(name = 'a.jpg', type = 'image/jpeg', size = 1000): File {
  const f = new File(['x'], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

function uploadResponse(id: string): PhotoUploadResponse {
  return {
    asset: { id } as PhotoUploadResponse['asset'],
    attachment: { id: `att-${id}` } as PhotoUploadResponse['attachment'],
    thumbnail_url: 'https://r2/t',
    display_url: 'https://r2/d',
    urls_expire_at: '2026-10-06T12:00:00Z',
    storage: { state: 'OK' },
  };
}

function detail(id: string): PhotoDetailResponse {
  return {
    asset: { id } as PhotoDetailResponse['asset'],
    attachments: [{ id: `first-${id}` }, { id: `second-${id}` }] as PhotoDetailResponse['attachments'],
    thumbnail_url: 't',
    display_url: 'd',
    urls_expire_at: null,
  };
}

interface UploadCall {
  uploadId: string;
  params: Parameters<PhotoQueueTransport['upload']>[0];
  options: Parameters<PhotoQueueTransport['upload']>[1];
  resolve: (value: PhotoUploadResponse) => void;
  reject: (reason: unknown) => void;
}

function setup(over: Partial<PhotoQueueOptions> = {}) {
  const calls: UploadCall[] = [];
  const fetchDetail = vi.fn<[string, string], Promise<PhotoDetailResponse>>();
  const transport: PhotoQueueTransport = {
    upload: (params, options) =>
      new Promise<PhotoUploadResponse>((resolve, reject) => {
        calls.push({ uploadId: params.uploadId, params, options, resolve, reject });
        options.signal?.addEventListener('abort', () => reject(new PhotoUploadError('canceled', 0, 'UPLOAD_ABORTED')));
      }),
    fetchDetail,
  };
  let seq = 0;
  const previews = { create: vi.fn(() => `blob:${(seq += 1)}`), revoke: vi.fn() };
  const onDone = vi.fn();
  const onRefetch = vi.fn();
  const onStopped = vi.fn();
  let idSeq = 0;
  const queue = new PhotoUploadQueue({
    transport,
    previews,
    onDone,
    onRefetch,
    onStopped,
    newId: () => `id-${(idSeq += 1)}`,
    ...over,
  });
  return { queue, calls, fetchDetail, previews, onDone, onRefetch, onStopped };
}

const tick = () => vi.advanceTimersByTimeAsync(0);
const state = (queue: PhotoUploadQueue, index = 0) => queue.getItems()[index].state;

describe('PhotoUploadQueue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  describe('enqueue and the single lane', () => {
    it('starts the first upload at once and keeps the others queued (concurrency 1)', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg'), file('3.jpg')], target, 'GALLERY');
      await tick();
      expect(calls).toHaveLength(1);
      expect(queue.getItems().map((i) => i.state)).toEqual(['uploading', 'queued', 'queued']);

      calls[0].resolve(uploadResponse('a'));
      await tick();
      expect(calls).toHaveLength(2);
      expect(queue.getItems().map((i) => i.state)).toEqual(['done', 'uploading', 'queued']);
    });

    it('never runs two uploads at once, whatever triggers the next start (new batch, retry, cancel)', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('1.jpg')], target, 'GALLERY');
      await tick();
      queue.enqueue([file('2.jpg')], target, 'GALLERY'); // a second selection while one is uploading
      await tick();
      expect(calls).toHaveLength(1);

      queue.enqueue([file('bad.gif', 'image/gif')], target, 'GALLERY');
      queue.retry(queue.getItems()[2].id); // refused (not retryable) and must not start anything either
      await tick();
      expect(calls).toHaveLength(1);
      expect(queue.getItems().filter((i) => i.state === 'uploading' || i.state === 'processing')).toHaveLength(1);
    });

    it('a manual retry of a failed row waits for the active upload instead of running beside it', async () => {
      const { queue, calls } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('x', 500, 'PHOTO_STORAGE_ERROR'));
      await tick();
      expect(calls).toHaveLength(2); // the second file is now uploading
      queue.retry(items[0].id);
      await tick();
      expect(calls).toHaveLength(2);
      expect(queue.getItems().map((i) => i.state)).toEqual(['queued', 'uploading']);
      calls[1].resolve(uploadResponse('b'));
      await tick();
      expect(calls).toHaveLength(3);
      expect(calls[2].uploadId).toBe(items[0].uploadId);
    });

    it('gives every file its own stable upload_id and passes target and declared source to the transport', async () => {
      const { queue, calls } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'CAMERA');
      await tick();
      expect(items[0].uploadId).not.toBe(items[1].uploadId);
      expect(calls[0].params).toMatchObject({ ...target, uploadId: items[0].uploadId, source: 'CAMERA' });
      expect(calls[0].params.file).toBe(items[0].file);
    });

    it('limits one selection to 10 files and reports how many were ignored', () => {
      const { queue } = setup();
      const files = Array.from({ length: 13 }, (_, i) => file(`${i}.jpg`));
      const result = queue.enqueue(files, target, 'GALLERY');
      expect(result.items).toHaveLength(MAX_FILES_PER_SELECTION);
      expect(result.ignored).toBe(3);
      expect(queue.getItems()).toHaveLength(MAX_FILES_PER_SELECTION);
    });

    it('rejects an oversized file locally without any request and without a preview', async () => {
      const { queue, calls, previews } = setup();
      queue.enqueue([file('big.jpg', 'image/jpeg', PHOTO_MAX_UPLOAD_BYTES + 1)], target, 'GALLERY');
      await tick();
      expect(calls).toHaveLength(0);
      expect(previews.create).not.toHaveBeenCalled();
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'too_large', retryable: false } });
    });

    it('accepts a file of exactly the limit', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('edge.jpg', 'image/jpeg', PHOTO_MAX_UPLOAD_BYTES)], target, 'GALLERY');
      await tick();
      expect(calls).toHaveLength(1);
    });

    it('rejects HEIC and other unsupported types locally; an empty MIME is left to the server', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('x.heic', 'image/heic'), file('y.gif', 'image/gif'), file('cam', '')], target, 'CAMERA');
      await tick();
      expect(queue.getItems().map((i) => i.state)).toEqual(['failed', 'failed', 'uploading']);
      expect(queue.getItems()[0].error?.key).toBe('unsupported_format');
      expect(calls).toHaveLength(1);
      expect(calls[0].params.file.name).toBe('cam');
    });

    it('accepts uppercase MIME spelling', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('a.jpg', 'IMAGE/JPEG')], target, 'GALLERY');
      await tick();
      expect(calls).toHaveLength(1);
    });
  });

  describe('progress and completion', () => {
    it('moves queued → uploading(progress) → processing → done and exposes the result', async () => {
      const { queue, calls, onDone, previews } = setup();
      queue.enqueue([file()], target, 'CAMERA');
      await tick();
      expect(state(queue)).toBe('uploading');

      calls[0].options.onProgress?.(50, 100);
      expect(queue.getItems()[0]).toMatchObject({ state: 'uploading', progress: 0.5 });

      calls[0].options.onBytesSent?.();
      expect(queue.getItems()[0]).toMatchObject({ state: 'processing', progress: 1 });

      calls[0].resolve(uploadResponse('asset-1'));
      await tick();
      const item = queue.getItems()[0];
      expect(item.state).toBe('done');
      expect(item.result).toMatchObject({
        asset: { id: 'asset-1' },
        attachment: { id: 'att-asset-1' },
        thumbnailUrl: 'https://r2/t',
        displayUrl: 'https://r2/d',
      });
      expect(onDone).toHaveBeenCalledTimes(1);
      expect(onDone.mock.calls[0][0].id).toBe(item.id);
      expect(previews.revoke).toHaveBeenCalledWith('blob:1');
      expect(item.previewUrl).toBeNull();
    });

    it('ignores late progress after the state moved on', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file()], target, 'CAMERA');
      await tick();
      calls[0].options.onBytesSent?.();
      calls[0].options.onProgress?.(10, 100);
      expect(queue.getItems()[0]).toMatchObject({ state: 'processing', progress: 1 });
    });
  });

  describe('retry protocol (GET first)', () => {
    it('after a network error asks the server first; an existing READY asset ends the item without a second POST', async () => {
      const { queue, calls, fetchDetail, onDone } = setup();
      fetchDetail.mockResolvedValue(detail('A'));
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
      await tick();
      expect(fetchDetail).toHaveBeenCalledWith(PROJECT, items[0].uploadId);
      expect(calls).toHaveLength(1);
      expect(queue.getItems()[0].state).toBe('done');
      // the upload's own attachment is the first one in creation order
      expect(queue.getItems()[0].result?.attachment?.id).toBe('first-A');
      expect(onDone).toHaveBeenCalledTimes(1);
    });

    it('404 on the check re-POSTs the SAME upload_id and the same File after a short backoff', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('nf', 404, 'PHOTO_NOT_FOUND'));
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('stalled', 0, 'UPLOAD_STALLED'));
      await tick();
      expect(queue.getItems()[0].state).toBe('queued');
      expect(calls).toHaveLength(1);

      await vi.advanceTimersByTimeAsync(2_000);
      expect(calls).toHaveLength(2);
      expect(calls[1].uploadId).toBe(items[0].uploadId);
      expect(calls[1].params.file).toBe(items[0].file);
      expect(queue.getItems()[0].attempt).toBe(2);
    });

    it('gives up after the automatic attempts and leaves a retryable failure', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('nf', 404, 'PHOTO_NOT_FOUND'));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      for (let attempt = 0; attempt <= MAX_AUTO_RETRIES; attempt += 1) {
        calls[attempt].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
        await vi.advanceTimersByTimeAsync(10_000);
      }
      expect(calls).toHaveLength(MAX_AUTO_RETRIES + 1);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'network', retryable: true } });
    });

    it('a failed check (still offline) is a manual-retry failure, not a silent re-POST', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('net', 0, 'NETWORK_ERROR'));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
      await vi.advanceTimersByTimeAsync(10_000);
      expect(calls).toHaveLength(1);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'network', retryable: true } });
    });

    it('an unreachable server (fetch rejects with a plain TypeError) is a network failure, not an "unexpected error"', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new TypeError('Failed to fetch'));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
      await vi.advanceTimersByTimeAsync(1_000);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'network', retryable: true } });
    });

    it('a real HTTP error answer of the check (e.g. 401) is reported as that error', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('auth', 401));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
      await vi.advanceTimersByTimeAsync(1_000);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'session_expired' } });
    });

    it('manual retry keeps the upload_id, resets the automatic budget and re-sends', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('net', 0, 'NETWORK_ERROR'));
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('net', 0, 'NETWORK_ERROR'));
      await vi.advanceTimersByTimeAsync(1_000);
      expect(state(queue)).toBe('failed');

      queue.retry(items[0].id);
      await tick();
      expect(calls).toHaveLength(2);
      expect(calls[1].uploadId).toBe(items[0].uploadId);
      expect(queue.getItems()[0]).toMatchObject({ state: 'uploading', error: null, attempt: 1 });
    });

    it('a BAD_RESPONSE (2xx with an unreadable body) is treated like a transport failure', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockResolvedValue(detail('B'));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('bad', 201, 'BAD_RESPONSE'));
      await tick();
      expect(fetchDetail).toHaveBeenCalledTimes(1);
      expect(state(queue)).toBe('done');
    });

    it('an HTTP error answer does NOT trigger the GET-first check', async () => {
      const { queue, calls, fetchDetail } = setup();
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('bad', 422, 'PHOTO_INVALID_IMAGE'));
      await tick();
      expect(fetchDetail).not.toHaveBeenCalled();
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'invalid_image', retryable: false } });
    });
  });

  describe('server busy (PHOTO_PROCESSING_BUSY)', () => {
    const busy = (seconds?: number) => new PhotoUploadError('busy', 503, 'PHOTO_PROCESSING_BUSY', null, seconds);

    it('retries once automatically after Retry-After, then leaves a retryable failure', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(busy(5));
      await tick();
      expect(state(queue)).toBe('queued');

      await vi.advanceTimersByTimeAsync(4_900);
      expect(calls).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(200);
      expect(calls).toHaveLength(2);
      expect(calls[1].uploadId).toBe(calls[0].uploadId);

      calls[1].reject(busy(5));
      await vi.advanceTimersByTimeAsync(60_000);
      expect(calls).toHaveLength(2);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { key: 'busy', retryable: true } });
    });

    it('caps a long Retry-After and defaults a missing one', async () => {
      const first = setup();
      first.queue.enqueue([file()], target, 'GALLERY');
      await tick();
      first.calls[0].reject(busy(300));
      await tick();
      await vi.advanceTimersByTimeAsync(BUSY_RETRY_CAP_SECONDS * 1000 - 100);
      expect(first.calls).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(200);
      expect(first.calls).toHaveLength(2);

      const second = setup();
      second.queue.enqueue([file()], target, 'GALLERY');
      await tick();
      second.calls[0].reject(busy());
      await tick();
      await vi.advanceTimersByTimeAsync(DEFAULT_BUSY_RETRY_SECONDS * 1000 - 100);
      expect(second.calls).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(200);
      expect(second.calls).toHaveLength(2);
    });

    it('does not block the lane: the next file is uploaded while a busy one waits', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(busy(20));
      await tick();
      expect(calls).toHaveLength(2);
      expect(calls[1].params.file.name).toBe('2.jpg');
    });
  });

  describe('identity conflicts, quota, gate', () => {
    it('offers "retry as new" only for identity conflicts and never silently', async () => {
      const { queue, calls } = setup();
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('c', 409, 'PHOTO_UPLOAD_ID_CONFLICT'));
      await tick();
      expect(calls).toHaveLength(1);
      expect(queue.getItems()[0]).toMatchObject({ state: 'failed', error: { retryable: false, retryAsNew: true } });

      queue.retry(items[0].id); // plain retry is refused for a conflict
      await tick();
      expect(calls).toHaveLength(1);

      queue.retryAsNew(items[0].id);
      await tick();
      expect(calls).toHaveLength(2);
      expect(calls[1].uploadId).not.toBe(items[0].uploadId);
      expect(queue.getItems()[0].uploadId).toBe(calls[1].uploadId);
    });

    it('retryAsNew is refused for a failure that does not allow it', async () => {
      const { queue, calls } = setup();
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('x', 422, 'PHOTO_INVALID_IMAGE'));
      await tick();
      queue.retryAsNew(items[0].id);
      queue.retry(items[0].id);
      await tick();
      expect(calls).toHaveLength(1);
    });

    it('quota exceeded stops the queue: the rest fails with the same reason and the host is told', async () => {
      const { queue, calls, onStopped } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg'), file('3.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('q', 409, 'PHOTO_STORAGE_QUOTA_EXCEEDED'));
      await tick();
      expect(calls).toHaveLength(1);
      expect(queue.getItems().map((i) => i.state)).toEqual(['failed', 'failed', 'failed']);
      expect(queue.getItems().every((i) => i.error?.key === 'quota_exceeded' && !i.error.retryable)).toBe(true);
      expect(onStopped).toHaveBeenCalledTimes(1);
    });

    it('uploads disabled fails everything as not retryable', async () => {
      const { queue, calls, onStopped } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('d', 503, 'PHOTO_UPLOADS_DISABLED'));
      await tick();
      expect(queue.getItems().map((i) => i.error?.key)).toEqual(['uploads_disabled', 'uploads_disabled']);
      expect(onStopped.mock.calls[0][0]).toMatchObject({ uploadsDisabled: true });
    });

    it('a vanished target asks the host to refetch its parent and does not stop the queue', async () => {
      const { queue, calls, onRefetch } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('nf', 404, 'ROOM_NOT_FOUND'));
      await tick();
      expect(onRefetch).toHaveBeenCalledWith('parent', expect.objectContaining({ state: 'failed' }));
      expect(calls).toHaveLength(2); // the next file still goes
    });

    it('a plain 401 stops the queue with a retryable session error', async () => {
      const { queue, calls } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('auth', 401));
      await tick();
      expect(queue.getItems().map((i) => i.error?.key)).toEqual(['session_expired', 'session_expired']);
      queue.retry(items[0].id);
      await tick();
      expect(calls).toHaveLength(2);
    });
  });

  describe('cancel and dismiss', () => {
    it('cancels a queued item without any request', async () => {
      const { queue, calls, previews } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      queue.cancel(items[1].id);
      expect(queue.getItems()[1].state).toBe('canceled');
      calls[0].resolve(uploadResponse('a'));
      await tick();
      expect(calls).toHaveLength(1);
      expect(previews.revoke).toHaveBeenCalledWith(expect.stringMatching(/^blob:/));
    });

    it('cancels the active upload: aborts the request, ignores its rejection, starts the next file', async () => {
      const { queue, calls, fetchDetail } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      queue.cancel(items[0].id);
      expect(calls[0].options.signal?.aborted).toBe(true);
      await tick();
      expect(queue.getItems()[0].state).toBe('canceled');
      expect(queue.getItems()[0].error).toBeNull();
      expect(fetchDetail).not.toHaveBeenCalled(); // an abort is not a network failure
      expect(calls).toHaveLength(2);
      expect(queue.getItems()[1].state).toBe('uploading');
    });

    it('a late success of a canceled upload does not resurrect it', async () => {
      const { queue, calls, onDone } = setup();
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      queue.cancel(items[0].id);
      calls[0].resolve(uploadResponse('late'));
      await tick();
      expect(queue.getItems()[0].state).toBe('canceled');
      expect(onDone).not.toHaveBeenCalled();
    });

    it('dismisses only finished rows and revokes their preview', async () => {
      const { queue, calls, previews } = setup();
      const { items } = queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      queue.dismiss(items[0].id); // still uploading: refused
      expect(queue.getItems()).toHaveLength(2);
      calls[0].reject(new PhotoUploadError('x', 422, 'PHOTO_INVALID_IMAGE'));
      await tick();
      queue.dismiss(items[0].id);
      expect(queue.getItems().map((i) => i.id)).toEqual([items[1].id]);
      expect(previews.revoke).toHaveBeenCalledWith('blob:1');
    });

    it('dismissDone removes only the finished uploads', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      calls[0].resolve(uploadResponse('a'));
      await tick();
      queue.dismissDone();
      expect(queue.getItems().map((i) => i.state)).toEqual(['uploading']);
    });

    it('never drops a failed row silently', async () => {
      const { queue, calls } = setup();
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].reject(new PhotoUploadError('x', 500, 'PHOTO_STORAGE_ERROR'));
      await vi.advanceTimersByTimeAsync(60_000);
      expect(queue.getItems()).toHaveLength(1);
      expect(state(queue)).toBe('failed');
    });
  });

  describe('foreground reconcile', () => {
    it('ends an in-flight item whose asset already exists on the server and aborts the dead request', async () => {
      const { queue, calls, fetchDetail, onDone } = setup();
      fetchDetail.mockResolvedValue(detail('R'));
      const { items } = queue.enqueue([file()], target, 'GALLERY');
      await tick();
      calls[0].options.onBytesSent?.();
      await queue.reconcile();
      expect(fetchDetail).toHaveBeenCalledWith(PROJECT, items[0].uploadId);
      expect(queue.getItems()[0].state).toBe('done');
      expect(calls[0].options.signal?.aborted).toBe(true);
      await tick();
      expect(onDone).toHaveBeenCalledTimes(1);
      expect(calls).toHaveLength(1);
    });

    it('does nothing when the server has no such asset yet (never a second concurrent POST)', async () => {
      const { queue, calls, fetchDetail } = setup();
      fetchDetail.mockRejectedValue(new ApiError('nf', 404, 'PHOTO_NOT_FOUND'));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      await queue.reconcile();
      expect(state(queue)).toBe('uploading');
      expect(calls).toHaveLength(1);
      expect(calls[0].options.signal?.aborted).toBe(false);
    });

    it('is a no-op without an active upload and joins a reconcile already running', async () => {
      const { queue, fetchDetail } = setup();
      await queue.reconcile();
      expect(fetchDetail).not.toHaveBeenCalled();

      fetchDetail.mockImplementation(() => new Promise(() => undefined));
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      void queue.reconcile();
      void queue.reconcile();
      await tick();
      expect(fetchDetail).toHaveBeenCalledTimes(1);
    });
  });

  describe('store API and lifecycle', () => {
    it('keeps the same snapshot instance until something changes and notifies subscribers', async () => {
      const { queue } = setup();
      const listener = vi.fn();
      const unsubscribe = queue.subscribe(listener);
      const before = queue.getItems();
      expect(queue.getItems()).toBe(before);
      queue.enqueue([file()], target, 'GALLERY');
      expect(queue.getItems()).not.toBe(before);
      expect(listener).toHaveBeenCalled();
      unsubscribe();
      listener.mockClear();
      await tick();
      queue.cancel(queue.getItems()[0].id);
      expect(listener).not.toHaveBeenCalled();
    });

    it('destroy aborts the active upload, revokes previews and stops everything', async () => {
      const { queue, calls, previews } = setup();
      queue.enqueue([file('1.jpg'), file('2.jpg')], target, 'GALLERY');
      await tick();
      queue.destroy();
      expect(calls[0].options.signal?.aborted).toBe(true);
      expect(previews.revoke).toHaveBeenCalledTimes(2);
      expect(queue.getItems()).toEqual([]);
      await tick();
      expect(calls).toHaveLength(1);
    });

    it('works without URL.createObjectURL (jsdom): no preview, no crash', async () => {
      const { queue, calls } = setup({ previews: undefined });
      queue.enqueue([file()], target, 'GALLERY');
      await tick();
      expect(queue.getItems()[0].previewUrl).toBeNull();
      expect(calls).toHaveLength(1);
    });
  });
});

describe('generateUploadId', () => {
  const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('produces a canonical lowercase UUIDv4', () => {
    expect(generateUploadId()).toMatch(V4);
  });

  it('falls back to getRandomValues when randomUUID is missing', () => {
    vi.stubGlobal('crypto', { getRandomValues: (bytes: Uint8Array) => bytes.fill(255) });
    expect(generateUploadId()).toMatch(V4);
  });

  it('falls back to Math.random without any crypto', () => {
    vi.stubGlobal('crypto', undefined);
    expect(generateUploadId()).toMatch(V4);
  });

  it('is unique across calls', () => {
    const ids = new Set(Array.from({ length: 200 }, () => generateUploadId()));
    expect(ids.size).toBe(200);
  });
});
