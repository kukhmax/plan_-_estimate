import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { archivePayment, createPayment, fetchPayments, restorePayment, saveAgreedAmount, updatePayment } from '../api/payments';
import type { PaymentFields } from '../types/payment';
import { freshIndexedDb } from '../test/fakeIdb';
import { reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { listOps } from './outbox';
import { getOutboxCounts, resetSyncStateForTests } from './outboxState';
import { setOfflineOwner } from './readCache';
import { drainOutbox } from './sync';

// IA-4: the whole way of a settlement record made without a signal.

const P = '11111111-1111-4111-8111-111111111111';
const ID1 = '00000000-0000-4000-8000-000000000001';
const ID2 = '00000000-0000-4000-8000-000000000002';
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

const fields = (over: Partial<PaymentFields> = {}): PaymentFields => ({
  title: 'Farba', amount_gross: '89.99', occurred_on: '2026-10-17', number: null, amount_net: null, vat_rate: null, due_on: null, settles_id: null,
  counterparty: 'Castorama', document_kind: 'RECEIPT', note: null, ...over,
});

/** A small server: it keeps the records by id (a second create of the same id answers with the one it has), as the real one does. */
function serverStub() {
  const rows = new Map<string, Record<string, unknown>>();
  const received: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
  const state = { up: true, lose: 0 };
  const base = `/api/projects/${P}/payments`;
  const handler = vi.fn(async (url: string, init?: RequestInit) => {
    if (!state.up) throw new TypeError('Failed to fetch');
    const path = String(url);
    const method = init?.method ?? 'GET';
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    if (method !== 'GET') received.push({ method, path, body });
    let answer: Response;
    if (method === 'POST' && path === base) {
      if (!rows.has(String(body?.id))) rows.set(String(body?.id), { ...body, project_id: P, is_archived: false, settled: null, remaining: null, state: null });
      answer = json(rows.get(String(body?.id)), 201);
    } else if (method === 'PATCH' && path.startsWith(`${base}/`)) {
      const id = path.slice(base.length + 1);
      rows.set(id, { ...rows.get(id), ...body });
      answer = json(rows.get(id));
    } else if (method === 'POST' && /\/(archive|restore)$/.test(path)) {
      const [id, what] = path.slice(base.length + 1).split('/');
      rows.set(id, { ...rows.get(id), is_archived: what === 'archive' });
      answer = json(rows.get(id));
    } else if (method === 'GET' && path.startsWith(base)) {
      const all = path.includes('include_archived=true');
      const items = [...rows.values()].filter((row) => all || !row.is_archived);
      answer = json({ items, total: items.length, summary: { invoiced: '0.00' }, agreed_amount: null });
    } else {
      answer = json({}, method === 'POST' ? 201 : 200);
    }
    if (method !== 'GET' && state.lose > 0) {
      state.lose -= 1;
      throw new TypeError('Failed to fetch'); // the server did it, the phone never heard
    }
    return answer;
  });
  return { handler, rows, received, state };
}

describe('the whole way of a settlement record made without a signal (IA-4)', () => {
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

  it('a record made, changed and archived in a basement reaches the server in order, once, with the id the phone gave it', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    await fetchPayments(P); // in the car: the list is read and kept
    await fetchPayments(P, true);
    server.state.up = false;
    reportNetworkFailure();

    const made = await createPayment(P, ID1, 'EXPENSE', fields());
    expect(made).toMatchObject({ id: ID1, title: 'Farba', _pending: true, state: null, settled: null });
    await updatePayment(P, ID1, fields({ title: 'Farba biała', amount_gross: '120.50' }));
    const second = await createPayment(P, ID2, 'ADVANCE', fields({ title: 'Zaliczka', counterparty: null, document_kind: null }));
    await archivePayment(P, ID2);

    // what the owner sees meanwhile
    const shown = await fetchPayments(P);
    expect(shown.items.map((item) => item.id)).toEqual([ID1]);
    expect(shown.items[0]).toMatchObject({ title: 'Farba biała', amount_gross: '120.50', _pending: true });
    expect((await fetchPayments(P, true)).items.map((item) => [item.id, item.is_archived])).toEqual([[ID2, true], [ID1, false]]);
    expect(second.id).toBe(ID2);
    expect(server.received).toEqual([]); // nothing reached the server
    expect(getOutboxCounts().pending).toBe(4);
    // every waiting change knows the record it is about (the sync screen and the order of sending rely on it)
    expect((await listOps()).map((o) => [o.kind, o.entityId])).toEqual([
      ['payment.create', ID1], ['payment.update', ID1], ['payment.create', ID2], ['payment.archive', ID2],
    ]);

    server.state.up = true;
    reportNetworkSuccess();
    expect(await drainOutbox()).toEqual({ sent: 4, refused: 0, stoppedBy: null });

    expect(server.received.map((r) => `${r.method} ${r.path.replace(`/api/projects/${P}`, '')}`)).toEqual([
      'POST /payments',
      `PATCH /payments/${ID1}`,
      'POST /payments',
      `POST /payments/${ID2}/archive`,
    ]);
    expect(server.received[0].body).toMatchObject({ id: ID1, kind: 'EXPENSE', title: 'Farba' });
    expect(server.received[2].body).toMatchObject({ id: ID2, kind: 'ADVANCE' });
    expect(await listOps()).toEqual([]);
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 0 });
    expect(server.rows.get(ID1)).toMatchObject({ title: 'Farba biała', amount_gross: '120.50' });
    expect(server.rows.get(ID2)).toMatchObject({ is_archived: true });
  });

  it('a lost answer: the same create is sent again with the same id and the server keeps one record', async () => {
    const server = serverStub();
    server.state.lose = 1;
    vi.stubGlobal('fetch', server.handler);
    const made = await createPayment(P, ID1, 'EXPENSE', fields()); // the answer is lost -> kept, shown as waiting
    expect(made).toMatchObject({ id: ID1, _pending: true });
    expect(server.rows.size).toBe(1); // the server has it already

    reportNetworkSuccess();
    await drainOutbox(); // the repeat
    expect(server.rows.size).toBe(1);
    expect(server.received.map((r) => r.body?.id)).toEqual([ID1, ID1]);
    expect(getOutboxCounts().pending).toBe(0);
  });

  it('while older changes wait, a new record goes behind them even with a signal (the order is kept)', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    await fetchPayments(P);
    server.state.up = false;
    reportNetworkFailure();
    await createPayment(P, ID1, 'EXPENSE', fields());
    server.state.up = true; // the signal is back, but the drain has not run yet
    await createPayment(P, ID2, 'EXPENSE', fields({ title: 'Grunt' }));
    expect(server.received).toEqual([]);
    expect((await listOps()).map((o) => o.entityId)).toEqual([ID1, ID2]);
    reportNetworkSuccess();
    await drainOutbox();
    expect(server.received.map((r) => r.body?.id)).toEqual([ID1, ID2]);
  });

  it('a record the server refuses is handed to the owner with the words of the sync screen, and the rest goes on', async () => {
    const server = serverStub();
    const inner = server.handler;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && String(url).endsWith('/payments') && JSON.parse(String(init.body)).id === ID1) {
        return json({ detail: { code: 'PAYMENT_INVALID', message: 'only an invoice has a due date' } }, 422);
      }
      return inner(url, init);
    }));
    await fetchPayments(P);
    server.state.up = false;
    reportNetworkFailure();
    await createPayment(P, ID1, 'EXPENSE', fields());
    await createPayment(P, ID2, 'EXPENSE', fields({ title: 'Grunt' }));
    server.state.up = true;
    reportNetworkSuccess();
    expect(await drainOutbox()).toEqual({ sent: 1, refused: 1, stoppedBy: null });
    const left = await listOps();
    expect(left).toHaveLength(1);
    expect(left[0]).toMatchObject({ kind: 'payment.create', entityId: ID1, status: 'failed', error: { status: 422, code: 'PAYMENT_INVALID' } });
    expect(server.rows.has(ID2)).toBe(true);
  });

  it('an online write goes straight to the server and nothing is kept', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    await createPayment(P, ID1, 'EXPENSE', fields());
    expect(server.received).toHaveLength(1);
    expect(await listOps()).toEqual([]);
  });

  it('the agreed amount is not kept: it needs the server', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    server.state.up = false;
    reportNetworkFailure();
    await expect(saveAgreedAmount(P, '40000.00')).rejects.toBeTruthy();
    expect(await listOps()).toEqual([]);
  });

  it('a restore of a record archived on the server brings it back into the list that hides archived ones', async () => {
    const server = serverStub();
    vi.stubGlobal('fetch', server.handler);
    server.rows.set(ID1, { id: ID1, project_id: P, title: 'Stara', kind: 'EXPENSE', is_archived: true });
    server.rows.set(ID2, { id: ID2, project_id: P, title: 'Żywa', kind: 'EXPENSE', is_archived: false });
    await fetchPayments(P);
    await fetchPayments(P, true);
    server.state.up = false;
    reportNetworkFailure();
    await restorePayment(P, ID1);
    expect((await fetchPayments(P)).items.map((item) => item.id).sort()).toEqual([ID1, ID2].sort());
  });
});
