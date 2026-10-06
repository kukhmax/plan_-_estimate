import pl from '../locales/pl.json';
import { ApiError } from '../api/http';

// Single mapping of backend photo error codes to UI behaviour (contract §6). The UI shows localized strings
// chosen by CODE (`t.photos.errors[key]`); the backend's English `message` is never displayed.

export type PhotoErrorKey = keyof typeof pl.photos.errors;

export interface PhotoErrorInfo {
  /** Backend (or transport) code; 'HTTP_<status>' / 'UNKNOWN' when none was supplied. */
  code: string;
  key: PhotoErrorKey;
  /** The user may retry the same request (same upload_id). */
  retryable: boolean;
  /** The user may retry with a NEW upload_id (explicit action only, never silent). */
  retryAsNew: boolean;
  /** Remaining queued uploads cannot succeed either: fail them with the same reason. */
  stopsQueue: boolean;
  /** The server gate is closed: hide upload controls and show the neutral note. */
  uploadsDisabled: boolean;
  /** What the host should refetch after this error. */
  refetch: 'parent' | 'list' | null;
}

const NO_STATUS_CODES = new Set(['NETWORK_ERROR', 'UPLOAD_STALLED', 'UPLOAD_ABORTED', 'BAD_RESPONSE']);

function info(
  code: string,
  key: PhotoErrorKey,
  overrides: Partial<Omit<PhotoErrorInfo, 'code' | 'key'>> = {},
): PhotoErrorInfo {
  return {
    code,
    key,
    retryable: false,
    retryAsNew: false,
    stopsQueue: false,
    uploadsDisabled: false,
    refetch: null,
    ...overrides,
  };
}

function byCode(code: string): PhotoErrorInfo | null {
  switch (code) {
    case 'PHOTO_UPLOADS_DISABLED':
      return info(code, 'uploads_disabled', { stopsQueue: true, uploadsDisabled: true });
    case 'PHOTO_STORAGE_QUOTA_EXCEEDED':
      return info(code, 'quota_exceeded', { stopsQueue: true });
    case 'PHOTO_TOO_LARGE':
      return info(code, 'too_large');
    case 'PHOTO_UNSUPPORTED_FORMAT':
      return info(code, 'unsupported_format');
    case 'PHOTO_INVALID_IMAGE':
    case 'PHOTO_TOO_MANY_PIXELS':
    case 'PHOTO_ANIMATED_NOT_SUPPORTED':
      return info(code, 'invalid_image');
    case 'PHOTO_UPLOAD_MALFORMED':
    case 'PHOTO_ATTACHMENT_INVALID':
    case 'PHOTO_CONTEXT_NOT_SUPPORTED':
      return info(code, 'generic');
    case 'PROJECT_NOT_FOUND':
    case 'ROOM_NOT_FOUND':
    case 'SURFACE_NOT_FOUND':
    case 'OPENING_NOT_FOUND':
      return info(code, 'target_not_found', { refetch: 'parent' });
    case 'PHOTO_UPLOAD_ID_CONFLICT':
    case 'PHOTO_UPLOAD_RESUME_MISMATCH':
    case 'PHOTO_OBJECT_CONFLICT':
      return info(code, 'conflict', { retryAsNew: true });
    case 'PHOTO_PROCESSING_BUSY':
      return info(code, 'busy', { retryable: true });
    case 'PHOTO_STORAGE_UNAVAILABLE':
    case 'PHOTO_STORAGE_ERROR':
      return info(code, 'storage_unavailable', { retryable: true });
    case 'NETWORK_ERROR':
    case 'UPLOAD_STALLED':
    case 'UPLOAD_ABORTED':
    case 'BAD_RESPONSE':
      return info(code, 'network', { retryable: true });
    case 'PHOTO_NOT_FOUND':
    case 'PHOTO_ATTACHMENT_NOT_FOUND':
      return info(code, 'not_found', { refetch: 'list' });
    case 'PHOTO_ATTACHMENT_DUPLICATE':
      return info(code, 'duplicate_attachment');
    case 'PHOTO_CURSOR_INVALID':
      return info(code, 'generic', { retryable: true, refetch: 'list' });
    default:
      return null;
  }
}

export function classifyPhotoError(error: unknown): PhotoErrorInfo {
  if (!(error instanceof ApiError)) return info('UNKNOWN', 'unknown', { retryable: true });
  if (error.code) {
    const known = byCode(error.code);
    if (known) return known;
  }
  // No (known) code: fall back to the HTTP status (e.g. a proxy page).
  if (error.status === 401) return info('HTTP_401', 'session_expired', { retryable: true, stopsQueue: true });
  if (error.status === 413) return info('PHOTO_TOO_LARGE', 'too_large');
  if (error.status === 415) return info('PHOTO_UNSUPPORTED_FORMAT', 'unsupported_format');
  if (error.status === 0) return info(error.code ?? 'NETWORK_ERROR', 'network', { retryable: true });
  if (error.status >= 500) return info(`HTTP_${error.status}`, 'storage_unavailable', { retryable: true });
  return info(error.code ?? `HTTP_${error.status}`, 'unknown');
}

/** True when the failure happened below HTTP (no answer): the outcome on the server is unknown. */
export function isTransportFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.status === 0 || (error.code !== undefined && NO_STATUS_CODES.has(error.code));
}
