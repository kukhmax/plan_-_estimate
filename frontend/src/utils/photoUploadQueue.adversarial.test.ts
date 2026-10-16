import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { PhotoUploadError } from '../api/photos';
import { PhotoDetailResponse, PhotoTarget, PhotoUploadResponse } from '../types/photo';
import {
  PHOTO_QUEUE_LIMIT_BYTES,
  PhotoQueueStore,
  PhotoUploadQueue,
  StoredPhoto,
  StoredPhotoPatch,
  queueBytes,
} from './photoUploadQueue';

// Stage 19F — the photo queue under random treatment: photos taken, cancelled and closed, the signal coming and going, the application
// closed and opened again. Whatever happens: one upload at a time, never more than the limit waiting, what rests on the phone is exactly
// what is not finished, and when the signal stays every photo that was not cancelled reaches the server once.

const target: PhotoTarget = { projectId: 'p1', context: 'SURFACE', surfaceId: 's1', roomId: 'r1' };
const MB = 1024 * 1024;

function prng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function file(name: string, megabytes: number): File {
  const f = new File(['x'], name, { type: 'image/jpeg' });
  Object.defineProperty(f, 'size', { value: Math.round(megabytes * MB) });
  return f;
}

const uploaded = (id: string) => ({ asset: { id }, attachment: null, thumbnail_url: 't', display_url: 'd', urls_expire_at: '2099-01-01T00:00:00Z', storage: { state: 'OK' } }) as unknown as PhotoUploadResponse;
const detailOf = (id: string) => ({ asset: { id }, attachments: [], thumbnail_url: 't', display_url: 'd', urls_expire_at: null, annotations: [], annotation_limit: 10, outline_max_points: 120 }) as unknown as PhotoDetailResponse;

function world(rnd: () => number) {
  const records = new Map<string, StoredPhoto>();
  const files = new Map<string, File>();
  const server = new Set<string>(); // upload ids the server holds
  const sent: string[] = []; // every upload id the server was asked to take, in order
  const busyBefore = new Set<string>(); // the server says "busy" to a photo once (the queue tries again once by itself)
  const state = { online: true, active: 0, maxActive: 0, losses: 0, duplicates: 0 };

  const store: PhotoQueueStore = {
    put: async (item, f, thumb) => {
      records.set(item.id, { id: item.id, ownerId: 'o', uploadId: item.uploadId, target: item.target, source: item.source, name: f.name, type: f.type, lastModified: 0, size: f.size, thumb, createdAt: records.size + 1, state: 'queued', attempt: item.attempt, error: item.error });
      files.set(item.id, f);
    },
    update: async (id: string, patch: StoredPhotoPatch) => {
      const current = records.get(id);
      if (current) records.set(id, { ...current, ...patch });
    },
    remove: async (id: string) => {
      records.delete(id);
      files.delete(id);
    },
    loadFile: async (id: string) => files.get(id) ?? null,
  };

  const transport = {
    upload: (params: { uploadId: string }, options: { signal?: AbortSignal }) =>
      new Promise<PhotoUploadResponse>((resolve, reject) => {
        if (server.has(params.uploadId)) state.duplicates += 1; // the server had this photo already: it should have been asked first
        state.active += 1;
        state.maxActive = Math.max(state.maxActive, state.active);
        const finish = (settle: () => void) => {
          state.active -= 1;
          settle();
        };
        options.signal?.addEventListener('abort', () => finish(() => reject(new PhotoUploadError('canceled', 0, 'UPLOAD_ABORTED'))), { once: true });
        const fate = !state.online ? 'drop' : rnd() < 0.2 ? 'lost' : rnd() < 0.15 && !busyBefore.has(params.uploadId) ? 'busy' : 'ok';
        setTimeout(() => {
          if (options.signal?.aborted) return;
          if (fate === 'drop') return finish(() => reject(new PhotoUploadError('Network error', 0, 'NETWORK_ERROR')));
          sent.push(params.uploadId);
          server.add(params.uploadId);
          if (fate === 'lost') { state.losses += 1; return finish(() => reject(new PhotoUploadError('Network error', 0, 'NETWORK_ERROR'))); }
          if (fate === 'busy') { busyBefore.add(params.uploadId); server.delete(params.uploadId); return finish(() => reject(new PhotoUploadError('busy', 503, 'PHOTO_PROCESSING_BUSY', undefined, 1))); }
          finish(() => resolve(uploaded(params.uploadId)));
        }, 50);
      }),
    fetchDetail: async (_projectId: string, id: string) => {
      if (!state.online) throw new TypeError('Failed to fetch');
      if (!server.has(id)) throw new ApiError('not found', 404, 'PHOTO_NOT_FOUND');
      return detailOf(id);
    },
  };
  return { records, files, server, sent, state, store, transport };
}

const SEEDS = Array.from({ length: 60 }, (_, i) => 31 + i * 104729);

describe('the photo queue under random treatment (Stage 19F)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it.each(SEEDS)('seed %i', async (seed) => {
    const rnd = prng(seed);
    const w = world(rnd);
    let n = 0;
    const make = () =>
      new PhotoUploadQueue({
        transport: w.transport,
        store: w.store,
        previews: { create: () => null, revoke: () => {} },
        newId: () => `id-${seed}-${(n += 1)}`,
        canStart: () => w.state.online,
        maxAutoRetries: 50,
      });
    let queue = make();
    const taken = new Set<string>(); // ids of the photos the queue accepted
    const cancelled = new Set<string>();
    const tick = (ms = 0) => vi.advanceTimersByTimeAsync(ms);
    const items = () => queue.getItems();

    const check = async () => {
      await tick(0);
      expect(w.state.maxActive, 'one upload at a time').toBeLessThanOrEqual(1);
      expect(queueBytes(items()), 'waiting photos within the limit').toBeLessThanOrEqual(PHOTO_QUEUE_LIMIT_BYTES);
    };

    const steps = 25 + Math.floor(rnd() * 25);
    for (let i = 0; i < steps; i += 1) {
      const x = rnd();
      if (x < 0.35) {
        const count = 1 + Math.floor(rnd() * 3);
        const result = queue.enqueue(Array.from({ length: count }, (_, k) => file(`p${i}-${k}.jpg`, 1 + Math.floor(rnd() * 22))), target, 'GALLERY');
        result.items.forEach((it) => taken.add(it.id));
      } else if (x < 0.45) {
        const open = items().filter((it) => it.state === 'queued' || it.state === 'uploading' || it.state === 'processing');
        if (open.length) { const it = open[Math.floor(rnd() * open.length)]; cancelled.add(it.id); queue.cancel(it.id); }
      } else if (x < 0.52) {
        const finished = items().filter((it) => it.state === 'done' || it.state === 'failed' || it.state === 'canceled');
        if (finished.length) queue.dismiss(finished[Math.floor(rnd() * finished.length)].id);
      } else if (x < 0.65) {
        w.state.online = !w.state.online;
        queue.kick();
      } else if (x < 0.72) {
        // the application is closed and opened again: the queue in memory is gone, what rests on the phone comes back
        await tick(0);
        const resting = [...w.records.values()];
        queue.destroy();
        w.state.active = 0;
        queue = make();
        queue.restore(resting);
      } else {
        await tick(40 + Math.floor(rnd() * 400));
      }
      await check();
    }

    // the signal stays: everything that was not cancelled is sent
    w.state.online = true;
    queue.kick();
    for (let i = 0; i < 40; i += 1) await tick(500);
    await tick(0);

    expect(w.state.maxActive).toBeLessThanOrEqual(1);
    expect(w.state.duplicates, 'a photo the server already held was never sent again').toBe(0);
    const unfinished = items().filter((it) => it.state === 'queued' || it.state === 'uploading' || it.state === 'processing');
    expect(unfinished.map((it) => `${it.name}:${it.state}`), 'nothing is left waiting').toEqual([]);
    expect(items().filter((it) => it.state === 'failed').map((it) => `${it.name}:${it.error?.code}`), 'nothing failed').toEqual([]);
    // what rests on the phone is exactly what is not finished: here nothing (a done / cancelled photo is removed)
    const resting = [...w.records.keys()].filter((id) => !items().some((it) => it.id === id && (it.state === 'done' || it.state === 'canceled')));
    expect(resting, 'nothing is kept on the phone for a finished photo').toEqual([]);
    expect([...w.records.keys()], 'nothing is kept for a finished photo').toEqual([]);
    // every photo shown as done is on the server, and the server holds no photo twice (the same upload id is the same photo)
    for (const it of items().filter((x) => x.state === 'done')) expect(w.server.has(it.uploadId), it.name).toBe(true);
    expect(new Set(w.sent).size, 'one asset per upload id').toBe(w.server.size + [...w.sent].filter((id) => !w.server.has(id)).length);
  }, 60_000);
});
