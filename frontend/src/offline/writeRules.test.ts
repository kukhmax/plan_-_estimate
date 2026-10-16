import { describe, expect, it } from 'vitest';
import type { OutboxKind, OutboxOp } from './opTypes';
import { labelOf, matchWrite, optimisticResult, overlayRead, resolveFromOutbox } from './writeRules';

const P = '11111111-1111-4111-8111-111111111111';
const R = '22222222-2222-4222-8222-222222222222';
const S = '33333333-3333-4333-8333-333333333333';
const O = '44444444-4444-4444-8444-444444444444';
const A = '55555555-5555-4555-8555-555555555555';
const N = '66666666-6666-4666-8666-666666666666';
const I = '77777777-7777-4777-8777-777777777777';
const NEW = '99999999-9999-4999-8999-999999999999';

const T0 = Date.UTC(2026, 9, 15, 12, 0, 0);
let seq = 0;
function op(kind: OutboxKind, method: OutboxOp['method'], path: string, body: Record<string, unknown> | null, entityId: string | null, extra: Partial<OutboxOp> = {}): OutboxOp {
  return { seq: ++seq, ownerId: 'o', createdAt: T0 + seq * 1000, method, path, body, kind, entityId, label: '', status: 'pending', attempts: 0, ...extra };
}
const roomsPath = `/api/projects/${P}/rooms`;
const wallsPath = `${roomsPath}/${R}/surfaces`;
const openingsPath = `${wallsPath}/${S}/openings`;
const segmentsPath = `${roomsPath}/${R}/area-segments`;
const notesPath = `/api/projects/${P}/notes`;
const answersPath = `${roomsPath}/${R}/inspections/${I}/answers`;
const list = (...items: unknown[]) => ({ items, total: items.length });

describe('matchWrite (Stage 19C)', () => {
  it.each([
    ['POST', notesPath, 'note.create'],
    ['PATCH', `${notesPath}/${N}`, 'note.update'],
    ['DELETE', `${notesPath}/${N}`, 'note.delete'],
    ['POST', roomsPath, 'room.create'],
    ['PATCH', `${roomsPath}/${R}`, 'room.update'],
    ['POST', `${roomsPath}/${R}/archive`, 'room.archive'],
    ['POST', `${roomsPath}/${R}/restore`, 'room.restore'],
    ['POST', wallsPath, 'surface.create'],
    ['PATCH', `${wallsPath}/${S}`, 'surface.update'],
    ['POST', `${wallsPath}/${S}/archive`, 'surface.archive'],
    ['POST', `${wallsPath}/${S}/restore`, 'surface.restore'],
    ['POST', openingsPath, 'opening.create'],
    ['PATCH', `${openingsPath}/${O}`, 'opening.update'],
    ['POST', `${openingsPath}/${O}/archive`, 'opening.archive'],
    ['POST', `${openingsPath}/${O}/restore`, 'opening.restore'],
    ['POST', segmentsPath, 'segment.create'],
    ['PATCH', `${segmentsPath}/${A}`, 'segment.update'],
    ['POST', `${segmentsPath}/${A}/archive`, 'segment.archive'],
    ['POST', `${segmentsPath}/${A}/restore`, 'segment.restore'],
    ['PUT', answersPath, 'answers.put'],
  ])('%s %s is %s', (method, path, kind) => {
    expect(matchWrite(method, path)?.kind).toBe(kind);
  });

  it('reads the ids out of the path', () => {
    expect(matchWrite('PATCH', `${openingsPath}/${O}`)?.ids).toEqual({ project: P, room: R, surface: S, opening: O });
  });

  it.each([
    ['POST', `${wallsPath}/generate`], // computed by the server
    ['POST', `${roomsPath}/${R}/inspections`],
    ['POST', `${roomsPath}/${R}/inspections/${I}/complete`],
    ['POST', `/api/projects/${P}/photos`],
    ['POST', `/api/projects/${P}/estimates/generate`],
    ['POST', `/api/projects/${P}/archive`],
    ['POST', '/api/calendar/reminders'],
    ['PUT', `${wallsPath}/${S}/work-plan`],
    ['GET', roomsPath],
    ['POST', `${roomsPath}/not-a-uuid/archive`],
    ['DELETE', `${roomsPath}/${R}`],
  ])('%s %s needs the server', (method, path) => {
    expect(matchWrite(method, path)).toBeNull();
  });
});

describe('overlayRead: a waiting change laid over what the server said', () => {
  it('a new room is added to the list, marked as waiting, with the typed values', () => {
    const created = op('room.create', 'POST', roomsPath, { id: NEW, name: 'Kuchnia', length: 4, width: 3, height: 2.6 }, NEW);
    const view = overlayRead(roomsPath, list({ id: R, name: 'Salon' }), [created]) as { items: Array<Record<string, unknown>>; total: number };

    expect(view.total).toBe(2);
    expect(view.items[0]).toEqual({ id: R, name: 'Salon' });
    expect(view.items[1]).toMatchObject({ id: NEW, project_id: P, name: 'Kuchnia', length: 4, is_archived: false, _pending: true, description: null });
  });

  it('is applied once even when the server already has the record (a change sent but not yet removed)', () => {
    const created = op('room.create', 'POST', roomsPath, { id: NEW, name: 'Kuchnia' }, NEW);
    const view = overlayRead(roomsPath, list({ id: NEW, name: 'Kuchnia' }), [created]) as { items: unknown[] };
    expect(view.items).toHaveLength(1);
  });

  it('a new note goes first (the newest first), the others at the end', () => {
    const note = op('note.create', 'POST', notesPath, { id: NEW, body: 'Nowa' }, NEW);
    const notes = overlayRead(notesPath, list({ id: N, body: 'Stara' }), [note]) as { items: Array<{ id: string }> };
    expect(notes.items.map((i) => i.id)).toEqual([NEW, N]);
    const wall = op('surface.create', 'POST', wallsPath, { id: NEW, name: 'Wall 5', surface_type: 'WALL', width: 2, height: 2.7 }, NEW);
    const walls = overlayRead(wallsPath, list({ id: S }), [wall]) as { items: Array<{ id: string }> };
    expect(walls.items.map((i) => i.id)).toEqual([S, NEW]);
  });

  it('a change of a record is laid over the list and over the record itself', () => {
    const change = op('room.update', 'PATCH', `${roomsPath}/${R}`, { name: 'Salon 2', length: 5 }, R);

    const inList = overlayRead(roomsPath, list({ id: R, name: 'Salon', length: 4 }), [change]) as { items: Array<Record<string, unknown>> };
    expect(inList.items[0]).toMatchObject({ id: R, name: 'Salon 2', length: 5, _pending: true });
    const single = overlayRead(`${roomsPath}/${R}`, { id: R, name: 'Salon', length: 4 }, [change]);
    expect(single).toMatchObject({ id: R, name: 'Salon 2', length: 5, _pending: true });
    expect(overlayRead(`${roomsPath}/${NEW}`, { id: NEW, name: 'Inny' }, [change])).toEqual({ id: NEW, name: 'Inny' });
  });

  it('archiving takes the record out of the list that hides archived ones, and marks it in the list that shows them', () => {
    const archive = op('surface.archive', 'POST', `${wallsPath}/${S}/archive`, null, S);
    const rows = list({ id: S, is_archived: false }, { id: NEW, is_archived: false });

    expect((overlayRead(wallsPath, rows, [archive]) as { items: unknown[] }).items).toEqual([{ id: NEW, is_archived: false }]);
    const all = overlayRead(`${wallsPath}?include_archived=true`, rows, [archive]) as { items: Array<Record<string, unknown>> };
    expect(all.items[0]).toMatchObject({ id: S, is_archived: true, _pending: true });
    const restore = op('surface.restore', 'POST', `${wallsPath}/${S}/restore`, null, S);
    const back = overlayRead(`${wallsPath}?include_archived=true`, all, [restore]) as { items: Array<Record<string, unknown>> };
    expect(back.items[0]).toMatchObject({ id: S, is_archived: false });
  });

  it('removing a note takes it out', () => {
    const del = op('note.delete', 'DELETE', `${notesPath}/${N}`, null, N);
    expect((overlayRead(notesPath, list({ id: N }, { id: NEW }), [del]) as { items: unknown[]; total: number }).total).toBe(1);
  });

  it('the answers of an inspection are replaced by the set typed on the phone', () => {
    const put = op('answers.put', 'PUT', answersPath, { answers: [{ question_id: 'q1', value_bool: true }, { question_id: 'q2', value_text: 'wilgotne' }] }, I);
    const view = overlayRead(answersPath, list({ id: 'a1', question_id: 'q1', value_bool: false }), [put]) as { items: Array<Record<string, unknown>>; total: number };
    expect(view.total).toBe(2);
    expect(view.items[0]).toMatchObject({ question_id: 'q1', value_bool: true, value_text: null, _pending: true });
    expect(view.items[1]).toMatchObject({ question_id: 'q2', value_text: 'wilgotne' });
  });

  it('changes are applied in the order they were made, and the ones the server refused are not applied', () => {
    const first = op('note.create', 'POST', notesPath, { id: NEW, body: 'A' }, NEW);
    const second = op('note.update', 'PATCH', `${notesPath}/${NEW}`, { body: 'B' }, NEW);
    const refused = op('note.update', 'PATCH', `${notesPath}/${NEW}`, { body: 'C' }, NEW, { status: 'failed' });
    const view = overlayRead(notesPath, list(), [first, second, refused]) as { items: Array<{ body: string }> };
    expect(view.items.map((i) => i.body)).toEqual(['B']);
  });

  it('leaves alone a path it is not about, and what is not a list or a record', () => {
    const created = op('room.create', 'POST', roomsPath, { id: NEW, name: 'X' }, NEW);
    const other = list({ id: 'z' });
    expect(overlayRead(`/api/projects/${R}/rooms`, other, [created])).toBe(other);
    expect(overlayRead(roomsPath, 'text', [created])).toBe('text');
    expect(overlayRead(roomsPath, null, [created])).toBeNull();
  });
});

describe('resolveFromOutbox: a record the phone made and the server has not seen yet', () => {
  const room = op('room.create', 'POST', roomsPath, { id: NEW, name: 'Kuchnia', length: 4 }, NEW);

  it('gives the room itself, with the later changes applied', () => {
    const rename = op('room.update', 'PATCH', `${roomsPath}/${NEW}`, { name: 'Kuchnia 2' }, NEW);
    expect(resolveFromOutbox(`${roomsPath}/${NEW}`, [room, rename])).toMatchObject({ id: NEW, name: 'Kuchnia 2', length: 4, _pending: true });
  });

  it('gives empty lists of a room made on the phone, plus what was made in it', () => {
    const wall = op('surface.create', 'POST', `${roomsPath}/${NEW}/surfaces`, { id: A, name: 'Wall 1', surface_type: 'WALL' }, A);
    expect(resolveFromOutbox(`${roomsPath}/${NEW}/surfaces`, [room, wall])).toMatchObject({ total: 1, items: [{ id: A, room_id: NEW }] });
    expect(resolveFromOutbox(`${roomsPath}/${NEW}/area-segments`, [room])).toEqual({ items: [], total: 0 });
    expect(resolveFromOutbox(`${roomsPath}/${NEW}/inspections`, [room])).toEqual({ items: [], total: 0 });
  });

  it('gives the empty openings of a wall made on the phone', () => {
    const wall = op('surface.create', 'POST', `${roomsPath}/${R}/surfaces`, { id: NEW, name: 'Wall 9', surface_type: 'WALL' }, NEW);
    expect(resolveFromOutbox(`${roomsPath}/${R}/surfaces/${NEW}/openings`, [wall])).toEqual({ items: [], total: 0 });
  });

  it('knows nothing about other paths, or about a record whose creation the server refused', () => {
    expect(resolveFromOutbox(`${roomsPath}/${R}`, [room])).toBeUndefined();
    expect(resolveFromOutbox(`${roomsPath}/${NEW}/risks`, [room])).toBeUndefined();
    expect(resolveFromOutbox(`${roomsPath}/${NEW}`, [{ ...room, status: 'failed' }])).toBeUndefined();
  });
});

describe('optimisticResult: what the screen that made the change gets back', () => {
  it('a create gives the record with the id of the phone', () => {
    const create = op('opening.create', 'POST', openingsPath, { id: NEW, opening_type: 'DOOR', width: 0.9, height: 2 }, NEW);
    expect(optimisticResult(create, [], [create])).toMatchObject({ id: NEW, surface_id: S, opening_type: 'DOOR', quantity: 1, is_archived: false, _pending: true });
  });

  it('a change gives the saved record with the change laid over it', () => {
    const change = op('surface.update', 'PATCH', `${wallsPath}/${S}`, { width: 3.2 }, S);
    const saved = [{ path: wallsPath, data: list({ id: S, name: 'Wall 1', width: 3, height: 2.7 }) }];
    expect(optimisticResult(change, saved, [change])).toMatchObject({ id: S, name: 'Wall 1', width: 3.2, height: 2.7, _pending: true });
  });

  it('a change of a record that is only in the outbox gives that record', () => {
    const create = op('surface.create', 'POST', wallsPath, { id: NEW, name: 'Wall 5', surface_type: 'WALL', width: 2 }, NEW);
    const change = op('surface.update', 'PATCH', `${wallsPath}/${NEW}`, { width: 2.5 }, NEW);
    expect(optimisticResult(change, [], [create, change])).toMatchObject({ id: NEW, width: 2.5, name: 'Wall 5' });
  });

  it('with nothing known, a change still gives its id and fields', () => {
    const change = op('room.update', 'PATCH', `${roomsPath}/${R}`, { name: 'X' }, R);
    expect(optimisticResult(change, [], [change])).toMatchObject({ id: R, name: 'X', _pending: true });
  });

  it('archiving marks the record; removing gives nothing; answers give the set', () => {
    const archive = op('room.archive', 'POST', `${roomsPath}/${R}/archive`, null, R);
    expect(optimisticResult(archive, [{ path: `${roomsPath}/${R}`, data: { id: R, name: 'S' } }], [archive])).toMatchObject({ id: R, is_archived: true });
    const del = op('note.delete', 'DELETE', `${notesPath}/${N}`, null, N);
    expect(optimisticResult(del, [], [del])).toBeUndefined();
    const put = op('answers.put', 'PUT', answersPath, { answers: [{ question_id: 'q1', value_bool: true }] }, I);
    expect(optimisticResult(put, [], [put])).toMatchObject({ total: 1 });
  });
});

describe('labelOf', () => {
  it('names the change in a few words', () => {
    const note = matchWrite('POST', notesPath)!;
    const label = labelOf(note, { body: '  Zadzwonić do klienta w sprawie koloru ścian w salonie i sypialni  ' });
    expect(label).toHaveLength(40);
    expect(label.startsWith('Zadzwonić do klienta')).toBe(true);
    expect(labelOf(matchWrite('POST', roomsPath)!, { name: 'Kuchnia' })).toBe('Kuchnia');
    expect(labelOf(matchWrite('POST', openingsPath)!, { opening_type: 'DOOR', width: 0.9, height: 2 })).toBe('DOOR 0.9 × 2');
    expect(labelOf(matchWrite('POST', segmentsPath)!, { plane: 'FLOOR', width: 2, height: 3 })).toBe('FLOOR 2 × 3');
    expect(labelOf(matchWrite('PUT', answersPath)!, null)).toBe('');
  });
});
