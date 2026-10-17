import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { archivePayment, createPayment, fetchPayments, restorePayment, updatePayment } from '../api/payments';
import type { PaymentFields } from '../types/payment';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { listOps } from './outbox';
import { getOutboxCounts, resetSyncStateForTests } from './outboxState';
import { setOfflineOwner } from './readCache';
import { drainOutbox } from './sync';

// IA-4, in the manner of Stage 19F: random histories of settlement records made without a signal. Two questions:
//  1. what the phone SHOWS (saved copies + waiting changes) is what the server will hold after the sending;
//  2. whatever goes wrong on the way (a dropped request, a lost answer, a server error), the server ends up with exactly the changes made, none twice.
// The order of the list is the server's to decide (by date), so the records are compared as sets.

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

interface Rec { id: string; title: string; amount: string; archived: boolean }
type World = Rec[];
const clone = (w: World): World => JSON.parse(JSON.stringify(w));
const row = (r: Rec) => ({ id: r.id, project_id: P, kind: 'EXPENSE', title: r.title, amount_gross: r.amount, is_archived: r.archived, settled: null, remaining: null, state: null });

function makeServer(world: World, chaos: () => 'ok' | 'drop' | 'lost' | 'error') {
  const state = { up: true };
  const base = `/api/projects/${P}/payments`;
  const handle = (method: string, url: string, body: Record<string, unknown> | null): Response => {
    const [path, query = ''] = url.split('?');
    const all = /include_archived=true/.test(query);
    let m: RegExpExecArray | null;
    if (method === 'GET' && path === base) {
      const items = world.filter((r) => all || !r.archived);
      return json({ items: items.map(row), total: items.length, summary: {}, agreed_amount: null });
    }
    if (method === 'POST' && path === base) {
      const id = body!.id as string;
      if (!world.some((r) => r.id === id)) world.push({ id, title: body!.title as string, amount: body!.amount_gross as string, archived: false });
      return json(row(world.find((r) => r.id === id)!), 201);
    }
    if ((m = new RegExp(`^${base}/([^/]+)(?:/(archive|restore))?$`).exec(path))) {
      const r = world.find((x) => x.id === m![1]);
      if (!r) return json({ detail: 'Payment not found' }, 404);
      if (method === 'PATCH') { r.title = body!.title as string; r.amount = body!.amount_gross as string; }
      if (m[2] === 'archive') r.archived = true;
      if (m[2] === 'restore') r.archived = false;
      return json(row(r));
    }
    return json({ detail: 'not found' }, 404);
  };
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    const fate = method === 'GET' ? 'ok' : chaos();
    if (fate === 'drop') throw new TypeError('Failed to fetch');
    if (fate === 'error') return json({ detail: 'boom' }, 503);
    const answer = handle(method, String(url), body);
    if (fate === 'lost') throw new TypeError('Failed to fetch'); // the server did it, the phone never heard
    return answer;
  });
  return { handler, state };
}

const fields = (title: string, amount: string): PaymentFields => ({
  title, amount_gross: amount, occurred_on: '2026-10-17', number: null, amount_net: null, vat_rate: null, due_on: null, settles_id: null,
  counterparty: null, document_kind: null, category: null, note: null,
});
const key = (id: string, title: string, amount: string, archived: boolean) => `${id}|${title}|${Number(amount).toFixed(2)}|${archived ? 'A' : '-'}`;
const norm = (rs: World, archivedToo: boolean) => rs.filter((r) => archivedToo || !r.archived).map((r) => key(r.id, r.title, r.amount, r.archived)).sort();
const fromList = (items: Array<{ id: string; title: string; amount_gross: string; is_archived: boolean }>) =>
  items.map((r) => key(r.id, r.title, r.amount_gross, r.is_archived)).sort();

async function phoneSees(world: World) {
  expect(fromList((await fetchPayments(P)).items), 'payments').toEqual(norm(world, false));
  expect(fromList((await fetchPayments(P, true)).items), 'payments (with archived)').toEqual(norm(world, true));
}

let counter = 0;
const newId = () => `00000000-0000-4000-8000-${String(++counter).padStart(12, '0')}`;

async function randomChange(world: World, rnd: () => number, n: number) {
  const pick = <T,>(xs: T[]): T | undefined => xs[Math.floor(rnd() * xs.length)];
  const amount = () => `${1 + Math.floor(rnd() * 900)}.${String(Math.floor(rnd() * 100)).padStart(2, '0')}`;
  const choices: Array<() => Promise<void>> = [];
  choices.push(async () => { const id = newId(); const a = amount(); await createPayment(P, id, 'EXPENSE', fields(`p${n}`, a)); world.push({ id, title: `p${n}`, amount: a, archived: false }); });
  const active = world.filter((r) => !r.archived);
  const archived = world.filter((r) => r.archived);
  if (world.length) choices.push(async () => { const x = pick(world)!; const a = amount(); await updatePayment(P, x.id, fields(`u${n}`, a)); x.title = `u${n}`; x.amount = a; });
  if (active.length) choices.push(async () => { const x = pick(active)!; await archivePayment(P, x.id); x.archived = true; });
  if (archived.length) choices.push(async () => { const x = pick(archived)!; await restorePayment(P, x.id); x.archived = false; });
  await pick(choices)!();
}

async function startFromSavedCopies() {
  await fetchPayments(P);
  await fetchPayments(P, true);
}

const SEEDS = Array.from({ length: 100 }, (_, i) => 2000 + i * 7919);
const start = (): World => [
  { id: '00000000-0000-4000-8000-0000000000b2', title: 'old two', amount: '20.00', archived: false },
  { id: '00000000-0000-4000-8000-0000000000b1', title: 'old one', amount: '10.00', archived: true },
];

describe.each([
  ['what the phone shows without a signal is what the server will hold afterwards', 'show'],
  ['whatever goes wrong on the way, the server gets the changes once', 'chaos'],
] as const)('settlement records: %s (IA-4)', (_name, mode) => {
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

  it.each(mode === 'show' ? SEEDS : SEEDS.slice(0, 60))('seed %i', async (seed) => {
    const rnd = prng(seed);
    const server = start();
    const chaos = mode === 'show' ? () => 'ok' as const : () => { const x = rnd(); return x < 0.2 ? 'drop' : x < 0.4 ? 'lost' : x < 0.5 ? 'error' : 'ok'; };
    const stub = makeServer(server, chaos);
    vi.stubGlobal('fetch', stub.handler);
    await startFromSavedCopies();
    const world = clone(server);

    stub.state.up = false;
    reportNetworkFailure();
    const steps = 8 + Math.floor(rnd() * 10);
    for (let n = 1; n <= steps; n += 1) {
      await randomChange(world, rnd, n);
      if (mode === 'show') {
        try {
          await phoneSees(world); // after EVERY change the phone shows exactly what the owner made
        } catch (error) {
          const waiting = (await listOps()).map((o) => `${o.kind}(${String(o.entityId ?? '').slice(-4)})`);
          throw new Error(`${(error as Error).message}\n  made so far: ${waiting.join(', ')}`);
        }
      }
    }
    const made = (await listOps()).length;

    stub.state.up = true;
    reportNetworkSuccess();
    let rounds = 0;
    while (getOutboxCounts().pending > 0 && rounds < 60) {
      await drainOutbox();
      reportNetworkSuccess();
      rounds += 1;
    }
    expect(getOutboxCounts(), `after ${rounds} tries`).toEqual({ pending: 0, failed: 0 });
    expect(norm(server, true), 'the server holds exactly what the owner made').toEqual(norm(world, true));
    expect(server.length, 'none twice').toBe(world.length);
    expect(made).toBeGreaterThan(0);
    if (mode === 'show') await phoneSees(world);
  }, 60_000);
});
