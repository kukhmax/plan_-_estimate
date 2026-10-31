import type { OutboxKind, OutboxOp } from './opTypes';

/**
 * Which writes can be made without a signal (Stage 19C), and what each of them does to what the screens show.
 *
 * The saved copies (`readCache`) always hold what the server said last. A change waiting in the outbox is laid over them when they are
 * read (`overlayRead`), so the screens show the record as the owner left it, marked `_pending`. Nothing here computes anything the
 * server computes (areas, totals): a record made on the phone carries only what the owner typed.
 */
const U = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const P = `/api/projects/(?<project>${U})`;
const R = `${P}/rooms/(?<room>${U})`;
const S = `${R}/surfaces/(?<surface>${U})`;

export type Entity = 'note' | 'room' | 'surface' | 'opening' | 'segment' | 'answers' | 'inspection' | 'execution' | 'payment';
export type Action = 'create' | 'update' | 'archive' | 'restore' | 'delete' | 'replace' | 'transition';
export type Ids = Partial<Record<'project' | 'room' | 'surface' | 'opening' | 'segment' | 'note' | 'inspection' | 'occurrence' | 'payment', string>>;

interface Rule {
  kind: OutboxKind;
  method: OutboxOp['method'];
  re: RegExp;
  entity: Entity;
  action: Action;
}

const rule = (kind: OutboxKind, method: Rule['method'], pattern: string, entity: Entity, action: Action): Rule => ({
  kind,
  method,
  re: new RegExp(`^${pattern}$`, 'i'),
  entity,
  action,
});

const RULES: readonly Rule[] = [
  rule('note.create', 'POST', `${P}/notes`, 'note', 'create'),
  rule('note.update', 'PATCH', `${P}/notes/(?<note>${U})`, 'note', 'update'),
  rule('note.delete', 'DELETE', `${P}/notes/(?<note>${U})`, 'note', 'delete'),
  rule('room.create', 'POST', `${P}/rooms`, 'room', 'create'),
  rule('room.update', 'PATCH', R, 'room', 'update'),
  rule('room.archive', 'POST', `${R}/archive`, 'room', 'archive'),
  rule('room.restore', 'POST', `${R}/restore`, 'room', 'restore'),
  rule('surface.create', 'POST', `${R}/surfaces`, 'surface', 'create'),
  rule('surface.update', 'PATCH', S, 'surface', 'update'),
  rule('surface.archive', 'POST', `${S}/archive`, 'surface', 'archive'),
  rule('surface.restore', 'POST', `${S}/restore`, 'surface', 'restore'),
  rule('opening.create', 'POST', `${S}/openings`, 'opening', 'create'),
  rule('opening.update', 'PATCH', `${S}/openings/(?<opening>${U})`, 'opening', 'update'),
  rule('opening.archive', 'POST', `${S}/openings/(?<opening>${U})/archive`, 'opening', 'archive'),
  rule('opening.restore', 'POST', `${S}/openings/(?<opening>${U})/restore`, 'opening', 'restore'),
  rule('segment.create', 'POST', `${R}/area-segments`, 'segment', 'create'),
  rule('segment.update', 'PATCH', `${R}/area-segments/(?<segment>${U})`, 'segment', 'update'),
  rule('segment.archive', 'POST', `${R}/area-segments/(?<segment>${U})/archive`, 'segment', 'archive'),
  rule('segment.restore', 'POST', `${R}/area-segments/(?<segment>${U})/restore`, 'segment', 'restore'),
  rule('answers.put', 'PUT', `${R}/inspections/(?<inspection>${U})/answers`, 'answers', 'replace'),
  // Stage 19C.3: starting an inspection, and the status of a planned work (it carries the moment of the tap)
  rule('inspection.create', 'POST', `${R}/inspections`, 'inspection', 'create'),
  rule('execution.transition', 'PATCH', `${S}/work-plan/occurrences/(?<occurrence>${U})/execution`, 'execution', 'transition'),
  // IA-4: the settlement records of an object (a record is archived, never erased)
  rule('payment.create', 'POST', `${P}/payments`, 'payment', 'create'),
  rule('payment.update', 'PATCH', `${P}/payments/(?<payment>${U})`, 'payment', 'update'),
  rule('payment.archive', 'POST', `${P}/payments/(?<payment>${U})/archive`, 'payment', 'archive'),
  rule('payment.restore', 'POST', `${P}/payments/(?<payment>${U})/restore`, 'payment', 'restore'),
];

const BY_KIND = new Map(RULES.map((r) => [r.kind, r]));

export interface WriteMatch {
  kind: OutboxKind;
  entity: Entity;
  action: Action;
  ids: Ids;
}

export function matchWrite(method: string, path: string): WriteMatch | null {
  const verb = method.toUpperCase();
  for (const r of RULES) {
    if (r.method !== verb) continue;
    const found = r.re.exec(path);
    if (found) return { kind: r.kind, entity: r.entity, action: r.action, ids: { ...(found.groups as Ids) } };
  }
  return null;
}

function matchOp(op: OutboxOp): WriteMatch | null {
  const known = BY_KIND.get(op.kind);
  if (!known) return null;
  const found = known.re.exec(op.path);
  return found ? { kind: known.kind, entity: known.entity, action: known.action, ids: { ...(found.groups as Ids) } } : null;
}

interface EntityDef {
  listPath(ids: Ids): string;
  itemPath(ids: Ids, id: string): string | null;
  fromParent(ids: Ids): Record<string, unknown>;
  defaults: Record<string, unknown>;
  newestFirst?: boolean;
  idKey: keyof Ids;
}

const ENTITIES: Record<Exclude<Entity, 'answers' | 'execution'>, EntityDef> = {
  note: {
    listPath: (ids) => `/api/projects/${ids.project}/notes`,
    itemPath: () => null,
    fromParent: (ids) => ({ project_id: ids.project }),
    defaults: {},
    newestFirst: true,
    idKey: 'note',
  },
  room: {
    listPath: (ids) => `/api/projects/${ids.project}/rooms`,
    itemPath: (ids, id) => `/api/projects/${ids.project}/rooms/${id}`,
    fromParent: (ids) => ({ project_id: ids.project }),
    defaults: { description: null, calculations: null },
    idKey: 'room',
  },
  surface: {
    listPath: (ids) => `/api/projects/${ids.project}/rooms/${ids.room}/surfaces`,
    itemPath: (ids, id) => `/api/projects/${ids.project}/rooms/${ids.room}/surfaces/${id}`,
    fromParent: (ids) => ({ room_id: ids.room }),
    defaults: { description: null, position: null },
    idKey: 'surface',
  },
  opening: {
    listPath: (ids) => `/api/projects/${ids.project}/rooms/${ids.room}/surfaces/${ids.surface}/openings`,
    itemPath: (ids, id) => `/api/projects/${ids.project}/rooms/${ids.room}/surfaces/${ids.surface}/openings/${id}`,
    fromParent: (ids) => ({ surface_id: ids.surface }),
    defaults: { name: null, quantity: 1, description: null },
    idKey: 'opening',
  },
  inspection: {
    listPath: (ids) => `/api/projects/${ids.project}/rooms/${ids.room}/inspections`,
    itemPath: (ids, id) => `/api/projects/${ids.project}/rooms/${ids.room}/inspections/${id}`,
    fromParent: (ids) => ({ room_id: ids.room }),
    // a new inspection is a draft with no answers (the screen reads them from the detail)
    defaults: { surface_id: null, plane: null, quality_target: null, notes: null, status: 'DRAFT', completed_at: null, answers: [] },
    idKey: 'inspection',
  },
  // a record the phone made carries what the owner typed; what the server derives from the other records of the object (the state of an
  // invoice, what is settled and what is left) is empty until it answers
  payment: {
    listPath: (ids) => `/api/projects/${ids.project}/payments`,
    itemPath: () => null,
    fromParent: (ids) => ({ project_id: ids.project }),
    defaults: {
      number: null, amount_net: null, vat_rate: null, due_on: null, settles_id: null, counterparty: null, document_kind: null, category: null,
      note: null, settled: null, remaining: null, state: null,
    },
    newestFirst: true,
    idKey: 'payment',
  },
  segment: {
    listPath: (ids) => `/api/projects/${ids.project}/rooms/${ids.room}/area-segments`,
    itemPath: (ids, id) => `/api/projects/${ids.project}/rooms/${ids.room}/area-segments/${id}`,
    fromParent: (ids) => ({ room_id: ids.room, surface_id: null }),
    defaults: { position: null, label: null, area: null },
    idKey: 'segment',
  },
};

const iso = (ms: number) => new Date(ms).toISOString();

type Json = Record<string, unknown>;
const isObject = (value: unknown): value is Json => typeof value === 'object' && value !== null && !Array.isArray(value);

/** The record a create makes, as the screens expect it, marked as waiting. */
function newRecord(def: EntityDef, op: OutboxOp, ids: Ids): Json {
  const { id: _clientId, ...fields } = op.body ?? {};
  return {
    ...def.defaults,
    ...def.fromParent(ids),
    ...fields,
    id: op.entityId,
    is_archived: false,
    created_at: iso(op.createdAt),
    updated_at: iso(op.createdAt),
    _pending: true,
  };
}

/**
 * What the server derives from a record's size (areas, totals). A change of the size makes the saved numbers wrong until the server
 * counts again, so they are emptied (the screens then show the typed size and, for a wall, the "~" preview) instead of showing the
 * old area beside the new size.
 */
const SIZE_FIELDS = ['width', 'height', 'length', 'quantity'];
const DERIVED_BY_SIZE: Partial<Record<Entity, readonly string[]>> = {
  room: ['calculations'],
  surface: ['gross_area', 'net_area'],
  opening: ['single_area', 'total_area', 'reveal_single_length', 'reveal_single_area', 'reveal_total_length', 'reveal_total_area'],
  segment: ['area'],
  // IA-4: an invoice's standing follows its amount and its due date (it is the server that counts it)
  payment: ['settled', 'remaining', 'state'],
};
/** The fields that make the derived ones stale; for a settlement record they are not sizes. */
const STALE_WHEN: Partial<Record<Entity, readonly string[]>> = { payment: ['amount_gross', 'due_on'] };

function changeRecord(record: Json, action: Action, op: OutboxOp): Json {
  const stamp = { updated_at: iso(op.createdAt), _pending: true };
  if (action === 'update') {
    const body = op.body ?? {};
    const derived = DERIVED_BY_SIZE[matchOp(op)?.entity as Entity] ?? [];
    const entity = matchOp(op)?.entity as Entity;
    const stale = (STALE_WHEN[entity] ?? SIZE_FIELDS).some((field) => field in body) ? Object.fromEntries(derived.map((field) => [field, null])) : {};
    return { ...record, ...body, ...stale, ...stamp };
  }
  if (action === 'archive') return { ...record, is_archived: true, ...stamp };
  if (action === 'restore') return { ...record, is_archived: false, ...stamp };
  return record;
}

function withItems(data: Json, items: unknown[]): Json {
  return { ...data, items, total: items.length };
}

function answersList(op: OutboxOp): Json {
  const answers = Array.isArray(op.body?.answers) ? (op.body?.answers as Json[]) : [];
  const items = answers.map((answer) => ({
    id: `pending-${String(answer.question_id)}`,
    value_bool: null,
    value_number: null,
    value_text: null,
    option_key: null,
    option_keys: null,
    ...answer,
    updated_at: iso(op.createdAt),
    _pending: true,
  }));
  return { items, total: items.length };
}

const EXECUTION_STATUSES = ['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED'] as const;
type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];
const isExecutionStatus = (value: unknown): value is ExecutionStatus => EXECUTION_STATUSES.includes(value as ExecutionStatus);

/** The moment of the tap: the phone's own clock, written into the change when it was made (the server believes it only when plausible). */
const tappedAt = (op: OutboxOp): string => (typeof op.body?.recorded_at === 'string' ? op.body.recorded_at : iso(op.createdAt));

/**
 * What the screen shows of a work after a status change, until the server has answered. Only the timestamps the owner has just made
 * (as the server records them); `ready_after` is derived by the server and stays empty until it answers.
 */
function movedExecution(current: Json | undefined, op: OutboxOp): Json {
  const status = op.body?.status;
  const was: ExecutionStatus = isExecutionStatus(current?.status) ? current.status : 'NOT_STARTED';
  const at = tappedAt(op);
  let startedAt = (current?.started_at as string | null | undefined) ?? null;
  let completedAt = (current?.completed_at as string | null | undefined) ?? null;
  if (status === 'IN_PROGRESS') {
    if (was === 'NOT_STARTED') startedAt = at;
    else completedAt = null; // reopened
  } else if (status === 'COMPLETED') {
    if (was === 'NOT_STARTED') startedAt = at;
    completedAt = at;
  } else if (status === 'NOT_STARTED') {
    startedAt = null;
  }
  return { status: isExecutionStatus(status) ? status : was, started_at: startedAt, completed_at: completedAt, ready_after: null };
}

/** A work plan with the status change laid over the work it is about. */
function overlayExecution(op: OutboxOp, ids: Ids, base: string, data: Json): Json {
  if (base !== `/api/projects/${ids.project}/rooms/${ids.room}/surfaces/${ids.surface}/work-plan` || !Array.isArray(data.planned_works)) return data;
  return {
    ...data,
    planned_works: (data.planned_works as unknown[]).map((work) =>
      isObject(work) && work.occurrence_key === ids.occurrence
        ? { ...work, execution: { ...movedExecution(isObject(work.execution) ? work.execution : undefined, op), _pending: true } }
        : work,
    ),
  };
}

/**
 * What a waiting "restore" needs to put a record back into a list that hides archived records: the records themselves (taken out of
 * the list by an "archive" laid over it, or archived on the server and known from the saved list that shows them) and the order
 * of the whole list, so that a record returns to the place it has in the server's order.
 */
export interface ArchivedPool {
  records: Map<string, Json>;
  order: string[];
}

/** The pool from a saved list that shows archived records (`?include_archived=true`). */
export function archivedPoolFrom(data: unknown): ArchivedPool {
  const pool: ArchivedPool = { records: new Map(), order: [] };
  if (!isObject(data) || !Array.isArray(data.items)) return pool;
  for (const item of data.items as unknown[]) {
    if (!isObject(item) || typeof item.id !== 'string') continue;
    pool.order.push(item.id);
    if (item.is_archived === true) pool.records.set(item.id, item);
  }
  return pool;
}

const idsOf = (items: unknown[]): string[] => items.flatMap((item) => (isObject(item) && typeof item.id === 'string' ? [item.id] : []));

/** Puts a record back after the nearest of the records that precede it in the full order which is in the list (at the start when none is). */
function insertBack(items: unknown[], record: Json, id: string, order: string[]): unknown[] {
  const preceding = order.slice(0, Math.max(0, order.indexOf(id))).reverse();
  for (const before of preceding) {
    const at = items.findIndex((item) => isObject(item) && item.id === before);
    if (at >= 0) return [...items.slice(0, at + 1), record, ...items.slice(at + 1)];
  }
  return [record, ...items];
}

/** One waiting change laid over what a GET returned (or would return). Pure; a path it is not about is returned as it came. */
function applyOp(op: OutboxOp, path: string, data: unknown, pool: ArchivedPool): unknown {
  const match = matchOp(op);
  if (!match || !isObject(data)) return data;
  const [base, query = ''] = path.split('?');
  const includeArchived = /(^|&)include_archived=true(&|$)/.test(query);

  if (match.entity === 'answers') {
    const inspectionPath = `/api/projects/${match.ids.project}/rooms/${match.ids.room}/inspections/${match.ids.inspection}`;
    if (base === `${inspectionPath}/answers`) return answersList(op);
    // the inspection itself carries its answers (the screen seeds the form from it)
    if (base === inspectionPath && data.id === match.ids.inspection) return { ...data, answers: answersList(op).items };
    return data;
  }
  if (match.entity === 'execution') return overlayExecution(op, match.ids, base, data);

  const def = ENTITIES[match.entity];
  const id = match.action === 'create' ? op.entityId : match.ids[def.idKey];
  if (!id) return data;

  if (base === def.listPath(match.ids) && Array.isArray(data.items)) {
    const items = data.items as unknown[];
    const same = (item: unknown) => isObject(item) && item.id === id;
    // the order of the whole list: the saved list that shows archived records when there is one, then what this list shows
    for (const known of idsOf(items)) if (!pool.order.includes(known)) pool.order.push(known);
    switch (match.action) {
      case 'create':
        if (items.some(same)) return data;
        if (!pool.order.includes(id)) pool.order.push(id);
        return withItems(data, def.newestFirst ? [newRecord(def, op, match.ids), ...items] : [...items, newRecord(def, op, match.ids)]);
      case 'update': {
        // a record taken out of the list (archived) is changed there too, so that a later restore brings it back as it was left
        const away = pool.records.get(id);
        if (away && !items.some(same)) pool.records.set(id, changeRecord(away, 'update', op));
        return withItems(data, items.map((item) => (same(item) ? changeRecord(item as Json, match.action, op) : item)));
      }
      case 'restore': {
        if (items.some(same)) return withItems(data, items.map((item) => (same(item) ? changeRecord(item as Json, match.action, op) : item)));
        // a list that hides archived records does not carry it: it comes back from where it was taken out (or from the saved archived list)
        const archived = includeArchived ? undefined : pool.records.get(id);
        if (!archived) return data;
        pool.records.delete(id);
        return withItems(data, insertBack(items, changeRecord(archived, 'restore', op), id, pool.order));
      }
      case 'archive': {
        if (includeArchived) return withItems(data, items.map((item) => (same(item) ? changeRecord(item as Json, 'archive', op) : item)));
        const at = items.findIndex(same);
        if (at >= 0) pool.records.set(id, changeRecord(items[at] as Json, 'archive', op));
        return withItems(data, items.filter((item) => !same(item)));
      }
      case 'delete':
        return withItems(data, items.filter((item) => !same(item)));
      default:
        return data;
    }
  }

  const item = def.itemPath(match.ids, id);
  if (item !== null && base === item && data.id === id && match.action !== 'create' && match.action !== 'delete') {
    return changeRecord(data, match.action, op);
  }
  return data;
}

/** A GET answer with every waiting change of the owner laid over it, in the order the changes were made. */
export function overlayRead(path: string, data: unknown, ops: readonly OutboxOp[], archived?: ArchivedPool): unknown {
  const pool: ArchivedPool = { records: new Map(archived?.records), order: [...(archived?.order ?? [])] };
  let result = data;
  for (const op of ops) if (op.status === 'pending') result = applyOp(op, path, result, pool);
  return result;
}

const LISTS_UNDER_ROOM = /^\/api\/projects\/[^/]+\/rooms\/(?<room>[^/?]+)\/(?:surfaces|area-segments|inspections)(?:\?.*)?$/i;
const UNDER_INSPECTION = /^\/api\/projects\/[^/]+\/rooms\/[^/]+\/inspections\/(?<inspection>[^/?]+)\/(?:answers|findings)(?:\?.*)?$/i;
const OPENINGS_UNDER_SURFACE = /^\/api\/projects\/[^/]+\/rooms\/[^/]+\/surfaces\/(?<surface>[^/?]+)\/openings(?:\?.*)?$/i;

/**
 * What a GET should return when the server cannot be asked and no saved copy exists, but the phone itself made the record (or its
 * parent) a moment ago: the record from the waiting changes. `undefined` when the phone knows nothing about that path.
 */
export function resolveFromOutbox(path: string, ops: readonly OutboxOp[]): unknown | undefined {
  const pending = ops.filter((op) => op.status === 'pending');
  const [base] = path.split('?');
  for (const op of pending) {
    const match = matchOp(op);
    if (!match || match.action !== 'create' || match.entity === 'answers' || match.entity === 'execution' || !op.entityId) continue;
    const def = ENTITIES[match.entity];
    if (def.itemPath(match.ids, op.entityId) === base) return overlayRead(path, newRecord(def, op, match.ids), pending);
  }
  const createdRoom = (id: string) => pending.some((op) => op.kind === 'room.create' && op.entityId === id);
  const createdSurface = (id: string) => pending.some((op) => op.kind === 'surface.create' && op.entityId === id);
  const underRoom = LISTS_UNDER_ROOM.exec(path)?.groups?.room;
  const underSurface = OPENINGS_UNDER_SURFACE.exec(path)?.groups?.surface;
  const underInspection = UNDER_INSPECTION.exec(path)?.groups?.inspection;
  const createdInspection = (id: string) => pending.some((op) => op.kind === 'inspection.create' && op.entityId === id);
  if ((underRoom && createdRoom(underRoom)) || (underSurface && createdSurface(underSurface)) || (underInspection && createdInspection(underInspection))) {
    return overlayRead(path, { items: [], total: 0 }, pending);
  }
  return undefined;
}

/** What the waiting change gives back to the screen that made it (the answer the server would have sent, in the shape it sends). */
export function optimisticResult(op: OutboxOp, saved: ReadonlyArray<{ path: string; data: unknown }>, ops: readonly OutboxOp[]): unknown {
  const match = matchOp(op);
  if (!match) return undefined;
  if (match.action === 'delete') return undefined;
  if (match.entity === 'answers') return answersList(op);
  if (match.entity === 'execution') return optimisticExecution(op, match.ids, saved, ops);
  const def = ENTITIES[match.entity];
  if (match.action === 'create') return newRecord(def, op, match.ids);
  const id = match.ids[def.idKey] as string;
  const asked = def.itemPath(match.ids, id) ?? def.listPath(match.ids);
  for (const candidate of [...saved, ...(resolveFromOutbox(asked, ops) !== undefined ? [{ path: asked, data: resolveFromOutbox(asked, ops) }] : [])]) {
    const laid = overlayRead(candidate.path, candidate.data, ops);
    if (isObject(laid) && laid.id === id) return laid;
    if (isObject(laid) && Array.isArray(laid.items)) {
      const found = (laid.items as unknown[]).find((item) => isObject(item) && item.id === id);
      if (found) return found;
    }
  }
  return changeRecord({ id }, match.action, op);
}

/**
 * The answer a status change gives the screen that made it (the shape of `SurfaceWorkExecutionRead`): the work as the plan shows it,
 * with the status changes made before this one already laid over it, then this change.
 */
function optimisticExecution(op: OutboxOp, ids: Ids, saved: ReadonlyArray<{ path: string; data: unknown }>, ops: readonly OutboxOp[]): unknown {
  const planPath = `/api/projects/${ids.project}/rooms/${ids.room}/surfaces/${ids.surface}/work-plan`;
  const before = ops.filter((candidate) => candidate.seq === undefined || op.seq === undefined || candidate.seq < op.seq);
  let current: Json | undefined;
  for (const candidate of saved) {
    if (candidate.path.split('?')[0] !== planPath) continue; // the plan is read with `?missing=null` (owner 2026-10-31)
    const laid = overlayRead(candidate.path, candidate.data, before);
    const work = isObject(laid) && Array.isArray(laid.planned_works) ? (laid.planned_works as unknown[]).find((w) => isObject(w) && w.occurrence_key === ids.occurrence) : undefined;
    if (isObject(work) && isObject(work.execution)) current = work.execution;
  }
  return { occurrence_key: ids.occurrence, ...movedExecution(current, op), _pending: true };
}

export function labelOf(match: WriteMatch, body: Record<string, unknown> | null): string {
  const text = (value: unknown) => (typeof value === 'string' ? value.trim().slice(0, 40) : '');
  switch (match.entity) {
    case 'note':
      return text(body?.body);
    case 'room':
    case 'surface':
      return text(body?.name);
    case 'opening':
      return [text(body?.name) || String(body?.opening_type ?? ''), body?.width && body?.height ? `${body.width} × ${body.height}` : ''].filter(Boolean).join(' ');
    case 'segment':
      return [String(body?.plane ?? ''), body?.width && body?.height ? `${body.width} × ${body.height}` : ''].filter(Boolean).join(' ');
    case 'inspection':
      return [String(body?.plane ?? ''), String(body?.substrate ?? '')].filter(Boolean).join(' ');
    case 'execution':
      return String(body?.status ?? '');
    case 'payment':
      return text(body?.title);
    default:
      return '';
  }
}

/** The saved copies a change is about: the list of its kind of record (and the records under it). */
export function cachePrefix(match: WriteMatch): string {
  if (match.entity === 'answers') return `/api/projects/${match.ids.project}/rooms/${match.ids.room}/inspections/${match.ids.inspection}/answers`;
  if (match.entity === 'execution') return `/api/projects/${match.ids.project}/rooms/${match.ids.room}/surfaces/${match.ids.surface}/work-plan`;
  return ENTITIES[match.entity].listPath(match.ids);
}
