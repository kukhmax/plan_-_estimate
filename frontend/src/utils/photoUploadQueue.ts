import { ApiError } from '../api/http';
import {
  PHOTO_UPLOAD_ABORTED,
  UploadPhotoOptions,
  UploadPhotoParams,
  PhotoUploadError,
} from '../api/photos';
import {
  PhotoAssetRead,
  PhotoAttachmentRead,
  PhotoCaptureSource,
  PhotoDetailResponse,
  PhotoTarget,
  PhotoUploadResponse,
} from '../types/photo';
import { PhotoErrorInfo, classifyPhotoError, isTransportFailure } from './photoErrors';

// UI-free upload queue (contract §5). One lane (concurrency 1), stable `upload_id` per file across every
// retry, GET-first retry protocol after a transport failure, foreground reconcile.
// Stage 19D: the unfinished photos are also kept on the phone (`store`), so a closed application or a missing signal
// no longer loses them; the queue waits for the signal (`canStart`) and refuses more than 200 MB of waiting photos.

export const MAX_FILES_PER_SELECTION = 10;
/** Advisory client-side limit; the server stays the authority (25 000 000 canonical image bytes). */
export const PHOTO_MAX_UPLOAD_BYTES = 25_000_000;
export const PHOTO_ACCEPTED_TYPES: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];
/** Automatic re-POSTs after a transport failure whose GET-first check found nothing on the server. */
export const MAX_AUTO_RETRIES = 2;
/** Photos waiting on the phone (not yet sent) may take this much room together (owner decision Q3). */
export const PHOTO_QUEUE_LIMIT_BYTES = 200 * 1024 * 1024;
/** From this much on the owner is warned that the queue is nearly full (80 %). */
export const PHOTO_QUEUE_WARN_BYTES = 160 * 1024 * 1024;
export const DEFAULT_BUSY_RETRY_SECONDS = 3;
export const BUSY_RETRY_CAP_SECONDS = 30;
const AUTO_RETRY_BACKOFF_MS = 2_000;

export type QueueItemState = 'queued' | 'uploading' | 'processing' | 'done' | 'failed' | 'canceled';

export interface QueueResult {
  asset: PhotoAssetRead;
  attachment: PhotoAttachmentRead | null;
  thumbnailUrl: string | null;
  displayUrl: string | null;
  urlsExpireAt: string | null;
}

export interface QueueItem {
  /** Stable local key (list keys, cancel / dismiss); never sent to the server. */
  id: string;
  /** Idempotency key sent as `upload_id` (= asset id); reused by every retry, replaced only by retryAsNew. */
  uploadId: string;
  /** Null while the bytes rest in the phone's storage only (after a restart, or to free memory); loaded when the upload starts. */
  file: File | null;
  name: string;
  size: number;
  target: PhotoTarget;
  source: PhotoCaptureSource;
  state: QueueItemState;
  /** 0..1 of the request bytes handed to the network. */
  progress: number;
  /** Number of POSTs started for the current uploadId. */
  attempt: number;
  previewUrl: string | null;
  error: PhotoErrorInfo | null;
  result: QueueResult | null;
  /** Earliest time (ms epoch) the item may start; used for the automatic busy / network retries. */
  notBefore: number;
  networkRetries: number;
  busyRetried: boolean;
  /** The server may already have this photo (a POST was started before the application closed or the signal went): ask first. */
  verify: boolean;
  /** The token was renewed once for this run. */
  authRetried: boolean;
  /** The photo could not be written to the phone's storage: it is sent in this session only. */
  saveFailed: boolean;
}

/** What the phone keeps about an unfinished photo (its bytes are stored next to it, under the same id). */
export interface StoredPhoto {
  id: string;
  ownerId: string;
  uploadId: string;
  target: PhotoTarget;
  source: PhotoCaptureSource;
  name: string;
  type: string;
  lastModified: number;
  size: number;
  createdAt: number;
  state: 'queued' | 'failed';
  /** A small picture (data URL) so that the row shows the photo after a restart; null where it could not be drawn. */
  thumb?: string | null;
  /** POSTs started for the current uploadId; above 0 means the server may have the photo already. */
  attempt: number;
  error: PhotoErrorInfo | null;
}

export type StoredPhotoPatch = Partial<Pick<StoredPhoto, 'uploadId' | 'state' | 'attempt' | 'error'>>;

/** Where unfinished photos rest between sessions (IndexedDB in the application, a fake in tests). */
export interface PhotoQueueStore {
  put(item: QueueItem, file: File, thumb: string | null): Promise<void>;
  update(id: string, patch: StoredPhotoPatch): Promise<void>;
  remove(id: string): Promise<void>;
  loadFile(id: string): Promise<File | null>;
}

export interface PhotoQueueTransport {
  upload(params: UploadPhotoParams, options: UploadPhotoOptions): Promise<PhotoUploadResponse>;
  fetchDetail(projectId: string, assetId: string): Promise<PhotoDetailResponse>;
}

export interface PhotoQueuePreviews {
  create(file: File): string | null;
  revoke(url: string): void;
}

export interface PhotoQueueOptions {
  transport: PhotoQueueTransport;
  newId?: () => string;
  previews?: PhotoQueuePreviews;
  maxAutoRetries?: number;
  /** Called once per item that reached `done` (host refetches the list and adjusts counts). */
  onDone?: (item: QueueItem) => void;
  /** Called when a failure asks the host to refetch ('parent' list of targets, or the photo 'list'). */
  onRefetch?: (what: 'parent' | 'list', item: QueueItem) => void;
  /** Called when the server gate / quota stops the queue (host updates storage status). */
  onStopped?: (info: PhotoErrorInfo) => void;
  /** Where unfinished photos are kept; without it the queue lives in memory only. */
  store?: PhotoQueueStore;
  /** False while there is no signal, or older changes still have to reach the server first (a photo may belong to them). */
  canStart?: () => boolean;
  /** The token expired: sign in again; true when a new token is in place. */
  refreshSession?: () => Promise<boolean>;
  limitBytes?: number;
  /** Draws the small picture kept with a waiting photo (Stage 19E); nothing is drawn without it. */
  thumbnail?: (file: File) => Promise<string | null>;
}

export interface EnqueueResult {
  items: QueueItem[];
  /** Files beyond MAX_FILES_PER_SELECTION that were ignored. */
  ignored: number;
  /** Files left out because the waiting photos would take more than the limit. */
  rejected: number;
}

/** Bytes taken by the photos that still have to be sent (a failed one stays until the owner closes it). */
export function queueBytes(items: readonly QueueItem[]): number {
  return items
    .filter((item) => item.state === 'queued' || item.state === 'uploading' || item.state === 'processing' || item.state === 'failed')
    .reduce((sum, item) => sum + item.size, 0);
}

/** RFC 4122 v4; `crypto.randomUUID` where available, `getRandomValues` otherwise. */
export function generateUploadId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const defaultPreviews: PhotoQueuePreviews = {
  create: (file) => (typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null),
  revoke: (url) => {
    if (typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url);
  },
};

function resultFromUpload(response: PhotoUploadResponse): QueueResult {
  return {
    asset: response.asset,
    attachment: response.attachment,
    thumbnailUrl: response.thumbnail_url,
    displayUrl: response.display_url,
    urlsExpireAt: response.urls_expire_at,
  };
}

function resultFromDetail(detail: PhotoDetailResponse): QueueResult {
  // The upload's own attachment is the first one in creation order (detail contract).
  return {
    asset: detail.asset,
    attachment: detail.attachments[0] ?? null,
    thumbnailUrl: detail.thumbnail_url,
    displayUrl: detail.display_url,
    urlsExpireAt: detail.urls_expire_at,
  };
}

interface ActiveRun {
  itemId: string;
  controller: AbortController;
}

export class PhotoUploadQueue {
  private items: QueueItem[] = [];
  private readonly listeners = new Set<() => void>();
  private active: ActiveRun | null = null;
  private pumpTimer: ReturnType<typeof setTimeout> | undefined;
  private reconciling = false;
  private destroyed = false;
  private counter = 0;
  private readonly options: PhotoQueueOptions;
  private readonly previews: PhotoQueuePreviews;
  private readonly maxAutoRetries: number;
  private readonly limitBytes: number;
  /** Writes to the phone's storage go one after another, so a removal never overtakes the write before it. */
  private storeChain: Promise<void> = Promise.resolve();

  constructor(options: PhotoQueueOptions) {
    this.options = options;
    this.previews = options.previews ?? defaultPreviews;
    this.maxAutoRetries = options.maxAutoRetries ?? MAX_AUTO_RETRIES;
    this.limitBytes = options.limitBytes ?? PHOTO_QUEUE_LIMIT_BYTES;
  }

  // ---- external-store API (useSyncExternalStore) ----

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** Immutable snapshot: the same array instance until something changes. */
  getItems = (): readonly QueueItem[] => this.items;

  // ---- commands ----

  enqueue(files: readonly File[], target: PhotoTarget, source: PhotoCaptureSource): EnqueueResult {
    const accepted = files.slice(0, MAX_FILES_PER_SELECTION);
    const created: QueueItem[] = [];
    let used = queueBytes(this.items);
    let rejected = 0;
    for (const file of accepted) {
      const item = this.createItem(file, target, source);
      if (item.state === 'queued') {
        if (used + item.size > this.limitBytes) {
          rejected += 1;
          this.revokePreview(item);
          continue;
        }
        used += item.size;
      }
      created.push(item);
    }
    this.items = [...this.items, ...created];
    this.emit();
    created.forEach((item) => {
      if (item.state === 'queued' && item.file) this.keep(item, item.file);
    });
    this.pump();
    return { items: created, ignored: files.length - accepted.length, rejected };
  }

  /**
   * Puts back the photos the phone kept from an earlier session. Their bytes stay in storage until the upload starts, so a
   * long queue does not fill the memory.
   */
  restore(records: readonly StoredPhoto[]): void {
    if (this.destroyed) return;
    const known = new Set(this.items.map((item) => item.id));
    const back = [...records]
      .filter((record) => !known.has(record.id))
      .sort((a, b) => a.createdAt - b.createdAt)
      .map<QueueItem>((record) => ({
        id: record.id,
        uploadId: record.uploadId,
        file: null,
        name: record.name,
        size: record.size,
        target: record.target,
        source: record.source,
        state: record.state,
        progress: 0,
        attempt: record.attempt,
        previewUrl: record.thumb ?? null, // a data URL: needs no revoking
        error: record.error,
        result: null,
        notBefore: 0,
        networkRetries: 0,
        busyRetried: false,
        verify: record.attempt > 0,
        authRetried: false,
        saveFailed: false,
      }));
    if (back.length === 0) return;
    this.items = [...back, ...this.items];
    this.emit();
    this.pump();
  }

  /** The signal came back, or the older changes reached the server: try to start. */
  kick(): void {
    this.pump();
  }

  cancel(id: string): void {
    const item = this.find(id);
    if (!item || !['queued', 'uploading', 'processing'].includes(item.state)) return;
    const wasActive = this.active?.itemId === id;
    this.revokePreview(item);
    this.patch(id, { state: 'canceled', previewUrl: null, file: null });
    this.forget(id);
    if (wasActive) this.active?.controller.abort();
  }

  /** Same upload_id, same File (backend idempotency). Only for a failure the table marks retryable. */
  retry(id: string): void {
    const item = this.find(id);
    if (!item || item.state !== 'failed' || !item.error?.retryable) return;
    this.requeue(item, item.uploadId);
  }

  /** New upload_id: only on the user's explicit action after an identity / storage conflict. */
  retryAsNew(id: string): void {
    const item = this.find(id);
    if (!item || item.state !== 'failed' || !item.error?.retryAsNew) return;
    this.requeue(item, (this.options.newId ?? generateUploadId)());
  }

  dismiss(id: string): void {
    const item = this.find(id);
    if (!item || !['done', 'failed', 'canceled'].includes(item.state)) return;
    this.revokePreview(item);
    this.items = this.items.filter((candidate) => candidate.id !== id);
    this.forget(id); // a failed photo is still kept until the owner closes it
    this.emit();
  }

  /** Remove every finished (done) row, e.g. after the list refetch put them into the grid. */
  dismissDone(): void {
    const done = this.items.filter((item) => item.state === 'done');
    if (done.length === 0) return;
    done.forEach((item) => this.revokePreview(item));
    this.items = this.items.filter((item) => item.state !== 'done');
    this.emit();
  }

  /**
   * Foreground / online: the WebView may have suspended JS mid-upload, so ask the server what it has for the
   * in-flight upload_id. A READY asset ends the item; anything else leaves it to the transport's own watchdog
   * (never a second concurrent POST).
   */
  async reconcile(): Promise<void> {
    const run = this.active;
    if (!run || this.reconciling || this.destroyed) return;
    const item = this.find(run.itemId);
    if (!item || (item.state !== 'uploading' && item.state !== 'processing')) return;
    this.reconciling = true;
    try {
      const detail = await this.options.transport.fetchDetail(item.target.projectId, item.uploadId);
      const current = this.find(run.itemId);
      if (this.active === run && current && (current.state === 'uploading' || current.state === 'processing')) {
        this.complete(current, resultFromDetail(detail));
        run.controller.abort();
      }
    } catch {
      // Not there yet (404) or still offline: the in-flight request / watchdog remains the source of truth.
    } finally {
      this.reconciling = false;
    }
  }

  destroy(): void {
    this.destroyed = true;
    if (this.pumpTimer !== undefined) clearTimeout(this.pumpTimer);
    this.active?.controller.abort();
    this.items.forEach((item) => this.revokePreview(item));
    this.items = [];
    this.listeners.clear();
  }

  // ---- internals ----

  private createItem(file: File, target: PhotoTarget, source: PhotoCaptureSource): QueueItem {
    this.counter += 1;
    const base: QueueItem = {
      id: `q${this.counter}-${(this.options.newId ?? generateUploadId)()}`,
      uploadId: (this.options.newId ?? generateUploadId)(),
      file,
      name: file.name,
      size: file.size,
      target,
      source,
      state: 'queued',
      progress: 0,
      attempt: 0,
      previewUrl: null,
      error: null,
      result: null,
      notBefore: 0,
      networkRetries: 0,
      busyRetried: false,
      verify: false,
      authRetried: false,
      saveFailed: false,
    };
    // Local advisory checks: no request is made for an obviously unusable file. An empty MIME (some
    // WebViews omit it for camera files) is left to the server, which never trusts the MIME anyway.
    const type = file.type.toLowerCase();
    if (type !== '' && !PHOTO_ACCEPTED_TYPES.includes(type)) {
      return { ...base, state: 'failed', error: classifyPhotoError(new ApiError('unsupported', 415, 'PHOTO_UNSUPPORTED_FORMAT')) };
    }
    if (file.size > PHOTO_MAX_UPLOAD_BYTES) {
      return { ...base, state: 'failed', error: classifyPhotoError(new ApiError('too large', 413, 'PHOTO_TOO_LARGE')) };
    }
    return { ...base, previewUrl: this.previews.create(file) };
  }

  private find(id: string): QueueItem | undefined {
    return this.items.find((item) => item.id === id);
  }

  private patch(id: string, changes: Partial<QueueItem>): void {
    this.items = this.items.map((item) => (item.id === id ? { ...item, ...changes } : item));
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((listener) => listener());
  }

  private revokePreview(item: QueueItem): void {
    if (item.previewUrl) this.previews.revoke(item.previewUrl);
  }

  // ---- the phone's storage (Stage 19D) ----

  /** Queues a write to the store; a failure is shown on the row (the photo is then sent in this session only). */
  private storeStep(step: (store: PhotoQueueStore) => Promise<void>, onError?: () => void): void {
    const store = this.options.store;
    if (!store) return;
    this.storeChain = this.storeChain
      .then(() => step(store))
      .catch((error: unknown) => {
        console.warn('[photos] the phone could not keep a photo', error);
        onError?.();
      });
  }

  private keep(item: QueueItem, file: File): void {
    this.storeStep(
      async (store) => {
        let thumb: string | null = null;
        try {
          thumb = (await this.options.thumbnail?.(file)) ?? null;
        } catch {
          thumb = null; // the small picture is a convenience: the photo is kept without it
        }
        await store.put(item, file, thumb);
      },
      () => {
        if (this.find(item.id)) this.patch(item.id, { saveFailed: true });
      },
    );
  }

  private save(id: string, patch: StoredPhotoPatch): void {
    this.storeStep((store) => store.update(id, patch));
  }

  private forget(id: string): void {
    this.storeStep((store) => store.remove(id));
  }

  /** The bytes of an item: in memory, or from the phone's storage (a restored photo). */
  private async bytesOf(item: QueueItem): Promise<File | null> {
    if (item.file) return item.file;
    const store = this.options.store;
    if (!store) return null;
    await this.storeChain; // a write that is still on its way
    try {
      return await store.loadFile(item.id);
    } catch (error) {
      console.warn('[photos] the photo could not be read from the phone', error);
      return null;
    }
  }

  private canStart(): boolean {
    return this.options.canStart ? this.options.canStart() : true;
  }

  private requeue(item: QueueItem, uploadId: string): void {
    this.patch(item.id, {
      uploadId,
      state: 'queued',
      progress: 0,
      attempt: 0,
      error: null,
      notBefore: 0,
      networkRetries: 0,
      busyRetried: false,
      authRetried: false,
      verify: false,
    });
    this.save(item.id, { uploadId, state: 'queued', attempt: 0, error: null });
    this.pump();
  }

  private pump(): void {
    if (this.destroyed || this.active) return;
    if (!this.canStart()) return; // no signal, or older changes first: `kick()` is called when that changes
    if (this.pumpTimer !== undefined) {
      clearTimeout(this.pumpTimer);
      this.pumpTimer = undefined;
    }
    const now = Date.now();
    const queued = this.items.filter((item) => item.state === 'queued');
    const ready = queued.find((item) => item.notBefore <= now);
    if (ready) {
      void this.run(ready);
      return;
    }
    if (queued.length > 0) {
      const next = Math.min(...queued.map((item) => item.notBefore));
      this.pumpTimer = setTimeout(() => {
        this.pumpTimer = undefined;
        this.pump();
      }, Math.max(0, next - now));
    }
  }

  private async run(item: QueueItem): Promise<void> {
    const run: ActiveRun = { itemId: item.id, controller: new AbortController() };
    this.active = run;
    this.patch(item.id, { state: 'uploading', progress: 0, attempt: item.attempt + 1, error: null });
    this.save(item.id, { attempt: item.attempt + 1 });
    try {
      const file = await this.bytesOf(item);
      if (this.active !== run || this.find(item.id)?.state !== 'uploading') return; // canceled meanwhile
      if (!file) {
        // The phone no longer has the photo (its storage was cleared): nothing to send.
        this.fail(item.id, classifyPhotoError(new ApiError('photo is gone', 410, 'PHOTO_GONE_FROM_PHONE')));
        return;
      }
      if (item.verify && (await this.alreadyOnServer(item, run))) return;
      if (this.active !== run || this.find(item.id)?.state !== 'uploading') return;
      const params: UploadPhotoParams = {
        ...item.target,
        uploadId: item.uploadId,
        file,
        source: item.source,
      };
      const response = await this.options.transport.upload(params, {
        signal: run.controller.signal,
        onProgress: (loaded, total) => {
          if (this.active !== run) return;
          const current = this.find(item.id);
          if (current?.state === 'uploading' && total > 0) this.patch(item.id, { progress: Math.min(1, loaded / total) });
        },
        onBytesSent: () => {
          if (this.active !== run) return;
          const current = this.find(item.id);
          if (current?.state === 'uploading') this.patch(item.id, { state: 'processing', progress: 1 });
        },
      });
      const current = this.find(item.id);
      if (this.active === run && current && (current.state === 'uploading' || current.state === 'processing')) {
        this.complete(current, resultFromUpload(response));
      }
    } catch (error) {
      if (this.active === run) await this.handleFailure(item.id, error);
    } finally {
      if (this.active === run) this.active = null;
      this.releaseMemory(item.id);
      this.pump();
    }
  }

  /** Photos that rest on the phone need not stay in memory as well. */
  private releaseMemory(id: string): void {
    const current = this.find(id);
    if (current && current.file && !current.saveFailed && this.options.store && (current.state === 'queued' || current.state === 'failed')) {
      this.patch(id, { file: null });
    }
  }

  /**
   * GET-first for a photo whose POST may have reached the server before the application closed or the signal went.
   * True when the photo is there (the item is done); a missing signal puts the item back to wait.
   */
  private async alreadyOnServer(item: QueueItem, run: ActiveRun): Promise<boolean> {
    try {
      const detail = await this.options.transport.fetchDetail(item.target.projectId, item.uploadId);
      const current = this.find(item.id);
      if (this.active === run && current && current.state === 'uploading') this.complete(current, resultFromDetail(detail));
      return true;
    } catch (lookup) {
      const current = this.find(item.id);
      if (!current || current.state !== 'uploading') return true; // canceled meanwhile
      if (lookup instanceof ApiError && lookup.status !== 0) {
        this.patch(item.id, { verify: false }); // the server answered (404 …): the photo is not there, send it
        return false;
      }
      this.waitForSignal(item.id);
      return true;
    }
  }

  /** No answer at all: it is the connection. The item waits (nothing is counted against it) until `kick()`. */
  private waitForSignal(id: string): void {
    this.patch(id, { state: 'queued', progress: 0, verify: true });
  }

  private async handleFailure(id: string, error: unknown): Promise<void> {
    const current = this.find(id);
    if (!current || (current.state !== 'uploading' && current.state !== 'processing')) return; // canceled / completed meanwhile
    if (error instanceof ApiError && error.code === PHOTO_UPLOAD_ABORTED) return;

    if (isTransportFailure(error)) {
      await this.reconcileAfterTransportFailure(current, error);
      return;
    }
    const info = classifyPhotoError(error);
    if (info.code === 'HTTP_401' && !current.authRetried && this.options.refreshSession) {
      // The token expired while the photo waited on the phone: sign in again and send it once more.
      this.patch(id, { authRetried: true });
      if (await this.options.refreshSession()) {
        this.patch(id, { state: 'queued', progress: 0, notBefore: 0 });
        return;
      }
    }
    if (info.code === 'PHOTO_PROCESSING_BUSY' && !current.busyRetried) {
      const requested = error instanceof PhotoUploadError ? error.retryAfterSeconds : undefined;
      const seconds = Math.min(requested ?? DEFAULT_BUSY_RETRY_SECONDS, BUSY_RETRY_CAP_SECONDS);
      this.patch(id, { state: 'queued', progress: 0, busyRetried: true, notBefore: Date.now() + seconds * 1000 });
      return;
    }
    this.fail(id, info);
  }

  /** GET-first (contract §9): 200 → done; 404 → re-POST the same upload_id; anything else → manual retry. */
  private async reconcileAfterTransportFailure(item: QueueItem, error: unknown): Promise<void> {
    const failure = classifyPhotoError(error);
    try {
      const detail = await this.options.transport.fetchDetail(item.target.projectId, item.uploadId);
      const current = this.find(item.id);
      if (current && (current.state === 'uploading' || current.state === 'processing')) {
        this.complete(current, resultFromDetail(detail));
      }
      return;
    } catch (lookup) {
      const current = this.find(item.id);
      if (!current || (current.state !== 'uploading' && current.state !== 'processing')) return;
      const notThere = lookup instanceof ApiError && lookup.status === 404;
      if (notThere && current.networkRetries < this.maxAutoRetries) {
        const retries = current.networkRetries + 1;
        this.patch(item.id, {
          state: 'queued',
          progress: 0,
          networkRetries: retries,
          notBefore: Date.now() + AUTO_RETRY_BACKOFF_MS * retries,
        });
        return;
      }
      // The check itself failed: a real HTTP answer (e.g. 401 / 5xx) is reported as such; no answer at all — `fetch`
      // rejects with a plain TypeError when the server is unreachable — keeps the transport failure that started this.
      const answered = lookup instanceof ApiError && lookup.status !== 0;
      if (!answered && !notThere && !this.canStart()) {
        this.waitForSignal(item.id); // the connection is gone: the photo waits on the phone for it to return
        return;
      }
      this.fail(item.id, notThere || !answered ? failure : classifyPhotoError(lookup));
    }
  }

  private complete(item: QueueItem, result: QueueResult): void {
    this.revokePreview(item);
    this.patch(item.id, { state: 'done', progress: 1, error: null, result, previewUrl: null, file: null });
    this.forget(item.id);
    const done = this.find(item.id);
    if (done) this.options.onDone?.(done);
  }

  private fail(id: string, info: PhotoErrorInfo): void {
    this.patch(id, { state: 'failed', error: info });
    this.save(id, { state: 'failed', error: info });
    const failed = this.find(id);
    if (failed && info.refetch) this.options.onRefetch?.(info.refetch, failed);
    if (info.stopsQueue) {
      const stopped = this.items.filter((item) => item.state === 'queued');
      this.items = this.items.map((item) =>
        item.state === 'queued' ? { ...item, state: 'failed', error: info } : item,
      );
      stopped.forEach((item) => this.save(item.id, { state: 'failed', error: info }));
      this.emit();
      this.options.onStopped?.(info);
    }
  }
}
