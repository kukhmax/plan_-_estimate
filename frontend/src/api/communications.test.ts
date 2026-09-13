import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  evaluateCommunications,
  fetchCommunicationDetail,
  fetchCommunications,
} from './communications';

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const inspectionId = '33333333-3333-3333-3333-333333333333';
const communicationId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

const BASE = import.meta.env.VITE_API_URL ?? '';
const base = `/api/projects/${projectId}/rooms/${roomId}/inspections/${inspectionId}/communications`;

function expectCall(
  calls: { url: string; method: string }[],
  index: number,
  method: string,
  path: string,
) {
  expect(calls[index].method).toBe(method);
  expect(calls[index].url).toBe(`${BASE}${path}`);
}

describe('communications API client URL contract (Stage 8)', () => {
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

  it('list targets the inspection communications collection (GET, default active)', async () => {
    await fetchCommunications(projectId, roomId, inspectionId);
    expect(calls).toHaveLength(1);
    expectCall(calls, 0, 'GET', base);
  });

  it('sends status=active explicitly (the backend defaults to active, but never guesses)', async () => {
    await fetchCommunications(projectId, roomId, inspectionId, {
      status: 'active',
    });
    expectCall(calls, 0, 'GET', `${base}?status=active`);
  });

  it('sends status=resolved explicitly (dropping it would silently default to active)', async () => {
    await fetchCommunications(projectId, roomId, inspectionId, {
      status: 'resolved',
    });
    expectCall(calls, 0, 'GET', `${base}?status=resolved`);
  });

  it('sends status=all explicitly so a mixed list cannot be masked', async () => {
    await fetchCommunications(projectId, roomId, inspectionId, { status: 'all' });
    expectCall(calls, 0, 'GET', `${base}?status=all`);
  });

  it('evaluate POSTs to the evaluate sub-route', async () => {
    await evaluateCommunications(projectId, roomId, inspectionId);
    expectCall(calls, 0, 'POST', `${base}/evaluate`);
  });

  it('detail GETs one application by id', async () => {
    await fetchCommunicationDetail(
      projectId,
      roomId,
      inspectionId,
      communicationId,
    );
    expectCall(calls, 0, 'GET', `${base}/${communicationId}`);
  });
});