import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/http';
import { classifyPhotoError, isTransportFailure } from './photoErrors';

const err = (status: number, code?: string) => new ApiError('x', status, code);

describe('classifyPhotoError (contract §6 table)', () => {
  // [status, code, key, retryable, retryAsNew, stopsQueue, uploadsDisabled, refetch]
  const rows: Array<[number, string, string, boolean, boolean, boolean, boolean, string | null]> = [
    [503, 'PHOTO_UPLOADS_DISABLED', 'uploads_disabled', false, false, true, true, null],
    [409, 'PHOTO_STORAGE_QUOTA_EXCEEDED', 'quota_exceeded', false, false, true, false, null],
    [413, 'PHOTO_TOO_LARGE', 'too_large', false, false, false, false, null],
    [415, 'PHOTO_UNSUPPORTED_FORMAT', 'unsupported_format', false, false, false, false, null],
    [422, 'PHOTO_INVALID_IMAGE', 'invalid_image', false, false, false, false, null],
    [422, 'PHOTO_TOO_MANY_PIXELS', 'invalid_image', false, false, false, false, null],
    [422, 'PHOTO_ANIMATED_NOT_SUPPORTED', 'invalid_image', false, false, false, false, null],
    [422, 'PHOTO_UPLOAD_MALFORMED', 'generic', false, false, false, false, null],
    [422, 'PHOTO_ATTACHMENT_INVALID', 'generic', false, false, false, false, null],
    [422, 'PHOTO_CONTEXT_NOT_SUPPORTED', 'generic', false, false, false, false, null],
    [404, 'PROJECT_NOT_FOUND', 'target_not_found', false, false, false, false, 'parent'],
    [404, 'ROOM_NOT_FOUND', 'target_not_found', false, false, false, false, 'parent'],
    [404, 'SURFACE_NOT_FOUND', 'target_not_found', false, false, false, false, 'parent'],
    [404, 'OPENING_NOT_FOUND', 'target_not_found', false, false, false, false, 'parent'],
    [409, 'PHOTO_ANNOTATION_LIMIT_REACHED', 'marker_limit', false, false, false, false, null],
    [409, 'PHOTO_ANNOTATION_READ_ONLY', 'marker_read_only', false, false, false, false, null],
    [422, 'PHOTO_ANNOTATION_INVALID', 'marker_invalid', false, false, false, false, null],
    [404, 'PHOTO_ANNOTATION_NOT_FOUND', 'marker_not_found', false, false, false, false, 'parent'],
    [409, 'PHOTO_UPLOAD_ID_CONFLICT', 'conflict', false, true, false, false, null],
    [409, 'PHOTO_UPLOAD_RESUME_MISMATCH', 'conflict', false, true, false, false, null],
    [409, 'PHOTO_OBJECT_CONFLICT', 'conflict', false, true, false, false, null],
    [503, 'PHOTO_PROCESSING_BUSY', 'busy', true, false, false, false, null],
    [503, 'PHOTO_STORAGE_UNAVAILABLE', 'storage_unavailable', true, false, false, false, null],
    [500, 'PHOTO_STORAGE_ERROR', 'storage_unavailable', true, false, false, false, null],
    [0, 'NETWORK_ERROR', 'network', true, false, false, false, null],
    [0, 'UPLOAD_STALLED', 'network', true, false, false, false, null],
    [201, 'BAD_RESPONSE', 'network', true, false, false, false, null],
    [0, 'UPLOAD_ABORTED', 'network', true, false, false, false, null],
    [404, 'PHOTO_NOT_FOUND', 'not_found', false, false, false, false, 'list'],
    [404, 'PHOTO_ATTACHMENT_NOT_FOUND', 'not_found', false, false, false, false, 'list'],
    [409, 'PHOTO_ATTACHMENT_DUPLICATE', 'duplicate_attachment', false, false, false, false, null],
    [409, 'WORK_OCCURRENCE_NOT_CURRENT', 'work_not_current', false, false, false, false, 'parent'],
    [422, 'PHOTO_CURSOR_INVALID', 'generic', true, false, false, false, 'list'],
  ];

  it.each(rows)('%s %s → %s', (status, code, key, retryable, retryAsNew, stopsQueue, uploadsDisabled, refetch) => {
    expect(classifyPhotoError(err(status, code))).toEqual({
      code,
      key,
      retryable,
      retryAsNew,
      stopsQueue,
      uploadsDisabled,
      refetch,
    });
  });

  it('falls back to the HTTP status when there is no known code (proxy pages, plain 401)', () => {
    expect(classifyPhotoError(err(401))).toMatchObject({ key: 'session_expired', retryable: true, stopsQueue: true });
    expect(classifyPhotoError(err(413))).toMatchObject({ key: 'too_large', code: 'PHOTO_TOO_LARGE' });
    expect(classifyPhotoError(err(415))).toMatchObject({ key: 'unsupported_format' });
    expect(classifyPhotoError(err(502))).toMatchObject({ key: 'storage_unavailable', retryable: true });
    expect(classifyPhotoError(err(418))).toMatchObject({ key: 'unknown', retryable: false });
    expect(classifyPhotoError(err(0))).toMatchObject({ key: 'network', retryable: true });
  });

  it('treats an unknown code like a missing one', () => {
    expect(classifyPhotoError(err(500, 'SOMETHING_NEW'))).toMatchObject({ key: 'storage_unavailable' });
  });

  it('never echoes server text: the key is the only user-facing output', () => {
    const result = classifyPhotoError(new ApiError('SECRET server detail', 422, 'PHOTO_INVALID_IMAGE'));
    expect(JSON.stringify(result)).not.toContain('SECRET');
  });

  it('classifies a non-ApiError as a retryable unknown', () => {
    expect(classifyPhotoError(new Error('boom'))).toMatchObject({ key: 'unknown', retryable: true });
  });
});

describe('isTransportFailure', () => {
  it('is true only for failures below HTTP', () => {
    expect(isTransportFailure(err(0, 'NETWORK_ERROR'))).toBe(true);
    expect(isTransportFailure(err(0, 'UPLOAD_STALLED'))).toBe(true);
    expect(isTransportFailure(err(201, 'BAD_RESPONSE'))).toBe(true);
    expect(isTransportFailure(err(503, 'PHOTO_PROCESSING_BUSY'))).toBe(false);
    expect(isTransportFailure(err(404, 'PHOTO_NOT_FOUND'))).toBe(false);
    expect(isTransportFailure(new Error('x'))).toBe(false);
  });
});
