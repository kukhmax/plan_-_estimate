import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAreaSegment } from '../api/areaSegments';
import { createOpening } from '../api/openings';
import { createProjectNote, deleteProjectNote, fetchProjectNotes, updateProjectNote } from '../api/projectNotes';
import { createRoom, fetchRoom, fetchRooms, updateRoom } from '../api/rooms';
import { createSurface, fetchSurfaces } from '../api/surfaces';
import { freshIndexedDb } from '../test/fakeIdb';
import { getConnectionState, reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { listOps } from './outbox';
import { getOutboxCounts, resetSyncStateForTests } from './outboxState';
import { setOfflineOwner } from './readCache';
import { drainOutbox } from './sync';

const P = '11111111-1111-4111-8111-111111111111';
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

/** A tiny server: it keeps what it is sent, so that the whole way (made offline -> sent -> read back) can be followed. */
function serverStub() {
  const rooms: Array<Record<string, unknown>> = [];
  const received: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const state = { up: true };
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const path = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    if (method !== 'GET') received.push({ method, path, body });
    if (method === 'POST' && path === `/api/projects/${P}/rooms`) {
      if (!rooms.some((r) => r.id === body?.id)) rooms.push({ ...body, project_id: P, is_archived: false });
      return json(rooms.find((r) => r.id === body?.id), 201);
    }
    if (method === 'GET' && path === `/api/projects/${P}/rooms`) return json({ items: rooms, total: rooms.length });
    if (method === 'GET') return json({ items: [], total: 0 });
    return json({}, method === 'POST' ? 201 : 200);
  });
  return { handler, rooms, received, state };
}

describe('the whole way of a change made without a signal (Stage 19C)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a room with a wall, a door, a rectangle and a note, all made in a basement, reach the server in order, once, when the signal returns', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    // in the car: what will be needed is read and kept
    await fetchRooms(P);
    await fetchProjectNotes(P);
    // the signal is lost
    server.state.up = false;
    reportNetworkFailure();

    const room = await createRoom(P, { name: 'Piwnica', length: 4, width: 3, height: 2.5 });
    const wall = await createSurface(P, room.id, { name: 'Wall 1', surface_type: 'WALL', position: 0, width: 4, height: 2.5 });
    const door = await createOpening(P, room.id, wall.id, { opening_type: 'DOOR', width: 0.9, height: 2 });
    const segment = await createAreaSegment(P, room.id, { plane: 'FLOOR', operation: 'ADD', width: 1, height: 2 });
    const note = await createProjectNote(P, 'Sprawdzić wilgotność');

    // what the owner sees meanwhile
    expect((await fetchRooms(P)).items.map((r) => r.id)).toEqual([room.id]);
    expect(await fetchRoom(P, room.id)).toMatchObject({ name: 'Piwnica', _pending: true });
    expect((await fetchSurfaces(P, room.id)).items.map((s) => s.id)).toEqual([wall.id]);
    expect((await fetchProjectNotes(P)).items.map((n) => n.id)).toEqual([note.id]);
    expect(server.received).toEqual([]); // nothing reached the server
    expect(getOutboxCounts().pending).toBe(5);

    // the signal returns
    server.state.up = true;
    reportNetworkSuccess();
    const result = await drainOutbox();

    expect(result).toEqual({ sent: 5, refused: 0, stoppedBy: null });
    expect(server.received.map((r) => r.path.replace(`/api/projects/${P}`, ''))).toEqual([
      '/rooms',
      `/rooms/${room.id}/surfaces`,
      `/rooms/${room.id}/surfaces/${wall.id}/openings`,
      `/rooms/${room.id}/area-segments`,
      '/notes',
    ]);
    // every create carried the id the phone had already given to the record, so the screens and the server agree on it
    expect(server.received.map((r) => r.body?.id)).toEqual([room.id, wall.id, door.id, segment.id, note.id]);
    expect(await listOps()).toEqual([]);
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 0 });
  });

  it('a lost answer: the same create is sent again with the same id, and the server makes one room', async () => {
    const server = serverStub();
    let lose = true;
    const inner = server.handler;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const answer = await inner(url, init);
      if (lose && init?.method === 'POST') {
        lose = false;
        throw new TypeError('Failed to fetch'); // the server did it, the phone never heard
      }
      return answer;
    }));

    const room = await createRoom(P, { name: 'Salon' }); // the answer is lost -> kept, shown as waiting
    expect(room).toMatchObject({ name: 'Salon', _pending: true });
    expect(server.rooms).toHaveLength(1); // the server has it already

    reportNetworkSuccess();
    await drainOutbox(); // the repeat

    expect(server.rooms).toHaveLength(1); // still one
    expect(server.received.map((r) => r.body?.id)).toEqual([room.id, room.id]);
  });

  it('edits of a record made later, offline, follow the record in order; a removed note is removed', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    await fetchRooms(P);
    await fetchProjectNotes(P);
    server.state.up = false;
    reportNetworkFailure();
    const note = await createProjectNote(P, 'A');
    await updateProjectNote(P, note.id, 'B');
    const kept = await createProjectNote(P, 'C');
    await deleteProjectNote(P, kept.id);
    const room = await createRoom(P, { name: 'X' });
    await updateRoom(P, room.id, { name: 'Y' });

    expect((await fetchProjectNotes(P)).items.map((n) => n.body)).toEqual(['B']);
    expect((await fetchRooms(P)).items[0]).toMatchObject({ name: 'Y' });
    expect((await listOps()).map((o) => o.kind)).toEqual(['note.create', 'note.update', 'note.create', 'note.delete', 'room.create', 'room.update']);
  });

  it('an online write goes straight to the server and nothing is kept', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    await createRoom(P, { name: 'Online' });
    expect(server.received).toHaveLength(1);
    expect(await listOps()).toEqual([]);
    expect(getConnectionState().offline).toBe(false);
  });
});
