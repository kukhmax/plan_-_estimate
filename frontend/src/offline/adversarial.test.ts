import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRoom, archiveRoom, fetchRoom, fetchRooms, restoreRoom, updateRoom } from '../api/rooms';
import { createSurface, archiveSurface, fetchSurfaces, restoreSurface, updateSurface } from '../api/surfaces';
import { createProjectNote, deleteProjectNote, fetchProjectNotes, updateProjectNote } from '../api/projectNotes';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { listOps } from './outbox';
import { getOutboxCounts, resetSyncStateForTests } from './outboxState';
import { setOfflineOwner } from './readCache';
import { drainOutbox } from './sync';

// Stage 19F — adversarial checks of the whole offline way. Two questions, asked over many random histories:
//  1. what the phone SHOWS while it has no signal (saved copies + waiting changes) is what the server will hold after the sending;
//  2. whatever goes wrong on the way (no signal, a lost answer, a server error), the server ends up with exactly the changes made.

const P = '11111111-1111-4111-8111-111111111111';
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function prng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Rec { id: string; name: string; archived: boolean }
interface World {
  notes: Array<{ id: string; body: string }>; // newest first
  rooms: Rec[]; // in the order they were made
  surfaces: Record<string, Rec[]>;
}
const clone = (w: World): World => JSON.parse(JSON.stringify(w));

/** A server that does what the real one does for these requests (a create under an id is idempotent), and can be made to misbehave. */
function makeServer(world: World, chaos: () => 'ok' | 'drop' | 'lost' | 'error') {
  const received: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const state = { up: true, errorsInRow: 0 };
  const rec = (r: Rec) => ({ id: r.id, name: r.name, is_archived: r.archived, project_id: P, room_id: undefined });
  const handle = (method: string, url: string, body: Record<string, unknown> | null): Response => {
    const [path, query = ''] = url.split('?');
    const all = /include_archived=true/.test(query);
    let m: RegExpExecArray | null;
    if (method === 'GET' && path === `/api/projects/${P}/notes`) return json({ items: world.notes.map((n) => ({ ...n, project_id: P })), total: world.notes.length });
    if (method === 'POST' && path === `/api/projects/${P}/notes`) {
      const id = body!.id as string;
      if (!world.notes.some((n) => n.id === id)) world.notes.unshift({ id, body: body!.body as string });
      return json(world.notes.find((n) => n.id === id), 201);
    }
    if ((m = new RegExp(`^/api/projects/${P}/notes/([^/]+)$`).exec(path))) {
      const i = world.notes.findIndex((n) => n.id === m![1]);
      if (i < 0) return json({ detail: 'Note not found' }, 404);
      if (method === 'PATCH') world.notes[i].body = body!.body as string;
      if (method === 'DELETE') { world.notes.splice(i, 1); return { ok: true, status: 204, json: async () => undefined } as unknown as Response; }
      return json(world.notes[i]);
    }
    if (method === 'GET' && path === `/api/projects/${P}/rooms`) { const items = world.rooms.filter((r) => all || !r.archived); return json({ items: items.map(rec), total: items.length }); }
    if (method === 'POST' && path === `/api/projects/${P}/rooms`) {
      const id = body!.id as string;
      if (!world.rooms.some((r) => r.id === id)) { world.rooms.push({ id, name: body!.name as string, archived: false }); world.surfaces[id] = []; }
      return json(rec(world.rooms.find((r) => r.id === id)!), 201);
    }
    if ((m = new RegExp(`^/api/projects/${P}/rooms/([^/]+)(?:/(archive|restore))?$`).exec(path)) && (method === 'GET' || method === 'PATCH' || method === 'POST')) {
      const r = world.rooms.find((x) => x.id === m![1]);
      if (!r) return json({ detail: 'Room not found' }, 404);
      if (method === 'PATCH') r.name = body!.name as string;
      if (m[2] === 'archive') r.archived = true;
      if (m[2] === 'restore') r.archived = false;
      return json(rec(r));
    }
    if ((m = new RegExp(`^/api/projects/${P}/rooms/([^/]+)/surfaces$`).exec(path))) {
      const list = world.surfaces[m[1]];
      if (!list) return json({ detail: 'Room not found' }, 404);
      if (method === 'GET') { const items = list.filter((s) => all || !s.archived); return json({ items: items.map(rec), total: items.length }); }
      const id = body!.id as string;
      if (!list.some((s) => s.id === id)) list.push({ id, name: body!.name as string, archived: false });
      return json(rec(list.find((s) => s.id === id)!), 201);
    }
    if ((m = new RegExp(`^/api/projects/${P}/rooms/([^/]+)/surfaces/([^/]+)(?:/(archive|restore))?$`).exec(path))) {
      const s = world.surfaces[m[1]]?.find((x) => x.id === m![2]);
      if (!s) return json({ detail: 'Surface not found' }, 404);
      if (method === 'PATCH') s.name = body!.name as string;
      if (m[3] === 'archive') s.archived = true;
      if (m[3] === 'restore') s.archived = false;
      return json(rec(s));
    }
    return json({ detail: `unexpected ${method} ${path}` }, 500);
  };
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    const fate = method === 'GET' ? 'ok' : chaos();
    if (fate === 'drop') throw new TypeError('Failed to fetch'); // never reached the server
    if (fate === 'error' && state.errorsInRow < 3) { state.errorsInRow += 1; return json({ detail: 'down' }, 503); }
    state.errorsInRow = 0;
    if (method !== 'GET') received.push({ method, path: String(url), body });
    const answer = handle(method, String(url), body);
    if (fate === 'lost') throw new TypeError('Failed to fetch'); // the server did it, the phone never heard
    return answer;
  });
  return { handler, state, received };
}

const norm = (rs: Rec[], archivedToo: boolean) => rs.filter((r) => archivedToo || !r.archived).map((r) => `${r.id}|${r.name}|${r.archived ? 'A' : '-'}`);
const fromList = (items: Array<{ id: string; name: string; is_archived: boolean }>) => items.map((r) => `${r.id}|${r.name}|${r.is_archived ? 'A' : '-'}`);

async function phoneSees(world: World) {
  const rooms = (await fetchRooms(P)).items;
  const roomsAll = (await fetchRooms(P, true)).items;
  expect(fromList(rooms), 'rooms').toEqual(norm(world.rooms, false));
  expect(fromList(roomsAll), 'rooms (with archived)').toEqual(norm(world.rooms, true));
  expect((await fetchProjectNotes(P)).items.map((n) => `${n.id}|${n.body}`), 'notes').toEqual(world.notes.map((n) => `${n.id}|${n.body}`));
  for (const room of world.rooms) {
    const one = await fetchRoom(P, room.id);
    expect([one.name, one.is_archived], `room ${room.id}`).toEqual([room.name, room.archived]);
    if (room.archived) continue;
    expect(fromList((await fetchSurfaces(P, room.id)).items), `surfaces of ${room.id}`).toEqual(norm(world.surfaces[room.id], false));
    expect(fromList((await fetchSurfaces(P, room.id, true)).items), `surfaces of ${room.id} (with archived)`).toEqual(norm(world.surfaces[room.id], true));
  }
}

/** One random, VALID change to the world, made through the same functions the screens use. */
async function randomChange(world: World, rnd: () => number, n: number) {
  const pick = <T,>(xs: T[]): T | undefined => xs[Math.floor(rnd() * xs.length)];
  const activeRooms = world.rooms.filter((r) => !r.archived);
  const choices: Array<() => Promise<void>> = [];
  choices.push(async () => { const note = await createProjectNote(P, `n${n}`); world.notes.unshift({ id: note.id, body: `n${n}` }); });
  if (world.notes.length) {
    choices.push(async () => { const x = pick(world.notes)!; await updateProjectNote(P, x.id, `u${n}`); x.body = `u${n}`; });
    choices.push(async () => { const x = pick(world.notes)!; await deleteProjectNote(P, x.id); world.notes.splice(world.notes.indexOf(x), 1); });
  }
  choices.push(async () => { const r = await createRoom(P, { name: `R${n}` }); world.rooms.push({ id: r.id, name: `R${n}`, archived: false }); world.surfaces[r.id] = []; });
  if (activeRooms.length) {
    choices.push(async () => { const x = pick(activeRooms)!; await updateRoom(P, x.id, { name: `r${n}` }); x.name = `r${n}`; });
    choices.push(async () => { const x = pick(activeRooms)!; await archiveRoom(P, x.id); x.archived = true; });
    choices.push(async () => { const room = pick(activeRooms)!; const s = await createSurface(P, room.id, { name: `S${n}`, surface_type: 'WALL' }); world.surfaces[room.id].push({ id: s.id, name: `S${n}`, archived: false }); });
    const withSurfaces = activeRooms.filter((r) => world.surfaces[r.id].length);
    if (withSurfaces.length) {
      choices.push(async () => { const room = pick(withSurfaces)!; const s = pick(world.surfaces[room.id])!; await updateSurface(P, room.id, s.id, { name: `s${n}` }); s.name = `s${n}`; });
      choices.push(async () => { const room = pick(withSurfaces)!; const s = pick(world.surfaces[room.id].filter((x) => !x.archived)); if (!s) return; await archiveSurface(P, room.id, s.id); s.archived = true; });
      choices.push(async () => { const room = pick(withSurfaces)!; const s = pick(world.surfaces[room.id].filter((x) => x.archived)); if (!s) return; await restoreSurface(P, room.id, s.id); s.archived = false; });
    }
  }
  const archivedRooms = world.rooms.filter((r) => r.archived);
  if (archivedRooms.length) choices.push(async () => { const x = pick(archivedRooms)!; await restoreRoom(P, x.id); x.archived = false; });
  const chosen = pick(choices)!;
  await chosen();
}

async function startFromSavedCopies(server: World) {
  // in the car: everything the screens will ask for is read and kept on the phone
  await fetchProjectNotes(P);
  await fetchRooms(P);
  await fetchRooms(P, true);
  for (const room of server.rooms) {
    await fetchRoom(P, room.id);
    await fetchSurfaces(P, room.id);
    await fetchSurfaces(P, room.id, true);
  }
}

const SEEDS = Array.from({ length: 120 }, (_, i) => 1000 + i * 7919);

describe('what the phone shows without a signal is what the server will hold afterwards (Stage 19F)', () => {
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

  it.each(SEEDS)('seed %i: notes, rooms and walls made, changed, archived and removed in a random order', async (seed) => {
    const rnd = prng(seed);
    const server: World = { notes: [{ id: '00000000-0000-4000-8000-000000000002', body: 'old two' }, { id: '00000000-0000-4000-8000-000000000001', body: 'old one' }], rooms: [{ id: '00000000-0000-4000-8000-000000000010', name: 'Old', archived: false }, { id: '00000000-0000-4000-8000-000000000011', name: 'Gone', archived: true }], surfaces: { '00000000-0000-4000-8000-000000000010': [{ id: '00000000-0000-4000-8000-000000000020', name: 'Old wall', archived: false }], '00000000-0000-4000-8000-000000000011': [] } };
    const stub = makeServer(server, () => 'ok');
    vi.stubGlobal('fetch', stub.handler);
    await startFromSavedCopies(server);
    const world = clone(server);

    stub.state.up = false;
    reportNetworkFailure();
    const steps = 8 + Math.floor(rnd() * 10);
    for (let n = 1; n <= steps; n += 1) {
      await randomChange(world, rnd, n);
      try {
        await phoneSees(world); // after EVERY change the phone shows exactly what the owner made
      } catch (error) {
        const waiting = (await listOps()).map((o) => `${o.kind}(${String(o.entityId ?? '').slice(0, 8)}${o.body?.name ? ` ${String(o.body.name)}` : ''})`);
        throw new Error(`${(error as Error).message}\n  made so far: ${waiting.join(', ')}`);
      }
    }

    stub.state.up = true;
    reportNetworkSuccess();
    const result = await drainOutbox();
    expect(result, 'nothing refused, nothing left').toMatchObject({ refused: 0, stoppedBy: null });
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 0 });
    expect(server).toEqual(world); // the server holds exactly what the owner made
    await phoneSees(world); // and a read from it agrees
  }, 60_000);
});

describe('whatever goes wrong on the way, the server gets the changes once (Stage 19F)', () => {
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

  it.each(SEEDS.slice(0, 80))('seed %i: dropped requests, lost answers and server errors in the middle of the sending', async (seed) => {
    const rnd = prng(seed);
    const server: World = { notes: [], rooms: [{ id: '00000000-0000-4000-8000-000000000010', name: 'Old', archived: false }], surfaces: { '00000000-0000-4000-8000-000000000010': [] } };
    const chaos = () => {
      const x = rnd();
      return x < 0.2 ? 'drop' : x < 0.4 ? 'lost' : x < 0.5 ? 'error' : 'ok';
    };
    const stub = makeServer(server, chaos);
    vi.stubGlobal('fetch', stub.handler);
    await startFromSavedCopies(server);
    const world = clone(server);

    stub.state.up = false;
    reportNetworkFailure();
    const steps = 8 + Math.floor(rnd() * 10);
    for (let n = 1; n <= steps; n += 1) await randomChange(world, rnd, n);
    const made = (await listOps()).length;

    stub.state.up = true;
    reportNetworkSuccess();
    let rounds = 0;
    while (getOutboxCounts().pending > 0 && rounds < 60) {
      await drainOutbox();
      reportNetworkSuccess(); // the signal comes back between the tries (the engine waits for it)
      rounds += 1;
    }

    expect(getOutboxCounts(), `after ${rounds} tries`).toEqual({ pending: 0, failed: 0 });
    expect(server, 'the server holds exactly the changes, none twice').toEqual(world);
    expect(made).toBeGreaterThan(0);
  }, 60_000);
});
