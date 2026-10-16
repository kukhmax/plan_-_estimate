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
const K = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

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
    ['POST', `${roomsPath}/${R}/inspections`, 'inspection.create'],
    ['PATCH', `${wallsPath}/${S}/work-plan/occurrences/${K}/execution`, 'execution.transition'],
  ])('%s %s is %s', (method, path, kind) => {
    expect(matchWrite(method, path)?.kind).toBe(kind);
  });

  it('reads the ids out of the path', () => {
    expect(matchWrite('PATCH', `${openingsPath}/${O}`)?.ids).toEqual({ project: P, room: R, surface: S, opening: O });
  });

  it.each([
    ['POST', `${wallsPath}/generate`], // computed by the server
    ['POST', `${roomsPath}/${R}/inspections/${I}/complete`],
    ['POST', `${roomsPath}/${R}/inspections/${I}/reopen`],
    ['POST', `${wallsPath}/${S}/work-plan/execution/bulk`], // carries a status to the other walls: computed by the server
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


// --- Stage 19C.3: an inspection started without a signal, the status of a planned work ---------------------------------------------

const inspectionsPath = `${roomsPath}/${R}/inspections`;
const planPath = `${wallsPath}/${S}/work-plan`;
const executionPath = `${planPath}/occurrences/${K}/execution`;
const startInspection = (id = NEW) =>
  op('inspection.create', 'POST', inspectionsPath, { id, template_id: 'tpl', substrate: 'CONCRETE', plane: 'CEILING', quality_target: 'S2' }, id);
const savedPlan = (execution: Record<string, unknown>) => ({
  id: 'plan', substrate: 'CONCRETE', planned_works: [{ occurrence_key: K, position: 0, execution }, { occurrence_key: 'other', position: 1, execution: { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null } }],
});
const NOT_STARTED = { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null };
const transition = (status: string, expected: string, recorded?: string) =>
  op('execution.transition', 'PATCH', executionPath, { status, expected_status: expected, ...(recorded ? { recorded_at: recorded } : {}) }, K);

describe('an inspection started without a signal', () => {
  it('is a draft with no answers, in the list of its room and as a record of its own', () => {
    const started = startInspection();
    const inList = overlayRead(inspectionsPath, list(), [started]) as { items: Array<Record<string, unknown>> };
    expect(inList.items).toHaveLength(1);
    expect(inList.items[0]).toMatchObject({ id: NEW, room_id: R, status: 'DRAFT', plane: 'CEILING', surface_id: null, notes: null, answers: [], is_archived: false, _pending: true });

    const itself = resolveFromOutbox(`${inspectionsPath}/${NEW}`, [started]) as Record<string, unknown>;
    expect(itself).toMatchObject({ id: NEW, status: 'DRAFT', template_id: 'tpl', quality_target: 'S2', answers: [] });
  });

  it('has empty answers and findings, then the answers typed on the phone', () => {
    const started = startInspection();
    expect(resolveFromOutbox(`${inspectionsPath}/${NEW}/answers`, [started])).toEqual({ items: [], total: 0 });
    expect(resolveFromOutbox(`${inspectionsPath}/${NEW}/findings?include_resolved=true`, [started])).toEqual({ items: [], total: 0 });
    const typed = op('answers.put', 'PUT', `${inspectionsPath}/${NEW}/answers`, { answers: [{ question_id: 'q1', value_bool: true }] }, NEW);
    const answers = resolveFromOutbox(`${inspectionsPath}/${NEW}/answers`, [started, typed]) as { items: unknown[] };
    expect(answers.items).toMatchObject([{ question_id: 'q1', value_bool: true, _pending: true }]);
  });

  it('knows nothing about another inspection', () => {
    expect(resolveFromOutbox(`${inspectionsPath}/${I}/answers`, [startInspection()])).toBeUndefined();
  });

  it('the answers typed on the phone are laid over the inspection the server has, so the form shows them', () => {
    const server = { id: I, room_id: R, status: 'DRAFT', answers: [{ id: 'old', question_id: 'q-old', value_bool: false }] };
    const typed = op('answers.put', 'PUT', answersPath, { answers: [{ question_id: 'q1', value_number: '3.5' }] }, I);
    const shown = overlayRead(`${inspectionsPath}/${I}`, server, [typed]) as { answers: Array<Record<string, unknown>> };
    expect(shown.answers).toHaveLength(1); // the set is replaced, as the server replaces it
    expect(shown.answers[0]).toMatchObject({ question_id: 'q1', value_number: '3.5' });
    expect(overlayRead(`${inspectionsPath}/${NEW}`, { id: NEW, answers: [] }, [typed])).toEqual({ id: NEW, answers: [] }); // not about it
  });

  it('gives the screen the inspection with the id of the phone', () => {
    const started = startInspection();
    expect(optimisticResult(started, [], [started])).toMatchObject({ id: NEW, room_id: R, status: 'DRAFT', _pending: true });
  });

  it('is named in a few words', () => {
    const match = matchWrite('POST', inspectionsPath)!;
    expect(labelOf(match, { plane: 'CEILING', substrate: 'CONCRETE' })).toBe('CEILING CONCRETE');
  });
});

describe('the status of a planned work marked without a signal', () => {
  const tap = '2026-10-16T08:30:00.000Z';

  it('is shown on the work of the plan at once, with the moment of the tap', () => {
    const shown = overlayRead(planPath, savedPlan(NOT_STARTED), [transition('IN_PROGRESS', 'NOT_STARTED', tap)]) as { planned_works: Array<{ occurrence_key: string; execution: Record<string, unknown> }> };
    expect(shown.planned_works[0].execution).toMatchObject({ status: 'IN_PROGRESS', started_at: tap, completed_at: null, ready_after: null, _pending: true });
    expect(shown.planned_works[1].execution.status).toBe('NOT_STARTED'); // another work is left alone
  });

  it('uses the time the change was made when no moment came with it', () => {
    const waiting = transition('IN_PROGRESS', 'NOT_STARTED');
    const shown = overlayRead(planPath, savedPlan(NOT_STARTED), [waiting]) as { planned_works: Array<{ execution: Record<string, unknown> }> };
    expect(shown.planned_works[0].execution.started_at).toBe(new Date(waiting.createdAt).toISOString());
  });

  it('follows the rules of the server: finishing keeps the start; reopening keeps it and clears the finish; resetting clears the start', () => {
    const t1 = '2026-10-16T08:00:00.000Z', t2 = '2026-10-16T09:00:00.000Z';
    const work = (ops: OutboxOp[]) => (overlayRead(planPath, savedPlan(NOT_STARTED), ops) as { planned_works: Array<{ execution: Record<string, unknown> }> }).planned_works[0].execution;
    const start = transition('IN_PROGRESS', 'NOT_STARTED', t1);
    const finish = transition('COMPLETED', 'IN_PROGRESS', t2);
    expect(work([start, finish])).toMatchObject({ status: 'COMPLETED', started_at: t1, completed_at: t2 });
    expect(work([start, finish, transition('IN_PROGRESS', 'COMPLETED', '2026-10-16T10:00:00.000Z')])).toMatchObject({ status: 'IN_PROGRESS', started_at: t1, completed_at: null });
    expect(work([start, transition('NOT_STARTED', 'IN_PROGRESS', t2)])).toMatchObject({ status: 'NOT_STARTED', started_at: null });
    expect(work([transition('COMPLETED', 'NOT_STARTED', t2)])).toMatchObject({ status: 'COMPLETED', started_at: t2, completed_at: t2 }); // the shortcut
  });

  it('leaves another surface, another path and a plan the change is not about alone', () => {
    expect(overlayRead(`${wallsPath}/${NEW}/work-plan`, savedPlan(NOT_STARTED), [transition('IN_PROGRESS', 'NOT_STARTED', tap)])).toEqual(savedPlan(NOT_STARTED));
    expect(overlayRead(`${wallsPath}/${S}`, { id: S }, [transition('IN_PROGRESS', 'NOT_STARTED', tap)])).toEqual({ id: S });
  });

  it('the screen that made the change gets the answer of the server\'s shape, built on the changes before it', () => {
    const start = transition('IN_PROGRESS', 'NOT_STARTED', '2026-10-16T08:00:00.000Z');
    const finish = transition('COMPLETED', 'IN_PROGRESS', '2026-10-16T09:00:00.000Z');
    const saved = [{ path: planPath, data: savedPlan(NOT_STARTED) }];
    expect(optimisticResult(start, saved, [start])).toEqual({ occurrence_key: K, status: 'IN_PROGRESS', started_at: '2026-10-16T08:00:00.000Z', completed_at: null, ready_after: null });
    expect(optimisticResult(finish, saved, [start, finish])).toEqual({ occurrence_key: K, status: 'COMPLETED', started_at: '2026-10-16T08:00:00.000Z', completed_at: '2026-10-16T09:00:00.000Z', ready_after: null });
  });

  it('the answer to a change is not changed by the changes made after it', () => {
    const start = transition('IN_PROGRESS', 'NOT_STARTED', '2026-10-16T08:00:00.000Z');
    const finish = transition('COMPLETED', 'IN_PROGRESS', '2026-10-16T09:00:00.000Z');
    const saved = [{ path: planPath, data: savedPlan(NOT_STARTED) }];
    expect(optimisticResult(start, saved, [start, finish])).toMatchObject({ status: 'IN_PROGRESS', completed_at: null });
    // the work was started, reset and started again: the answer to the FIRST start knows nothing of the later moments
    const reset = transition('NOT_STARTED', 'IN_PROGRESS', '2026-10-16T08:30:00.000Z');
    const again = transition('IN_PROGRESS', 'NOT_STARTED', '2026-10-16T10:00:00.000Z');
    expect(optimisticResult(start, saved, [start, reset, again])).toMatchObject({ status: 'IN_PROGRESS', started_at: '2026-10-16T08:00:00.000Z' });
  });

  it('with no saved plan the change still answers with its own status and moment', () => {
    const only = transition('IN_PROGRESS', 'NOT_STARTED', tap);
    expect(optimisticResult(only, [], [only])).toMatchObject({ occurrence_key: K, status: 'IN_PROGRESS', started_at: tap });
  });

  it('is named by its status', () => {
    expect(labelOf(matchWrite('PATCH', executionPath)!, { status: 'COMPLETED' })).toBe('COMPLETED');
  });
});
