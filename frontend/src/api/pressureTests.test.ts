import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { previewPressureTestPdf } from './documents';
import { abandonPressureDraft, fetchPressureTests, issuePressure, openPressureDraft, updatePressure } from './pressureTests';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}

describe('pressure tests API (V2-12b)', () => {
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
    await fetchPressureTests('p1');
    expect(call().url).toBe('/api/projects/p1/pressure-tests');
    vi.mocked(fetch).mockClear();
    respond(201, {});
    await openPressureDraft('p1');
    expect(call().init.method).toBe('POST');
  });

  it('patches only what is sent', async () => {
    respond(200, {});
    await updatePressure('p1', 'z1', { photo_ids: ['f1'], customer_absent: false, notified_on: null });
    expect(call().url).toBe('/api/projects/p1/pressure-tests/z1');
    expect(call().init.method).toBe('PATCH');
    expect(JSON.parse(String(call().init.body))).toEqual({ photo_ids: ['f1'], customer_absent: false, notified_on: null });
  });

  it('abandons, issues and previews through their own routes', async () => {
    respond(200, {});
    await abandonPressureDraft('p1', 'z1');
    expect(call().url).toBe('/api/projects/p1/pressure-tests/z1/archive');
    vi.mocked(fetch).mockClear();
    respond(202, {});
    await issuePressure('p1', 'z1');
    expect(call().url).toBe('/api/projects/p1/pressure-tests/z1/issue');
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 2, byte_size: 1 });
    await previewPressureTestPdf('p1');
    expect(call().url).toBe('/api/projects/p1/documents/pressure-test/preview');
    expect(call().init.method).toBe('POST');
  });
});
