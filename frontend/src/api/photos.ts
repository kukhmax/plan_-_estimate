import { API_BASE, ApiError, apiRequest } from './http';
import {
  PhotoAttachPayload,
  PhotoAttachmentPatch,
  PhotoAttachmentRead,
  PhotoAssetRead,
  PhotoCaptureSource,
  PhotoCategory,
  PhotoCounts,
  PhotoDetailResponse,
  PhotoListParams,
  PhotoListResponse,
  PhotoStorageStatus,
  PhotoTarget,
  PhotoUploadResponse,
} from '../types/photo';

// JSON calls go through apiRequest. Uploads use a separate XHR transport (contract §5): apiRequest forces a
// JSON Content-Type when a body exists, which would break multipart, and fetch has no upload progress.

function photosPath(projectId: string): string {
  return `/api/projects/${projectId}/photos`;
}

function listQuery(params: PhotoListParams): string {
  const query = new URLSearchParams();
  if (params.context) query.set('context', params.context);
  if (params.roomId) query.set('room_id', params.roomId);
  if (params.surfaceId) query.set('surface_id', params.surfaceId);
  if (params.openingId) query.set('opening_id', params.openingId);
  if (params.inRoomId) query.set('in_room_id', params.inRoomId);
  if (params.inspectionId) query.set('inspection_id', params.inspectionId);
  if (params.questionId) query.set('question_id', params.questionId);
  if (params.findingId) query.set('finding_id', params.findingId);
  if (params.lineageId) query.set('lineage', params.lineageId);
  if (params.siteOnly) query.set('site_only', 'true');
  if (params.category) query.set('category', params.category);
  if (params.includeInReport !== undefined) query.set('include_in_report', String(params.includeInReport));
  if (params.archived !== undefined) query.set('archived', String(params.archived));
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.cursor) query.set('cursor', params.cursor);
  const text = query.toString();
  return text ? `?${text}` : '';
}

export function fetchPhotos(projectId: string, params: PhotoListParams = {}): Promise<PhotoListResponse> {
  return apiRequest(`${photosPath(projectId)}${listQuery(params)}`);
}

export function fetchPhoto(projectId: string, assetId: string): Promise<PhotoDetailResponse> {
  return apiRequest(`${photosPath(projectId)}/${assetId}`);
}

export function fetchPhotoCounts(projectId: string): Promise<PhotoCounts> {
  return apiRequest(`${photosPath(projectId)}/counts`);
}

export function fetchPhotoStorage(): Promise<PhotoStorageStatus> {
  return apiRequest('/api/photo-storage');
}

function attachmentPath(projectId: string, attachmentId: string): string {
  return `/api/projects/${projectId}/photo-attachments/${attachmentId}`;
}

export function patchPhotoAttachment(
  projectId: string,
  attachmentId: string,
  patch: PhotoAttachmentPatch,
): Promise<PhotoAttachmentRead> {
  return apiRequest(attachmentPath(projectId, attachmentId), { method: 'PATCH', body: JSON.stringify(patch) });
}

export function archivePhotoAttachment(projectId: string, attachmentId: string): Promise<PhotoAttachmentRead> {
  return apiRequest(`${attachmentPath(projectId, attachmentId)}/archive`, { method: 'POST' });
}

export function restorePhotoAttachment(projectId: string, attachmentId: string): Promise<PhotoAttachmentRead> {
  return apiRequest(`${attachmentPath(projectId, attachmentId)}/restore`, { method: 'POST' });
}

export function archivePhoto(projectId: string, assetId: string): Promise<PhotoAssetRead> {
  return apiRequest(`${photosPath(projectId)}/${assetId}/archive`, { method: 'POST' });
}

export function restorePhoto(projectId: string, assetId: string): Promise<PhotoAssetRead> {
  return apiRequest(`${photosPath(projectId)}/${assetId}/restore`, { method: 'POST' });
}

export function attachPhoto(
  projectId: string,
  assetId: string,
  payload: PhotoAttachPayload,
): Promise<PhotoAttachmentRead> {
  return apiRequest(`${photosPath(projectId)}/${assetId}/attachments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Upload transport
// ---------------------------------------------------------------------------

/** Transport-level failure codes (status 0): the request never produced an HTTP answer. */
export const PHOTO_NETWORK_ERROR = 'NETWORK_ERROR';
export const PHOTO_UPLOAD_STALLED = 'UPLOAD_STALLED';
export const PHOTO_UPLOAD_ABORTED = 'UPLOAD_ABORTED';
export const PHOTO_BAD_RESPONSE = 'BAD_RESPONSE';

/** No upload progress for this long → abort (mirrors the server's 60 s idle receive timeout). */
export const PHOTO_IDLE_TIMEOUT_MS = 60_000;
/** Bytes sent but no answer for this long → give up waiting; the GET-first retry protocol decides what happened. */
export const PHOTO_PROCESSING_TIMEOUT_MS = 120_000;

/** ApiError plus the `Retry-After` of a 503 (seconds), which `ApiError` does not carry. */
export class PhotoUploadError extends ApiError {
  readonly retryAfterSeconds?: number;

  constructor(message: string, status: number, code?: string, detail?: unknown, retryAfterSeconds?: number) {
    super(message, status, code, detail);
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export interface UploadPhotoParams extends PhotoTarget {
  /** Client-generated UUIDv4 = the asset id; stable across retries (backend idempotency). */
  uploadId: string;
  file: File;
  category?: PhotoCategory;
  caption?: string;
  includeInReport?: boolean;
  source?: PhotoCaptureSource;
}

export interface UploadPhotoOptions {
  signal?: AbortSignal;
  onProgress?: (loaded: number, total: number) => void;
  /** All request bytes were handed to the network; the server is now processing. */
  onBytesSent?: () => void;
  idleTimeoutMs?: number;
  processingTimeoutMs?: number;
}

export function buildUploadFormData(params: UploadPhotoParams): FormData {
  const form = new FormData();
  form.append('upload_id', params.uploadId);
  form.append('context', params.context);
  if (params.context === 'ROOM' && params.roomId) form.append('room_id', params.roomId);
  if (params.context === 'SURFACE' && params.surfaceId) form.append('surface_id', params.surfaceId);
  if (params.context === 'OPENING' && params.openingId) form.append('opening_id', params.openingId);
  if (params.context === 'INSPECTION' && params.inspectionId) form.append('inspection_id', params.inspectionId);
  if (params.context === 'INSPECTION' && params.inspectionId && params.questionId) form.append('question_id', params.questionId);
  if (params.context === 'FINDING' && params.findingId) form.append('finding_id', params.findingId);
  if (params.category) form.append('category', params.category);
  if (params.caption) form.append('caption', params.caption);
  if (params.includeInReport !== undefined) form.append('include_in_report', params.includeInReport ? 'true' : 'false');
  if (params.source) form.append('source', params.source);
  form.append('file', params.file, params.file.name);
  return form;
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number.parseInt(value, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined;
}

function httpError(xhr: XMLHttpRequest): PhotoUploadError {
  let detail: unknown = null;
  try {
    const payload: unknown = JSON.parse(xhr.responseText);
    if (payload && typeof payload === 'object' && 'detail' in payload) detail = payload.detail;
  } catch {
    // Non-JSON body (e.g. a proxy 413 page): the status alone identifies the failure.
  }
  let code: string | undefined;
  let message = `Request failed (${xhr.status})`;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const structured = detail as { code?: unknown; message?: unknown };
    if (typeof structured.code === 'string') code = structured.code;
    if (typeof structured.message === 'string') message = structured.message;
  }
  // The reverse proxy rejects an oversized request before the application can answer.
  if (!code && xhr.status === 413) code = 'PHOTO_TOO_LARGE';
  return new PhotoUploadError(
    message,
    xhr.status,
    code,
    detail,
    parseRetryAfter(xhr.getResponseHeader('Retry-After')),
  );
}

export function uploadPhoto(params: UploadPhotoParams, options: UploadPhotoOptions = {}): Promise<PhotoUploadResponse> {
  const { signal, onProgress, onBytesSent } = options;
  const idleMs = options.idleTimeoutMs ?? PHOTO_IDLE_TIMEOUT_MS;
  const processingMs = options.processingTimeoutMs ?? PHOTO_PROCESSING_TIMEOUT_MS;

  return new Promise<PhotoUploadResponse>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new PhotoUploadError('Upload canceled', 0, PHOTO_UPLOAD_ABORTED));
      return;
    }

    const xhr = new XMLHttpRequest();
    let settled = false;
    let watchdog: ReturnType<typeof setTimeout> | undefined;

    const clearWatchdog = () => {
      if (watchdog !== undefined) clearTimeout(watchdog);
      watchdog = undefined;
    };
    const finish = (settle: () => void) => {
      if (settled) return;
      settled = true;
      clearWatchdog();
      signal?.removeEventListener('abort', onAbort);
      settle();
    };
    const fail = (error: PhotoUploadError) => finish(() => reject(error));
    const arm = (ms: number) => {
      clearWatchdog();
      watchdog = setTimeout(() => {
        fail(new PhotoUploadError('Upload stalled', 0, PHOTO_UPLOAD_STALLED));
        xhr.abort();
      }, ms);
    };
    function onAbort() {
      fail(new PhotoUploadError('Upload canceled', 0, PHOTO_UPLOAD_ABORTED));
      xhr.abort();
    }

    xhr.open('POST', `${API_BASE}${photosPath(params.projectId)}`);
    const token = localStorage.getItem('access_token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    // No Content-Type here: the browser sets multipart/form-data with the boundary itself.

    xhr.upload.onprogress = (event) => {
      arm(idleMs);
      onProgress?.(event.loaded, event.lengthComputable ? event.total : params.file.size);
    };
    xhr.upload.onload = () => {
      onBytesSent?.();
      arm(processingMs);
    };
    xhr.onerror = () => fail(new PhotoUploadError('Network error', 0, PHOTO_NETWORK_ERROR));
    xhr.onabort = () => fail(new PhotoUploadError('Upload canceled', 0, PHOTO_UPLOAD_ABORTED));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const body = JSON.parse(xhr.responseText) as PhotoUploadResponse;
          finish(() => resolve(body));
        } catch {
          fail(new PhotoUploadError('Invalid server response', xhr.status, PHOTO_BAD_RESPONSE));
        }
        return;
      }
      fail(httpError(xhr));
    };

    signal?.addEventListener('abort', onAbort);
    arm(idleMs);
    xhr.send(buildUploadFormData(params));
  });
}
