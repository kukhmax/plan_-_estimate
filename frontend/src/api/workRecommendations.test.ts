import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptWorkRecommendation } from './workRecommendations';

const projectId = '11111111-1111-1111-1111-111111111111';
const recommendationId = '22222222-2222-2222-2222-222222222222';
const path = `/api/projects/${projectId}/work-recommendations/${recommendationId}/accept`;
const base = import.meta.env.VITE_API_URL ?? '';

describe('acceptWorkRecommendation API client (Stage 11D.2)', () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  beforeEach(() => {
    calls.length = 0;
    localStorage.setItem('access_token', 'test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response('{"id":"rec-1","status":"ACCEPTED"}', { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('POSTs to the exact accept endpoint with no manual id and an empty body (semantic resolution)', async () => {
    await acceptWorkRecommendation(projectId, recommendationId);

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${base}${path}`);
    expect(calls[0].init?.method).toBe('POST');
    expect(calls[0].init?.body).toBe(JSON.stringify({}));
  });

  it('sends an explicit price_item_id for a manual fallback selection', async () => {
    await acceptWorkRecommendation(projectId, recommendationId, {
      price_item_id: 'price-9',
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${base}${path}`);
    expect(calls[0].init?.method).toBe('POST');
    expect(calls[0].init?.body).toBe(JSON.stringify({ price_item_id: 'price-9' }));
  });

  it('parses the authoritative WorkRecommendationRead response', async () => {
    const result = await acceptWorkRecommendation(projectId, recommendationId);
    expect(result).toEqual({ id: 'rec-1', status: 'ACCEPTED' });
  });
});
