import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchKnowledgeLinkIndex, forgetKnowledgeLinkIndex, listKnowledgeEntries } from './knowledge';

describe('knowledge API (Stage 17D, 17E)', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    forgetKnowledgeLinkIndex();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

  it('asks for the link index once however many cards ask, and shares the answer', async () => {
    fetchMock.mockResolvedValue(ok({ items: [] }));
    const answers = await Promise.all([fetchKnowledgeLinkIndex(), fetchKnowledgeLinkIndex(), fetchKnowledgeLinkIndex()]);
    await fetchKnowledgeLinkIndex();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/knowledge/links/index');
    expect(answers[0]).toBe(answers[2]);
  });

  it('forgets a failed request, so the next card asks again', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: { code: 'KNOWLEDGE_UNAVAILABLE', message: 'x' } }) });
    await expect(fetchKnowledgeLinkIndex()).rejects.toBeTruthy();
    fetchMock.mockResolvedValueOnce(ok({ items: [{ target_kind: 'RISK', target: 'X', entries: [] }] }));
    await expect(fetchKnowledgeLinkIndex()).resolves.toEqual({ items: [{ target_kind: 'RISK', target: 'X', entries: [] }] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('sends the typed words trimmed and asks for the whole list', async () => {
    fetchMock.mockResolvedValue(ok({ items: [], total: 0 }));
    await listKnowledgeEntries('  rekoj  ');
    expect(fetchMock.mock.calls[0][0]).toContain('q=rekoj');
    expect(fetchMock.mock.calls[0][0]).toContain('limit=200');
    await listKnowledgeEntries('   ');
    expect(fetchMock.mock.calls[1][0]).not.toContain('q=');
  });
});
