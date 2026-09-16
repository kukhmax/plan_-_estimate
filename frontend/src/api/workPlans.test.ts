import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './http';
import {
  fetchSurfaceWorkPlan,
  isSurfaceWorkPlanMissing,
  putSurfaceWorkPlan,
} from './workPlans';

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surfaceId = '33333333-3333-3333-3333-333333333333';
const path = `/api/projects/${projectId}/rooms/${roomId}/surfaces/${surfaceId}/work-plan`;
const base = import.meta.env.VITE_API_URL ?? '';

describe('workPlans API client', () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  beforeEach(() => {
    calls.length = 0;
    localStorage.setItem('access_token', 'test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response('{}', { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('loads the exact surface WorkPlan endpoint with GET', async () => {
    await fetchSurfaceWorkPlan(projectId, roomId, surfaceId);

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${base}${path}`);
    expect(calls[0].init?.method ?? 'GET').toBe('GET');
  });

  it('fully replaces the exact WorkPlan endpoint with the ordered payload', async () => {
    const payload = {
      substrate: 'PAINTED' as const,
      quality_target: null,
      price_item_ids: ['price-a', 'price-b', 'price-a'],
    };

    await putSurfaceWorkPlan(projectId, roomId, surfaceId, payload);

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${base}${path}`);
    expect(calls[0].init?.method).toBe('PUT');
    expect(calls[0].init?.body).toBe(JSON.stringify(payload));
  });
});

describe('isSurfaceWorkPlanMissing', () => {
  it('matches only the exact no-plan 404 contract', () => {
    expect(isSurfaceWorkPlanMissing(new ApiError('Surface work plan not found', 404))).toBe(true);
    expect(isSurfaceWorkPlanMissing(new ApiError('Surface not found', 404))).toBe(false);
    expect(isSurfaceWorkPlanMissing(new ApiError('Surface work plan not found', 403))).toBe(false);
    expect(isSurfaceWorkPlanMissing(new Error('Surface work plan not found'))).toBe(false);
  });
});
