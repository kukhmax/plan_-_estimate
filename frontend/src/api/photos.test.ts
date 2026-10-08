import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './http';
import {
  PHOTO_BAD_RESPONSE,
  PHOTO_IDLE_TIMEOUT_MS,
  PHOTO_NETWORK_ERROR,
  PHOTO_PROCESSING_TIMEOUT_MS,
  PHOTO_UPLOAD_ABORTED,
  PHOTO_UPLOAD_STALLED,
  PhotoUploadError,
  archivePhoto,
  archivePhotoAttachment,
  attachPhoto,
  buildUploadFormData,
  createPhotoAnnotation,
  deletePhotoAnnotation,
  fetchPhoto,
  fetchPhotoCounts,
  fetchPhotoStorage,
  fetchPhotos,
  patchPhotoAnnotation,
  patchPhotoAttachment,
  restorePhoto,
  restorePhotoAttachment,
  uploadPhoto,
} from './photos';

const PROJECT = '11111111-1111-4111-8111-111111111111';
const ROOM = '22222222-2222-4222-8222-222222222222';
const UPLOAD = '33333333-3333-4333-8333-333333333333';

function jsonResponse(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response;
}

describe('photos JSON API', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({})));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function lastCall(): { url: string; init: RequestInit } {
    const calls = vi.mocked(fetch).mock.calls;
    const [url, init] = calls[calls.length - 1] as [string, RequestInit];
    return { url, init };
  }

  it('builds the list query from the filters and omits unset ones', async () => {
    await fetchPhotos(PROJECT, {
      context: 'ROOM',
      roomId: ROOM,
      category: 'DEFECT',
      includeInReport: false,
      archived: true,
      limit: 30,
      cursor: 'abc',
    });
    const { url } = lastCall();
    expect(url.startsWith(`/api/projects/${PROJECT}/photos?`)).toBe(true);
    const query = new URLSearchParams(url.split('?')[1]);
    expect(Object.fromEntries(query)).toEqual({
      context: 'ROOM',
      room_id: ROOM,
      category: 'DEFECT',
      include_in_report: 'false',
      archived: 'true',
      limit: '30',
      cursor: 'abc',
    });
  });

  it('builds the evidence filters (inspection, question, finding, lineage) and the site-only flag', async () => {
    await fetchPhotos(PROJECT, { context: 'INSPECTION', inspectionId: 'I1', questionId: 'Q1' });
    expect(Object.fromEntries(new URLSearchParams(lastCall().url.split('?')[1]))).toEqual({
      context: 'INSPECTION',
      inspection_id: 'I1',
      question_id: 'Q1',
    });
    await fetchPhotos(PROJECT, { context: 'FINDING', findingId: 'F1' });
    expect(Object.fromEntries(new URLSearchParams(lastCall().url.split('?')[1]))).toEqual({ context: 'FINDING', finding_id: 'F1' });
    await fetchPhotos(PROJECT, { lineageId: 'L1', archived: false });
    expect(Object.fromEntries(new URLSearchParams(lastCall().url.split('?')[1]))).toEqual({ lineage: 'L1', archived: 'false' });
    await fetchPhotos(PROJECT, { context: 'WORK', surfaceId: 'S1', occurrenceKey: 'K1' });
    expect(Object.fromEntries(new URLSearchParams(lastCall().url.split('?')[1]))).toEqual({
      context: 'WORK',
      surface_id: 'S1',
      occurrence_key: 'K1',
    });
    await fetchPhotos(PROJECT, { siteOnly: true });
    expect(Object.fromEntries(new URLSearchParams(lastCall().url.split('?')[1]))).toEqual({ site_only: 'true' });
    await fetchPhotos(PROJECT, { siteOnly: false });
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos`); // false is not sent
  });

  it('calls the bare list route when no filter is set', async () => {
    await fetchPhotos(PROJECT);
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos`);
  });

  it('uses the documented routes and verbs', async () => {
    await fetchPhoto(PROJECT, UPLOAD);
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos/${UPLOAD}`);
    await fetchPhotoCounts(PROJECT);
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos/counts`);
    await fetchPhotoStorage();
    expect(lastCall().url).toBe('/api/photo-storage');

    await patchPhotoAttachment(PROJECT, 'att', { caption: 'x', include_in_report: true });
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att`);
    expect(lastCall().init.method).toBe('PATCH');
    expect(JSON.parse(lastCall().init.body as string)).toEqual({ caption: 'x', include_in_report: true });

    await archivePhotoAttachment(PROJECT, 'att');
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att/archive`);
    expect(lastCall().init.method).toBe('POST');
    await restorePhotoAttachment(PROJECT, 'att');
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att/restore`);
    await archivePhoto(PROJECT, UPLOAD);
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos/${UPLOAD}/archive`);
    await restorePhoto(PROJECT, UPLOAD);
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos/${UPLOAD}/restore`);

    await attachPhoto(PROJECT, UPLOAD, { context: 'ROOM', room_id: ROOM });
    expect(lastCall().url).toBe(`/api/projects/${PROJECT}/photos/${UPLOAD}/attachments`);
    expect(JSON.parse(lastCall().init.body as string)).toEqual({ context: 'ROOM', room_id: ROOM });
  });

  it('sends the bearer token and maps a structured error to ApiError with its code', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ detail: { code: 'PHOTO_NOT_FOUND', message: 'Photo not found' } }, 404),
    );
    const error = await fetchPhoto(PROJECT, UPLOAD).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: 'PHOTO_NOT_FOUND' });
    const headers = lastCall().init.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer tok');
  });
});

// ---------------------------------------------------------------------------

class FakeXhr {
  static instances: FakeXhr[] = [];
  method = '';
  url = '';
  headers: Record<string, string> = {};
  body: unknown = null;
  status = 0;
  responseText = '';
  responseHeaders: Record<string, string> = {};
  aborted = false;
  upload: { onprogress: ((e: unknown) => void) | null; onload: (() => void) | null } = { onprogress: null, onload: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.instances.push(this);
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  getResponseHeader(name: string): string | null {
    return this.responseHeaders[name] ?? null;
  }
  send(body: unknown) {
    this.body = body;
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  // test helpers
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ loaded, total, lengthComputable: true });
  }
  bytesSent() {
    this.upload.onload?.();
  }
  respond(status: number, body: unknown, headers: Record<string, string> = {}) {
    this.status = status;
    this.responseText = typeof body === 'string' ? body : JSON.stringify(body);
    this.responseHeaders = headers;
    this.onload?.();
  }
}

function makeFile(name = 'p.jpg', type = 'image/jpeg', size = 1234): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('uploadPhoto (XHR transport)', () => {
  beforeEach(() => {
    FakeXhr.instances = [];
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const params = (over: Record<string, unknown> = {}) => ({
    projectId: PROJECT,
    context: 'ROOM' as const,
    roomId: ROOM,
    uploadId: UPLOAD,
    file: makeFile(),
    source: 'CAMERA' as const,
    ...over,
  });

  it('posts multipart FormData with the bearer token and NO manual Content-Type', () => {
    void uploadPhoto(params());
    const xhr = FakeXhr.instances[0];
    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe(`/api/projects/${PROJECT}/photos`);
    expect(xhr.headers).toEqual({ Authorization: 'Bearer tok' });
    expect(Object.keys(xhr.headers).map((name) => name.toLowerCase())).not.toContain('content-type');
    expect(xhr.body).toBeInstanceOf(FormData);
  });

  it('puts exactly the documented fields in the FormData, the target id of its own context only', () => {
    const form = buildUploadFormData(
      params({ category: 'DEFECT', caption: 'Pęknięcie', includeInReport: true, surfaceId: 'ignored', openingId: 'ignored' }),
    );
    expect([...form.keys()]).toEqual(['upload_id', 'context', 'room_id', 'category', 'caption', 'include_in_report', 'source', 'file']);
    expect(form.get('upload_id')).toBe(UPLOAD);
    expect(form.get('context')).toBe('ROOM');
    expect(form.get('room_id')).toBe(ROOM);
    expect(form.get('include_in_report')).toBe('true');
    expect(form.get('source')).toBe('CAMERA');
    expect((form.get('file') as File).name).toBe('p.jpg');
  });

  it('sends a PROJECT upload without any target id and omits unset optional fields', () => {
    const form = buildUploadFormData(params({ context: 'PROJECT', roomId: undefined, source: undefined }));
    expect([...form.keys()]).toEqual(['upload_id', 'context', 'file']);
  });

  it('sends a SURFACE / OPENING upload with its own id', () => {
    const surface = buildUploadFormData(params({ context: 'SURFACE', roomId: ROOM, surfaceId: 'S1' }));
    expect(surface.get('surface_id')).toBe('S1');
    expect(surface.has('room_id')).toBe(false);
    const opening = buildUploadFormData(params({ context: 'OPENING', roomId: ROOM, openingId: 'O1' }));
    expect(opening.get('opening_id')).toBe('O1');
    expect(opening.has('room_id')).toBe(false);
  });

  it('sends an INSPECTION upload with its inspection, and the question only when the photo documents one', () => {
    const inspection = buildUploadFormData(params({ context: 'INSPECTION', roomId: undefined, inspectionId: 'I1', questionId: undefined }));
    expect([...inspection.keys()]).toEqual(['upload_id', 'context', 'inspection_id', 'source', 'file']);
    expect(inspection.get('inspection_id')).toBe('I1');
    expect(inspection.has('question_id')).toBe(false);
    const question = buildUploadFormData(params({ context: 'INSPECTION', roomId: undefined, inspectionId: 'I1', questionId: 'Q1' }));
    expect(question.get('inspection_id')).toBe('I1');
    expect(question.get('question_id')).toBe('Q1');
    // a question without its inspection is never sent
    const orphan = buildUploadFormData(params({ context: 'INSPECTION', roomId: undefined, inspectionId: undefined, questionId: 'Q1' }));
    expect(orphan.has('question_id')).toBe(false);
  });

  it('sends a WORK upload with its surface, its planned work and the suggested category (14H)', () => {
    const work = buildUploadFormData(
      params({ context: 'WORK', roomId: undefined, surfaceId: 'S1', occurrenceKey: 'K1', category: 'BEFORE' }),
    );
    expect([...work.keys()]).toEqual(['upload_id', 'context', 'surface_id', 'occurrence_key', 'category', 'source', 'file']);
    expect(work.get('surface_id')).toBe('S1');
    expect(work.get('occurrence_key')).toBe('K1');
    expect(work.get('category')).toBe('BEFORE');
    // nothing else names the target: the operation is taken from the plan by the server
    expect(work.has('price_item_id')).toBe(false);
    expect(work.has('room_id')).toBe(false);
    // the key belongs to WORK only
    const surface = buildUploadFormData(params({ context: 'SURFACE', roomId: undefined, surfaceId: 'S1', occurrenceKey: 'K1' }));
    expect(surface.has('occurrence_key')).toBe(false);
    // a work photo without its key is never half-addressed
    expect(buildUploadFormData(params({ context: 'WORK', roomId: undefined, surfaceId: 'S1' })).has('occurrence_key')).toBe(false);
  });

  it('sends a FINDING upload with its finding only; the lineage never leaves the client', () => {
    const form = buildUploadFormData(params({ context: 'FINDING', roomId: undefined, findingId: 'F1', lineageId: 'L1', inspectionId: 'I1', questionId: 'Q1' }));
    expect(form.get('finding_id')).toBe('F1');
    for (const name of ['inspection_id', 'question_id', 'lineage_id', 'lineage', 'room_id']) expect(form.has(name)).toBe(false);
  });

  it('reports progress and the moment all bytes were sent, then resolves with the parsed body', async () => {
    const onProgress = vi.fn();
    const onBytesSent = vi.fn();
    const promise = uploadPhoto(params(), { onProgress, onBytesSent });
    const xhr = FakeXhr.instances[0];
    xhr.progress(50, 200);
    xhr.bytesSent();
    xhr.respond(201, { asset: { id: UPLOAD } });
    await expect(promise).resolves.toEqual({ asset: { id: UPLOAD } });
    expect(onProgress).toHaveBeenCalledWith(50, 200);
    expect(onBytesSent).toHaveBeenCalledTimes(1);
  });

  it('maps a structured error body to PhotoUploadError with status, code and Retry-After', async () => {
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].respond(
      503,
      { detail: { code: 'PHOTO_PROCESSING_BUSY', message: 'busy' } },
      { 'Retry-After': '7' },
    );
    const error = await promise.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(PhotoUploadError);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: 'PHOTO_PROCESSING_BUSY', retryAfterSeconds: 7 });
  });

  it('maps a non-JSON proxy 413 page to PHOTO_TOO_LARGE', async () => {
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].respond(413, '<html>Request Entity Too Large</html>');
    await expect(promise).rejects.toMatchObject({ status: 413, code: 'PHOTO_TOO_LARGE' });
  });

  it('keeps other non-JSON failures without a code', async () => {
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].respond(502, 'bad gateway');
    const error = await promise.catch((caught: unknown) => caught);
    expect(error).toMatchObject({ status: 502 });
    expect((error as ApiError).code).toBeUndefined();
  });

  it('reports a network error as status 0 NETWORK_ERROR', async () => {
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].onerror?.();
    await expect(promise).rejects.toMatchObject({ status: 0, code: PHOTO_NETWORK_ERROR });
  });

  it('reports an unparsable 2xx body as BAD_RESPONSE (outcome unknown, GET-first applies)', async () => {
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].respond(201, 'not json');
    await expect(promise).rejects.toMatchObject({ code: PHOTO_BAD_RESPONSE });
  });

  it('aborts the request when the signal fires and rejects with UPLOAD_ABORTED', async () => {
    const controller = new AbortController();
    const promise = uploadPhoto(params(), { signal: controller.signal });
    controller.abort();
    await expect(promise).rejects.toMatchObject({ status: 0, code: PHOTO_UPLOAD_ABORTED });
    expect(FakeXhr.instances[0].aborted).toBe(true);
  });

  it('rejects at once, without a request, when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(uploadPhoto(params(), { signal: controller.signal })).rejects.toMatchObject({ code: PHOTO_UPLOAD_ABORTED });
    expect(FakeXhr.instances).toHaveLength(0);
  });

  it('idle watchdog: aborts after 60 s without progress, restarts on every progress event', async () => {
    vi.useFakeTimers();
    const promise = uploadPhoto(params());
    const settled = vi.fn();
    promise.catch(settled);
    const xhr = FakeXhr.instances[0];

    vi.advanceTimersByTime(PHOTO_IDLE_TIMEOUT_MS - 1_000);
    xhr.progress(10, 100); // progress restarts the countdown
    vi.advanceTimersByTime(PHOTO_IDLE_TIMEOUT_MS - 1_000);
    await Promise.resolve();
    expect(settled).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1_000);
    await expect(promise).rejects.toMatchObject({ status: 0, code: PHOTO_UPLOAD_STALLED });
    expect(xhr.aborted).toBe(true);
  });

  it('has no total timeout: a slow but steadily progressing upload is never cut off', async () => {
    vi.useFakeTimers();
    const promise = uploadPhoto(params());
    const settled = vi.fn();
    promise.catch(settled);
    const xhr = FakeXhr.instances[0];
    for (let i = 1; i <= 20; i += 1) {
      vi.advanceTimersByTime(30_000);
      xhr.progress(i, 100);
    }
    await Promise.resolve();
    expect(settled).not.toHaveBeenCalled();
  });

  it('processing watchdog: after the bytes are sent it waits for the answer, but not forever', async () => {
    vi.useFakeTimers();
    const promise = uploadPhoto(params());
    const settled = vi.fn();
    promise.catch(settled);
    const xhr = FakeXhr.instances[0];
    xhr.bytesSent();
    vi.advanceTimersByTime(PHOTO_IDLE_TIMEOUT_MS + 1_000); // longer than the idle limit: still waiting for the server
    await Promise.resolve();
    expect(settled).not.toHaveBeenCalled();
    vi.advanceTimersByTime(PHOTO_PROCESSING_TIMEOUT_MS);
    await expect(promise).rejects.toMatchObject({ code: PHOTO_UPLOAD_STALLED });
  });

  it('stops the watchdog once the answer arrived', async () => {
    vi.useFakeTimers();
    const promise = uploadPhoto(params());
    FakeXhr.instances[0].respond(200, { ok: true });
    await promise;
    vi.advanceTimersByTime(PHOTO_PROCESSING_TIMEOUT_MS * 2);
    expect(FakeXhr.instances[0].aborted).toBe(false);
  });
});

describe('photo marker (annotation) API', () => {
  const lastFetch = () => {
    const calls = vi.mocked(fetch).mock.calls;
    const [url, init] = calls[calls.length - 1] as [string, RequestInit];
    return { url, init };
  };
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({})));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('places a marker with a POST of x, y (and the label when given)', async () => {
    await createPhotoAnnotation(PROJECT, 'att', { x: 0.25, y: 0.75 });
    expect(lastFetch().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att/annotations`);
    expect(lastFetch().init.method).toBe('POST');
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ x: 0.25, y: 0.75 });
    await createPhotoAnnotation(PROJECT, 'att', { x: 0, y: 1, label: 'rysa' });
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ x: 0, y: 1, label: 'rysa' });
  });

  it('changes only the label with a PATCH (null clears it)', async () => {
    await patchPhotoAnnotation(PROJECT, 'att', 'm1', { label: 'nowy' });
    expect(lastFetch().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att/annotations/m1`);
    expect(lastFetch().init.method).toBe('PATCH');
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ label: 'nowy' });
    await patchPhotoAnnotation(PROJECT, 'att', 'm1', { label: null });
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ label: null });
  });

  it('sets or clears the contour with a PATCH of outline only', async () => {
    await patchPhotoAnnotation(PROJECT, 'att', 'm1', { outline: [[0.1, 0.2], [0.3, 0.4], [0.5, 0.2]] });
    expect(lastFetch().init.method).toBe('PATCH');
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ outline: [[0.1, 0.2], [0.3, 0.4], [0.5, 0.2]] });
    await patchPhotoAnnotation(PROJECT, 'att', 'm1', { outline: null });
    expect(JSON.parse(lastFetch().init.body as string)).toEqual({ outline: null });
  });

  it('deletes with a DELETE and no body, and a 204 answer is fine', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 204, json: vi.fn() } as unknown as Response);
    await expect(deletePhotoAnnotation(PROJECT, 'att', 'm1')).resolves.toBeUndefined();
    expect(lastFetch().url).toBe(`/api/projects/${PROJECT}/photo-attachments/att/annotations/m1`);
    expect(lastFetch().init.method).toBe('DELETE');
    expect(lastFetch().init.body).toBeUndefined();
  });
});

