import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  archiveAreaSegment,
  createAreaSegment,
  fetchAreaSegments,
  restoreAreaSegment,
  updateAreaSegment,
} from './areaSegments';

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const segmentId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

const BASE = import.meta.env.VITE_API_URL ?? '';

function expectCall(
  calls: { url: string; method: string }[],
  index: number,
  method: string,
  path: string,
) {
  expect(calls[index].method).toBe(method);
  expect(calls[index].url).toBe(`${BASE}${path}`);
}

describe('areaSegments API client URL contract', () => {
  const calls: { url: string; method: string }[] = [];

  beforeEach(() => {
    calls.length = 0;
    localStorage.setItem('access_token', 'test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, method: init?.method ?? 'GET' });
        return new Response('{}', { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('list targets /api/projects/{p}/rooms/{r}/area-segments', async () => {
    await fetchAreaSegments(projectId, roomId);
    expect(calls).toHaveLength(1);
    expectCall(calls, 0, 'GET', `/api/projects/${projectId}/rooms/${roomId}/area-segments`);
  });

  it('list appends the include_archived query when requested', async () => {
    await fetchAreaSegments(projectId, roomId, true);
    expectCall(
      calls,
      0,
      'GET',
      `/api/projects/${projectId}/rooms/${roomId}/area-segments?include_archived=true`,
    );
  });

  it('create targets the same collection with POST', async () => {
    await createAreaSegment(projectId, roomId, {
      plane: 'FLOOR',
      operation: 'ADD',
      width: 3,
      height: 2,
      label: null,
    });
    expectCall(calls, 0, 'POST', `/api/projects/${projectId}/rooms/${roomId}/area-segments`);
  });

  it('update targets the segment with PATCH', async () => {
    await updateAreaSegment(projectId, roomId, segmentId, { width: 4 });
    expectCall(
      calls,
      0,
      'PATCH',
      `/api/projects/${projectId}/rooms/${roomId}/area-segments/${segmentId}`,
    );
  });

  it('archive targets the archive sub-route with POST', async () => {
    await archiveAreaSegment(projectId, roomId, segmentId);
    expectCall(
      calls,
      0,
      'POST',
      `/api/projects/${projectId}/rooms/${roomId}/area-segments/${segmentId}/archive`,
    );
  });

  it('restore targets the restore sub-route with POST', async () => {
    await restoreAreaSegment(projectId, roomId, segmentId);
    expectCall(
      calls,
      0,
      'POST',
      `/api/projects/${projectId}/rooms/${roomId}/area-segments/${segmentId}/restore`,
    );
  });
});
