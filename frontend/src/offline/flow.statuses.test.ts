import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { completeInspection, createInspection, fetchInspection, fetchInspectionAnswers, fetchInspectionFindings, fetchInspections, putInspectionAnswers } from '../api/inspections';
import { fetchSurfaceWorkPlan, transitionWorkExecution } from '../api/workPlans';
import { generateEstimate } from '../api/estimates';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { listOps } from './outbox';
import { getOutboxCounts, resetSyncStateForTests, setDrainRunner } from './outboxState';
import { setOfflineOwner } from './readCache';
import { drainOutbox } from './sync';

const P = '11111111-1111-4111-8111-111111111111';
const R = '22222222-2222-4222-8222-222222222222';
const S = '33333333-3333-4333-8333-333333333333';
const K = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const TEMPLATE = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const Q = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;
const NOT_STARTED = { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null };
const plan = (execution: Record<string, unknown>) => ({ id: 'plan', planned_works: [{ occurrence_key: K, position: 0, execution }] });
const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** A server that keeps what it is sent in the order it arrives. */
function server() {
  const state = { up: true };
  const received: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const inspections = new Map<string, Record<string, unknown>>();
  let execution: Record<string, unknown> = { ...NOT_STARTED };
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const path = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    if (method !== 'GET') received.push({ method, path, body });
    const base = `/api/projects/${P}/rooms/${R}`;
    if (method === 'GET' && path === `${base}/surfaces/${S}/work-plan`) return json(plan(execution));
    if (method === 'GET' && path === `${base}/inspections`) return json({ items: [...inspections.values()], total: inspections.size });
    if (method === 'POST' && path === `${base}/inspections`) {
      const id = body?.id as string;
      if (!inspections.has(id)) inspections.set(id, { ...body, room_id: R, status: 'DRAFT', answers: [], is_archived: false });
      return json(inspections.get(id), 201);
    }
    if (method === 'PATCH' && path === `${base}/surfaces/${S}/work-plan/occurrences/${K}/execution`) {
      execution = { status: body?.status, started_at: body?.recorded_at, completed_at: body?.status === 'COMPLETED' ? body?.recorded_at : null, ready_after: null };
      return json({ occurrence_key: K, ...execution });
    }
    if (method === 'GET') return json({ items: [], total: 0 });
    return json({}, 200);
  });
  return { handler, state, received, inspections };
}

describe('starting an inspection and marking works without a signal (Stage 19C.3)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('an inspection started in a basement, its answers and the status of a work reach the server in order, with the moment of the tap', async () => {
    const s = server();
    vi.stubGlobal('fetch', s.handler);
    await fetchSurfaceWorkPlan(P, R, S); // read in the car, kept on the phone
    await fetchInspections(P, R);
    s.state.up = false;
    reportNetworkFailure();

    const started = await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', quality_target: 'S2', plane: 'CEILING' });
    expect(started).toMatchObject({ room_id: R, status: 'DRAFT', plane: 'CEILING', _pending: true });
    expect(started.id).toMatch(UUID4);
    await putInspectionAnswers(P, R, started.id, { answers: [{ question_id: Q, value_bool: true }] });
    const tapped = Date.now();
    const result = await transitionWorkExecution(P, R, S, K, { status: 'IN_PROGRESS', expected_status: 'NOT_STARTED' });

    // what the owner sees meanwhile
    expect((await fetchInspections(P, R)).items.map((i) => i.id)).toEqual([started.id]);
    const opened = await fetchInspection(P, R, started.id);
    expect(opened).toMatchObject({ id: started.id, status: 'DRAFT' });
    expect(opened.answers).toMatchObject([{ question_id: Q, value_bool: true }]); // the form is filled in from them
    expect((await fetchInspectionAnswers(P, R, started.id)).items).toHaveLength(1);
    expect((await fetchInspectionFindings(P, R, started.id, true)).items).toEqual([]);
    expect(result).toMatchObject({ status: 'IN_PROGRESS', occurrence_key: K });
    expect(Date.parse(result.started_at as string)).toBeGreaterThanOrEqual(tapped - 5);
    expect((await fetchSurfaceWorkPlan(P, R, S)).planned_works[0].execution).toMatchObject({ status: 'IN_PROGRESS', started_at: result.started_at });
    expect(s.received).toEqual([]);

    // the signal returns
    s.state.up = true;
    reportNetworkSuccess();
    expect(await drainOutbox()).toEqual({ sent: 3, refused: 0, stoppedBy: null });

    expect(s.received.map((r) => `${r.method} ${r.path.replace(`/api/projects/${P}/rooms/${R}`, '')}`)).toEqual([
      'POST /inspections',
      `PUT /inspections/${started.id}/answers`,
      `PATCH /surfaces/${S}/work-plan/occurrences/${K}/execution`,
    ]);
    expect(s.received[0].body?.id).toBe(started.id); // the id the screens already had
    expect(s.received[2].body).toMatchObject({ status: 'IN_PROGRESS', expected_status: 'NOT_STARTED', recorded_at: result.started_at });
    expect(await listOps()).toEqual([]);
  });

  it('a lost answer: the inspection is sent again under the same id and the server holds one', async () => {
    const s = server();
    let lose = true;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const answer = await s.handler(url, init);
      if (lose && init?.method === 'POST') {
        lose = false;
        throw new TypeError('Failed to fetch');
      }
      return answer;
    }));

    const started = await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', plane: 'FLOOR' });
    expect(started).toMatchObject({ _pending: true });
    expect(s.inspections.size).toBe(1);

    reportNetworkSuccess();
    await drainOutbox();

    expect(s.inspections.size).toBe(1);
    expect(s.received.map((r) => r.body?.id)).toEqual([started.id, started.id]);
  });

  it('the status carries the moment of the tap also when the server is reachable (a lost answer is repeated with the same moment)', async () => {
    const s = server();
    vi.stubGlobal('fetch', s.handler);
    const before = Date.now();
    await transitionWorkExecution(P, R, S, K, { status: 'IN_PROGRESS', expected_status: 'NOT_STARTED' });
    const sent = s.received[0].body as { recorded_at: string };
    expect(Date.parse(sent.recorded_at)).toBeGreaterThanOrEqual(before - 5);
    expect(Date.parse(sent.recorded_at)).toBeLessThanOrEqual(Date.now() + 5);
  });

  it('a status the server refuses (it was changed elsewhere) is parked with its reason and the rest goes on', async () => {
    const s = server();
    const inner = s.handler;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH') return json({ detail: { code: 'WORK_EXECUTION_CONFLICT', message: 'moved', current_status: 'COMPLETED' } }, 409);
      return inner(url, init);
    }));
    reportNetworkFailure();
    await transitionWorkExecution(P, R, S, K, { status: 'IN_PROGRESS', expected_status: 'NOT_STARTED' });
    await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', plane: 'FLOOR' });
    reportNetworkSuccess();

    expect(await drainOutbox()).toEqual({ sent: 1, refused: 1, stoppedBy: null });
    expect((await listOps()).map((o) => ({ kind: o.kind, status: o.status, code: o.error?.code }))).toEqual([{ kind: 'execution.transition', status: 'failed', code: 'WORK_EXECUTION_CONFLICT' }]);
  });
});

describe('what acts on the server waits for the changes made without a signal (Stage 19C.3)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    setDrainRunner(drainOutbox);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('closing an inspection first sends its answers, so it is closed with them', async () => {
    const s = server();
    vi.stubGlobal('fetch', s.handler);
    reportNetworkFailure();
    const started = await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', plane: 'FLOOR' });
    await putInspectionAnswers(P, R, started.id, { answers: [{ question_id: Q, value_bool: false }] });
    reportNetworkSuccess(); // the signal is back, the engine has not yet looked at the outbox

    await completeInspection(P, R, started.id);

    expect(s.received.map((r) => `${r.method} ${r.path.split('/').slice(-1)[0]}`)).toEqual(['POST inspections', 'PUT answers', 'POST complete']);
    expect(getOutboxCounts().pending).toBe(0);
  });

  it('without a signal it does not even try: the owner is told that earlier changes wait', async () => {
    const s = server();
    vi.stubGlobal('fetch', s.handler);
    reportNetworkFailure();
    const started = await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', plane: 'FLOOR' });
    s.handler.mockClear();

    const attempt = completeInspection(P, R, started.id);

    await expect(attempt).rejects.toMatchObject({ code: 'CHANGES_WAITING' });
    await expect(attempt).rejects.toBeInstanceOf(ApiError);
    expect(s.handler).not.toHaveBeenCalled();
    expect(getOutboxCounts().pending).toBe(1); // nothing was lost
  });

  it('when the sending is stopped on the way (the signal goes again) the request is not made', async () => {
    const s = server();
    const inner = s.handler;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && String(url).endsWith('/inspections')) throw new TypeError('Failed to fetch'); // dies in the middle of the sending
      return inner(url, init);
    }));
    reportNetworkFailure();
    const started = await createInspection(P, R, { template_id: TEMPLATE, substrate: 'CONCRETE', plane: 'FLOOR' });
    reportNetworkSuccess();

    await expect(completeInspection(P, R, started.id)).rejects.toMatchObject({ code: 'CHANGES_WAITING' });
    expect(s.received).toEqual([]);
  });

  it('with nothing waiting a write goes straight through', async () => {
    const s = server();
    vi.stubGlobal('fetch', s.handler);
    await generateEstimate(P);
    expect(s.received).toHaveLength(1);
  });
});
