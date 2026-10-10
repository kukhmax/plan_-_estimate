import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { previewConcealedPdf } from './documents';
import { abandonConcealedDraft, fetchConcealedWorks, issueConcealed, openConcealedDraft, updateConcealed } from './concealedWorks';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}

describe('concealed works API (Stage 16G)', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  const call = () => {
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    return { url: String(url), init: (init ?? {}) as RequestInit };
  };

  it('reads the protocols and opens the draft with a POST', async () => {
    respond(200, { items: [], total: 0 });
    await fetchConcealedWorks('p1');
    expect(call().url).toBe('/api/projects/p1/concealed-works');
    vi.mocked(fetch).mockClear();
    respond(201, {});
    await openConcealedDraft('p1');
    expect(call().init.method).toBe('POST');
  });

  it('patches only what is sent', async () => {
    respond(200, {});
    await updateConcealed('p1', 'z1', { photo_ids: ['f1'], customer_absent: false, notified_on: null });
    expect(call().url).toBe('/api/projects/p1/concealed-works/z1');
    expect(call().init.method).toBe('PATCH');
    expect(JSON.parse(String(call().init.body))).toEqual({ photo_ids: ['f1'], customer_absent: false, notified_on: null });
  });

  it('abandons, issues and previews through their own routes', async () => {
    respond(200, {});
    await abandonConcealedDraft('p1', 'z1');
    expect(call().url).toBe('/api/projects/p1/concealed-works/z1/archive');
    vi.mocked(fetch).mockClear();
    respond(202, {});
    await issueConcealed('p1', 'z1');
    expect(call().url).toBe('/api/projects/p1/concealed-works/z1/issue');
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 2, byte_size: 1 });
    await previewConcealedPdf('p1');
    expect(call().url).toBe('/api/projects/p1/documents/concealed-works/preview');
    expect(call().init.method).toBe('POST');
  });
});
