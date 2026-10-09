import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { previewHandoverPdf } from './documents';
import { abandonHandoverDraft, fetchHandovers, issueHandover, openHandoverDraft, updateHandover } from './handovers';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}

describe('handovers API (Stage 16F)', () => {
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
    await fetchHandovers('p1');
    expect(call().url).toBe('/api/projects/p1/handovers');
    vi.mocked(fetch).mockClear();
    respond(201, {});
    await openHandoverDraft('p1');
    expect(call().url).toBe('/api/projects/p1/handovers');
    expect(call().init.method).toBe('POST');
  });

  it('patches only what is sent, with null clearing a value', async () => {
    respond(200, {});
    await updateHandover('p1', 'h1', { rooms: { r1: { requirements: { lighting_level: { value: null } } } } });
    expect(call().url).toBe('/api/projects/p1/handovers/h1');
    expect(call().init.method).toBe('PATCH');
    expect(JSON.parse(String(call().init.body))).toEqual({ rooms: { r1: { requirements: { lighting_level: { value: null } } } } });
  });

  it('abandons, issues and previews through their own routes', async () => {
    respond(200, {});
    await abandonHandoverDraft('p1', 'h1');
    expect(call().url).toBe('/api/projects/p1/handovers/h1/archive');
    vi.mocked(fetch).mockClear();
    respond(202, {});
    await issueHandover('p1', 'h1');
    expect(call().url).toBe('/api/projects/p1/handovers/h1/issue');
    expect(call().init.method).toBe('POST');
    vi.mocked(fetch).mockClear();
    respond(200, { sent: true, pages: 4, byte_size: 1 });
    await previewHandoverPdf('p1');
    expect(call().url).toBe('/api/projects/p1/documents/handover/preview');
    expect(call().init.method).toBe('POST');
  });
});
