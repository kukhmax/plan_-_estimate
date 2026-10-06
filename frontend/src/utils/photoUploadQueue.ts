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
// retry, GET-first retry protocol after a transport failure, foreground reconcile. Nothing is persisted (D2).

export const MAX_FILES_PER_SELECTION = 10;
/** Advisory client-side limit; the server stays the authority (25 000 000 canonical image bytes). */
export const PHOTO_MAX_UPLOAD_BYTES = 25_000_000;
export const PHOTO_ACCEPTED_TYPES: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];
/** Automatic re-POSTs after a transport failure whose GET-first check found nothing on the server. */
export const MAX_AUTO_RETRIES = 2;
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
  file: File;
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
}

export interface EnqueueResult {
  items: QueueItem[];
  /** Files beyond MAX_FILES_PER_SELECTION that were ignored. */
  ignored: number;
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

  constructor(options: PhotoQueueOptions) {
    this.options = options;
    this.previews = options.previews ?? defaultPreviews;
    this.maxAutoRetries = options.maxAutoRetries ?? MAX_AUTO_RETRIES;
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
    const created = accepted.map((file) => this.createItem(file, target, source));
    this.items = [...this.items, ...created];
    this.emit();
    this.pump();
    return { items: created, ignored: files.length - accepted.length };
  }

  cancel(id: string): void {
    const item = this.find(id);
    if (!item || !['queued', 'uploading', 'processing'].includes(item.state)) return;
    const wasActive = this.active?.itemId === id;
    this.revokePreview(item);
    this.patch(id, { state: 'canceled', previewUrl: null });
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
    });
    this.pump();
  }

  private pump(): void {
    if (this.destroyed || this.active) return;
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
    const params: UploadPhotoParams = {
      ...item.target,
      uploadId: item.uploadId,
      file: item.file,
      source: item.source,
    };
    try {
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
      this.pump();
    }
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
      this.fail(item.id, notThere ? failure : classifyPhotoError(lookup));
    }
  }

  private complete(item: QueueItem, result: QueueResult): void {
    this.revokePreview(item);
    this.patch(item.id, { state: 'done', progress: 1, error: null, result, previewUrl: null });
    const done = this.find(item.id);
    if (done) this.options.onDone?.(done);
  }

  private fail(id: string, info: PhotoErrorInfo): void {
    this.patch(id, { state: 'failed', error: info });
    const failed = this.find(id);
    if (failed && info.refetch) this.options.onRefetch?.(info.refetch, failed);
    if (info.stopsQueue) {
      this.items = this.items.map((item) =>
        item.state === 'queued' ? { ...item, state: 'failed', error: info } : item,
      );
      this.emit();
      this.options.onStopped?.(info);
    }
  }
}
