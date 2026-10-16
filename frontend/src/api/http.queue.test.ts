import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getConnectionState, reportNetworkFailure, resetConnectionForTests } from '../offline/connection';
import { listOps } from '../offline/outbox';
import { getOutboxCounts, resetSyncStateForTests } from '../offline/outboxState';
import { saveRead, setOfflineOwner } from '../offline/readCache';
import { freshIndexedDb } from '../test/fakeIdb';
import { WRITE_TIMEOUT_MS, apiRequest } from './http';

const P = '11111111-1111-4111-8111-111111111111';
const R = '22222222-2222-4222-8222-222222222222';
const S = '33333333-3333-4333-8333-333333333333';
const ROOMS = `/api/projects/${P}/rooms`;
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;
const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const send = (path: string, method: string, body?: unknown) =>
  apiRequest<Record<string, unknown>>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

describe('apiRequest: changes made without a signal (Stage 19C)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a create is sent with an id chosen on the phone (so that a repeat is safe); an id the caller gave is kept', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ id: 'x' }, 201));
    await send(ROOMS, 'POST', { name: 'Salon' });
    const sent = JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
    expect(sent.id).toMatch(UUID4);
    expect(sent.name).toBe('Salon');

    await send(ROOMS, 'POST', { id: R, name: 'Salon' });
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string).id).toBe(R);
  });

  it('while the server cannot be reached a create is kept, and the screen gets the record at once, marked as waiting', async () => {
    reportNetworkFailure();

    const room = await send(ROOMS, 'POST', { name: 'Kuchnia', length: 4, width: 3, height: 2.6 });

    expect(fetch).not.toHaveBeenCalled();
    expect(room).toMatchObject({ project_id: P, name: 'Kuchnia', length: 4, is_archived: false, _pending: true });
    expect(room.id).toMatch(UUID4);
    const ops = await listOps();
    expect(ops).toHaveLength(1);
    expect(ops[0]).toMatchObject({ kind: 'room.create', method: 'POST', path: ROOMS, entityId: room.id, label: 'Kuchnia', status: 'pending' });
    expect(ops[0].body).toMatchObject({ id: room.id, name: 'Kuchnia' });
    expect(getOutboxCounts().pending).toBe(1);
  });

  it('a network failure in the middle of a write keeps it and marks the connection offline', async () => {
    await saveRead(`${ROOMS}/${R}`, { id: R, project_id: P, name: 'Salon', length: 5 });
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const room = await send(`${ROOMS}/${R}`, 'PATCH', { length: 6 });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(room).toMatchObject({ id: R, name: 'Salon', length: 6, _pending: true });
    expect(getConnectionState().offline).toBe(true);
    expect((await listOps())[0]).toMatchObject({ kind: 'room.update', entityId: R, body: { length: 6 } });
  });

  it('a write that gets no answer in time is kept (the weak signal hangs instead of failing)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }); // the IndexedDB double needs the real scheduler
    vi.mocked(fetch).mockImplementationOnce(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          (init?.signal as AbortSignal).addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    );

    const pending = send(`${ROOMS}/${R}/archive`, 'POST');
    await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS + 1);

    expect(await pending).toMatchObject({ id: R, is_archived: true, _pending: true });
    expect((await listOps())[0].kind).toBe('room.archive');
  });

  it('a new change goes behind the older ones that still wait, even when the server answers again', async () => {
    reportNetworkFailure();
    await send(ROOMS, 'POST', { id: R, name: 'Salon' });
    resetConnectionForTests(); // the signal is back, but the first change has not been sent yet

    const second = await send(`${ROOMS}/${R}`, 'PATCH', { name: 'Salon 2' });

    expect(fetch).not.toHaveBeenCalled();
    expect(second).toMatchObject({ id: R, name: 'Salon 2' }); // the record made a moment ago, with the later change laid over it
    expect((await listOps()).map((o) => o.kind)).toEqual(['room.create', 'room.update']);
  });

  it('what the server answers to a read has the waiting changes laid over it, and the saved copy stays as the server said it', async () => {
    reportNetworkFailure();
    await send(ROOMS, 'POST', { id: R, name: 'Nowy' });
    resetConnectionForTests();
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [{ id: S, name: 'Stary' }], total: 1 }));

    const view = (await apiRequest(ROOMS)) as { items: Array<{ id: string }>; total: number };

    expect(view.items.map((i) => i.id)).toEqual([S, R]);
    expect(view.total).toBe(2);
  });

  it('without a signal the list shows the saved rooms plus the room made on the phone, and the room itself can be opened', async () => {
    await saveRead(ROOMS, { items: [{ id: S, name: 'Stary' }], total: 1 });
    reportNetworkFailure();
    await send(ROOMS, 'POST', { id: R, name: 'Nowy', length: 4 });
    vi.mocked(fetch).mockRejectedValue(new TypeError('x'));

    const list = (await apiRequest(ROOMS)) as { items: Array<{ id: string }> };
    expect(list.items.map((i) => i.id)).toEqual([S, R]);
    expect(await apiRequest(`${ROOMS}/${R}`)).toMatchObject({ id: R, name: 'Nowy', length: 4, _pending: true });
    expect(await apiRequest(`${ROOMS}/${R}/surfaces`)).toEqual({ items: [], total: 0 });
  });

  it('a wall made in a room that was made on the phone is kept under the path of that room', async () => {
    reportNetworkFailure();
    await send(ROOMS, 'POST', { id: R, name: 'Nowy' });

    vi.mocked(fetch).mockRejectedValue(new TypeError('x'));
    const wall = await send(`${ROOMS}/${R}/surfaces`, 'POST', { name: 'Wall 1', surface_type: 'WALL', width: 3, height: 2.7 });

    expect(wall).toMatchObject({ room_id: R, name: 'Wall 1', width: 3 });
    const listed = (await apiRequest(`${ROOMS}/${R}/surfaces`)) as { items: Array<{ id: string }> };
    expect(listed.items.map((i) => i.id)).toEqual([wall.id]);
    expect((await listOps()).map((o) => o.kind)).toEqual(['room.create', 'surface.create']);
  });

  it('removing a note without a signal gives nothing back and takes it out of the list', async () => {
    const N = '66666666-6666-4666-8666-666666666666';
    const notes = `/api/projects/${P}/notes`;
    await saveRead(notes, { items: [{ id: N, body: 'x' }], total: 1 });
    reportNetworkFailure();
    vi.mocked(fetch).mockRejectedValue(new TypeError('x'));

    expect(await send(`${notes}/${N}`, 'DELETE')).toBeUndefined();

    expect(await apiRequest(notes)).toEqual({ items: [], total: 0 });
  });

  it('the answers of an inspection typed without a signal are kept as one change', async () => {
    reportNetworkFailure();
    const path = `${ROOMS}/${R}/inspections/${S}/answers`;

    const result = await send(path, 'PUT', { answers: [{ question_id: 'q1', value_bool: true }] });

    expect(result).toMatchObject({ total: 1, items: [{ question_id: 'q1', value_bool: true, _pending: true }] });
    expect((await listOps())[0]).toMatchObject({ kind: 'answers.put', method: 'PUT' });
  });

  it('a refusal of the server is raised as before and nothing is kept', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ detail: { code: 'X', message: 'no' } }, 422));
    await expect(send(ROOMS, 'POST', { name: '' })).rejects.toMatchObject({ status: 422, code: 'X' });
    expect(await listOps()).toEqual([]);
  });

  it('what needs the server fails as before without a signal, and nothing is kept', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(send(`/api/projects/${P}/estimates/generate`, 'POST', {})).rejects.toBeInstanceOf(TypeError);
    await expect(send(`/api/projects/${P}/archive`, 'POST')).rejects.toBeInstanceOf(TypeError);
    expect(await listOps()).toEqual([]);
  });

  it('when no owner is known nothing can be kept: the failure is the same as before', async () => {
    localStorage.removeItem('offline_owner');
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(send(ROOMS, 'POST', { name: 'X' })).rejects.toBeInstanceOf(TypeError);
    expect(getOutboxCounts().pending).toBe(0);
  });

  it('a body that is not JSON is sent as it is and never kept', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(apiRequest(ROOMS, { method: 'POST', body: 'not json' })).rejects.toBeInstanceOf(TypeError);
    expect(await listOps()).toEqual([]);
  });

  it('while the server is known to be out of reach a read is answered from the phone at once, without waiting for the network', async () => {
    await saveRead(ROOMS, { items: [{ id: S }], total: 1 });
    reportNetworkFailure();

    expect(await apiRequest(ROOMS)).toEqual({ items: [{ id: S }], total: 1 });

    expect(fetch).not.toHaveBeenCalled();
  });

  it('but a read the phone knows nothing about still tries the network', async () => {
    reportNetworkFailure();
    vi.mocked(fetch).mockResolvedValueOnce(json({ items: [], total: 0 }));
    expect(await apiRequest(ROOMS)).toEqual({ items: [], total: 0 });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getConnectionState().offline).toBe(false);
  });
});
