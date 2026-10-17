import { describe, expect, it } from 'vitest';
import type { OutboxKind, OutboxOp } from './opTypes';
import { archivedPoolFrom, labelOf, matchWrite, optimisticResult, overlayRead } from './writeRules';

// IA-4: the settlement records of an object (invoices, money from the client, expenses on materials) made without a signal.

const P = '11111111-1111-4111-8111-111111111111';
const A = '00000000-0000-4000-8000-00000000000a';
const B = '00000000-0000-4000-8000-00000000000b';
const C = '00000000-0000-4000-8000-00000000000c';
const NEW = '99999999-9999-4999-8999-999999999999';
const paymentsPath = `/api/projects/${P}/payments`;

const T0 = Date.UTC(2026, 9, 17, 12, 0, 0);
let seq = 0;
function op(kind: OutboxKind, method: OutboxOp['method'], path: string, body: Record<string, unknown> | null, entityId: string | null, extra: Partial<OutboxOp> = {}): OutboxOp {
  return { seq: ++seq, ownerId: 'o', createdAt: T0 + seq * 1000, method, path, body, kind, entityId, label: '', status: 'pending', attempts: 0, ...extra };
}
const create = (id: string, body: Record<string, unknown> = {}) =>
  op('payment.create', 'POST', paymentsPath, { id, kind: 'EXPENSE', title: 'Farba', amount_gross: '89.99', occurred_on: '2026-10-17', ...body }, id);
const update = (id: string, body: Record<string, unknown>) => op('payment.update', 'PATCH', `${paymentsPath}/${id}`, body, id);
const archive = (id: string) => op('payment.archive', 'POST', `${paymentsPath}/${id}/archive`, null, id);
const restore = (id: string) => op('payment.restore', 'POST', `${paymentsPath}/${id}/restore`, null, id);

const record = (id: string, over: Record<string, unknown> = {}) => ({
  id, project_id: P, kind: 'INVOICE', title: 'Faktura', number: null, amount_gross: '1000.00', amount_net: null, vat_rate: null,
  occurred_on: '2026-10-01', due_on: '2026-10-15', settles_id: null, counterparty: null, document_kind: null, note: null, is_archived: false,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', settled: '400.00', remaining: '600.00', state: 'PARTIAL', ...over,
});
const list = (...items: unknown[]) => ({ items, total: items.length, summary: { invoiced: '1000.00' }, agreed_amount: '40000.00' });
const ids = (data: unknown) => (data as { items: Array<{ id: string }> }).items.map((item) => item.id);
const items = (data: unknown) => (data as { items: Array<Record<string, unknown>> }).items;

describe('the writes of a settlement record are kept on the phone', () => {
  it.each([
    ['POST', paymentsPath, 'payment.create'],
    ['PATCH', `${paymentsPath}/${A}`, 'payment.update'],
    ['POST', `${paymentsPath}/${A}/archive`, 'payment.archive'],
    ['POST', `${paymentsPath}/${A}/restore`, 'payment.restore'],
  ])('%s %s is %s', (method, path, kind) => {
    expect(matchWrite(method, path)?.kind).toBe(kind);
    expect(matchWrite(method, path)?.entity).toBe('payment');
  });

  it('reads the project and the record out of the path', () => {
    expect(matchWrite('PATCH', `${paymentsPath}/${A}`)?.ids).toEqual({ project: P, payment: A });
  });

  it.each([
    ['PUT', `/api/projects/${P}/finance`], // the agreed amount: with a signal only
    ['GET', paymentsPath],
    ['DELETE', `${paymentsPath}/${A}`], // a record is never erased
    ['PATCH', `${paymentsPath}/not-a-uuid`],
    ['POST', `${paymentsPath}/${A}/settle`],
    ['POST', `/api/projects/${P}/payments/export`],
  ])('%s %s needs the server', (method, path) => {
    expect(matchWrite(method, path)).toBeNull();
  });
});

describe('a record made on the phone, laid over the list the server gave', () => {
  it('goes first, marked as waiting, with what was typed and nothing the server derives', () => {
    const shown = overlayRead(paymentsPath, list(record(A)), [create(NEW)]);
    expect(ids(shown)).toEqual([NEW, A]);
    expect((shown as { total: number }).total).toBe(2);
    expect(items(shown)[0]).toMatchObject({
      id: NEW, project_id: P, kind: 'EXPENSE', title: 'Farba', amount_gross: '89.99', is_archived: false, _pending: true,
      settled: null, remaining: null, state: null, number: null, due_on: null, settles_id: null, note: null,
    });
  });

  it('leaves the summary and the agreed amount as the server said (nothing is counted on the phone)', () => {
    const shown = overlayRead(paymentsPath, list(record(A)), [create(NEW, { amount_gross: '500.00' })]) as Record<string, unknown>;
    expect(shown.summary).toEqual({ invoiced: '1000.00' });
    expect(shown.agreed_amount).toBe('40000.00');
  });

  it('is laid over once even when the server already has it (sent, but not yet removed)', () => {
    expect(ids(overlayRead(paymentsPath, list(record(NEW)), [create(NEW)]))).toEqual([NEW]);
  });

  it('is laid over the list that shows archived records as well', () => {
    expect(ids(overlayRead(`${paymentsPath}?include_archived=true`, list(record(A, { is_archived: true })), [create(NEW)]))).toEqual([NEW, A]);
  });

  it('is not laid over the payments of another object', () => {
    const other = '22222222-2222-4222-8222-222222222222';
    expect(ids(overlayRead(`/api/projects/${other}/payments`, list(record(A)), [create(NEW)]))).toEqual([A]);
  });

  it('a refused one is not laid over', () => {
    expect(ids(overlayRead(paymentsPath, list(record(A)), [{ ...create(NEW), status: 'failed' }]))).toEqual([A]);
  });
});

describe('a change of a record', () => {
  it('lays the typed fields over the record and marks it', () => {
    const shown = overlayRead(paymentsPath, list(record(A)), [update(A, { title: 'Faktura końcowa', note: 'do 14 dni' })]);
    expect(items(shown)[0]).toMatchObject({ id: A, title: 'Faktura końcowa', note: 'do 14 dni', _pending: true });
  });

  it('keeps what the server derived when neither the amount nor the due date changed', () => {
    const shown = overlayRead(paymentsPath, list(record(A)), [update(A, { title: 'Inna nazwa' })]);
    expect(items(shown)[0]).toMatchObject({ settled: '400.00', remaining: '600.00', state: 'PARTIAL' });
  });

  it.each([['amount_gross', '1200.00'], ['due_on', '2026-11-01']])('empties the standing of an invoice when %s changes (the server counts it again)', (field, value) => {
    const shown = overlayRead(paymentsPath, list(record(A)), [update(A, { [field]: value })]);
    expect(items(shown)[0]).toMatchObject({ [field]: value, settled: null, remaining: null, state: null, _pending: true });
  });

  it('a record made on the phone is changed in place, in the order of the changes', () => {
    const shown = overlayRead(paymentsPath, list(), [create(NEW), update(NEW, { title: 'Farba biała', amount_gross: '120.00' })]);
    expect(items(shown)).toHaveLength(1);
    expect(items(shown)[0]).toMatchObject({ id: NEW, title: 'Farba biała', amount_gross: '120.00', _pending: true });
  });

  it('a change of another record leaves this one alone', () => {
    expect(items(overlayRead(paymentsPath, list(record(A), record(B)), [update(B, { title: 'X' })]))[0]).toMatchObject({ id: A, title: 'Faktura' });
  });
});

describe('archive and restore of a record', () => {
  it('archiving takes the record out of the list that hides archived ones, and marks it in the list that shows them', () => {
    expect(ids(overlayRead(paymentsPath, list(record(A), record(B)), [archive(A)]))).toEqual([B]);
    const shown = overlayRead(`${paymentsPath}?include_archived=true`, list(record(A), record(B)), [archive(A)]);
    expect(items(shown)[0]).toMatchObject({ id: A, is_archived: true, _pending: true });
  });

  it('a record archived on the server comes back into its own place from the saved list that shows archived', () => {
    const active = list(record(A), record(C));
    const withArchived = list(record(A), record(B, { is_archived: true }), record(C));
    const shown = overlayRead(paymentsPath, active, [restore(B)], archivedPoolFrom(withArchived));
    expect(ids(shown)).toEqual([A, B, C]);
    expect(items(shown)[1]).toMatchObject({ id: B, is_archived: false, _pending: true });
  });

  it('a record made, archived and restored on the phone is in the list again', () => {
    // its place is the server's to decide once it is sent (by date); until then it is simply there
    expect(ids(overlayRead(paymentsPath, list(record(A)), [create(NEW), archive(NEW), restore(NEW)])).sort()).toEqual([A, NEW].sort());
    expect(ids(overlayRead(paymentsPath, list(record(A)), [create(NEW), archive(NEW)]))).toEqual([A]);
  });
});

describe('what the screen that made the change gets back', () => {
  it('a create gives the record with the id of the phone', () => {
    const made = create(NEW);
    expect(optimisticResult(made, [], [made])).toMatchObject({ id: NEW, title: 'Farba', _pending: true, state: null });
  });

  it('a change gives the saved record with the change laid over it', () => {
    const changed = update(A, { title: 'Nowy tytuł' });
    expect(optimisticResult(changed, [{ path: paymentsPath, data: list(record(A)) }], [changed])).toMatchObject({ id: A, title: 'Nowy tytuł', _pending: true });
  });

  it('archiving gives the record marked archived', () => {
    const archived = archive(A);
    expect(optimisticResult(archived, [{ path: paymentsPath, data: list(record(A)) }], [archived])).toMatchObject({ id: A, is_archived: true });
  });

  it('a change of a record that is only on the phone gives that record', () => {
    const made = create(NEW);
    const changed = update(NEW, { note: 'x' });
    expect(optimisticResult(changed, [], [made, changed])).toMatchObject({ id: NEW, note: 'x' });
  });
});

describe('the words of a waiting record', () => {
  it('names a create by its title and cuts a long one', () => {
    const match = matchWrite('POST', paymentsPath)!;
    expect(labelOf(match, { title: '  Farba  ' })).toBe('Farba');
    expect(labelOf(match, { title: 'x'.repeat(100) })).toHaveLength(40);
    expect(labelOf(match, null)).toBe('');
  });
});
