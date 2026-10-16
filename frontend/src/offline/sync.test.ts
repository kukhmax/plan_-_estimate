import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as authApi from '../api/auth';
import { freshIndexedDb } from '../test/fakeIdb';
import { getConnectionState, reportNetworkFailure, reportNetworkSuccess, resetConnectionForTests } from './connection';
import { addOp, listOps, refreshOutboxCounts } from './outbox';
import { drainNow, getOutboxCounts, getSyncInfo, resetSyncStateForTests } from './outboxState';
import type { OutboxKind } from './opTypes';
import { setOfflineOwner } from './readCache';
import { MAX_ATTEMPTS, SYNC_INTERVAL_MS, drainOutbox, startSync } from './sync';

vi.mock('../api/auth', () => ({ loginWithTelegram: vi.fn() }));

const P = '11111111-1111-4111-8111-111111111111';
const R = '22222222-2222-4222-8222-222222222222';
const ok = (status = 200, body: unknown = {}) => ({ ok: true, status, json: async () => body }) as unknown as Response;
const refuse = (status: number, detail: unknown) => ({ ok: false, status, json: async () => ({ detail }) }) as unknown as Response;

async function queue(kind: OutboxKind, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body: Record<string, unknown> | null, label: string = kind) {
  return addOp({ ownerId: 'owner-1', createdAt: Date.now(), method, path, body, kind, entityId: (body?.id as string) ?? null, label });
}
const create = (label: string) => queue('room.create', 'POST', `/api/projects/${P}/rooms`, { id: R, name: label }, label);

describe('the sync engine (Stage 19C)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.stubGlobal('fetch', vi.fn());
    vi.mocked(authApi.loginWithTelegram).mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete (window as unknown as { Telegram?: unknown }).Telegram;
  });

  it('sends the changes one at a time in the order they were made, with the token and the body, and removes each when the server accepts it', async () => {
    await create('A');
    await queue('room.update', 'PATCH', `/api/projects/${P}/rooms/${R}`, { name: 'B' });
    await queue('room.archive', 'POST', `/api/projects/${P}/rooms/${R}/archive`, null);
    vi.mocked(fetch).mockResolvedValue(ok());

    const result = await drainOutbox();

    expect(result).toEqual({ sent: 3, refused: 0, stoppedBy: null });
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.map((c) => [(c[1] as RequestInit).method, c[0]])).toEqual([
      ['POST', `/api/projects/${P}/rooms`],
      ['PATCH', `/api/projects/${P}/rooms/${R}`],
      ['POST', `/api/projects/${P}/rooms/${R}/archive`],
    ]);
    const first = calls[0][1] as RequestInit;
    expect((first.headers as Headers).get('Authorization')).toBe('Bearer tok');
    expect((first.headers as Headers).get('Content-Type')).toBe('application/json');
    expect(JSON.parse(first.body as string)).toEqual({ id: R, name: 'A' });
    expect((calls[2][1] as RequestInit).body).toBeUndefined(); // an archive has no body, and no content type
    expect(await listOps()).toEqual([]);
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 0 });
    expect(getSyncInfo().lastSent?.count).toBe(3);
    expect(getSyncInfo().running).toBe(false);
  });

  it('does nothing when nothing waits', async () => {
    expect(await drainOutbox()).toEqual({ sent: 0, refused: 0, stoppedBy: null });
    expect(fetch).not.toHaveBeenCalled();
    expect(getSyncInfo().lastSent).toBeNull();
  });

  it('stops when the network is gone: the change and the ones behind it stay, in the same order, and the connection is marked offline', async () => {
    await create('A');
    await queue('room.update', 'PATCH', `/api/projects/${P}/rooms/${R}`, { name: 'B' });
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));

    const result = await drainOutbox();

    expect(result).toMatchObject({ sent: 0, stoppedBy: 'network' });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect((await listOps()).map((o) => o.kind)).toEqual(['room.create', 'room.update']);
    expect(getOutboxCounts().pending).toBe(2);
    expect(getConnectionState().offline).toBe(true);
  });

  it('what was sent before the network went stays sent, and the rest goes later', async () => {
    await create('A');
    await queue('room.update', 'PATCH', `/api/projects/${P}/rooms/${R}`, { name: 'B' });
    vi.mocked(fetch).mockResolvedValueOnce(ok(201)).mockRejectedValueOnce(new TypeError('x'));
    await drainOutbox();
    expect((await listOps()).map((o) => o.kind)).toEqual(['room.update']);

    vi.mocked(fetch).mockResolvedValue(ok());
    expect(await drainOutbox()).toMatchObject({ sent: 1 });
    expect(await listOps()).toEqual([]);
  });

  it('a change the server refuses is kept for the owner with the reason, and the ones behind it still go', async () => {
    await queue('opening.create', 'POST', `/api/projects/${P}/rooms/${R}/surfaces/${R}/openings`, { id: P, width: 5 }, 'big door');
    await queue('note.create', 'POST', `/api/projects/${P}/notes`, { id: R, body: 'x' });
    vi.mocked(fetch)
      .mockResolvedValueOnce(refuse(422, 'Total opening deductions (20) would exceed wall gross area (9)'))
      .mockResolvedValueOnce(ok(201));

    const result = await drainOutbox();

    expect(result).toEqual({ sent: 1, refused: 1, stoppedBy: null });
    const left = await listOps();
    expect(left).toHaveLength(1);
    expect(left[0]).toMatchObject({ kind: 'opening.create', status: 'failed', attempts: 1, error: { status: 422, code: 'openings_deductions_exceed_gross' } });
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 1 });
  });

  it('a conflict of the id is refused with its code', async () => {
    await create('A');
    vi.mocked(fetch).mockResolvedValue(refuse(409, { code: 'CLIENT_ID_CONFLICT', message: 'The id is already used' }));
    await drainOutbox();
    expect((await listOps())[0]).toMatchObject({ status: 'failed', error: { status: 409, code: 'CLIENT_ID_CONFLICT' } });
  });

  it('a server error is tried again later, up to five times, then handed to the owner', async () => {
    await create('A');
    vi.mocked(fetch).mockResolvedValue(refuse(503, 'down'));

    for (let i = 1; i < MAX_ATTEMPTS; i++) {
      expect(await drainOutbox()).toMatchObject({ stoppedBy: 'server' });
      expect((await listOps())[0]).toMatchObject({ status: 'pending', attempts: i });
    }
    expect(await drainOutbox()).toMatchObject({ refused: 1 });
    expect((await listOps())[0]).toMatchObject({ status: 'failed', attempts: MAX_ATTEMPTS, error: { status: 503 } });
  });

  it('removing a note that is already gone counts as done', async () => {
    await queue('note.delete', 'DELETE', `/api/projects/${P}/notes/${R}`, null);
    vi.mocked(fetch).mockResolvedValue(refuse(404, 'Note not found'));
    expect(await drainOutbox()).toMatchObject({ sent: 1, refused: 0 });
    expect(await listOps()).toEqual([]);
  });

  it('an expired token: signs in again with the data of Telegram and sends the same change with the new token', async () => {
    (window as unknown as { Telegram: unknown }).Telegram = { WebApp: { initData: 'signed-by-telegram' } };
    vi.mocked(authApi.loginWithTelegram).mockResolvedValue({ access_token: 'new-token' } as never);
    await create('A');
    vi.mocked(fetch).mockResolvedValueOnce(refuse(401, 'expired')).mockResolvedValueOnce(ok(201));

    expect(await drainOutbox()).toMatchObject({ sent: 1 });

    expect(authApi.loginWithTelegram).toHaveBeenCalledWith('signed-by-telegram');
    expect(localStorage.getItem('access_token')).toBe('new-token');
    expect(((vi.mocked(fetch).mock.calls[1][1] as RequestInit).headers as Headers).get('Authorization')).toBe('Bearer new-token');
  });

  it('an expired token that cannot be renewed stops the sending and says the owner has to sign in; nothing is lost', async () => {
    await create('A');
    vi.mocked(fetch).mockResolvedValue(refuse(401, 'expired'));

    expect(await drainOutbox()).toMatchObject({ sent: 0, stoppedBy: 'login' });

    expect(getSyncInfo().needsLogin).toBe(true);
    expect(await listOps()).toHaveLength(1);
    expect(getOutboxCounts().pending).toBe(1);
  });

  it('sends one run at a time: two calls share one sending', async () => {
    await create('A');
    let release: () => void = () => {};
    vi.mocked(fetch).mockImplementation(() => new Promise((resolve) => { release = () => resolve(ok(201)); }));

    const first = drainOutbox();
    const second = drainOutbox();
    expect(second).toBe(first);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    release();
    await first;
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('sends only the changes of the signed-in owner', async () => {
    await addOp({ ownerId: 'someone-else', createdAt: 1, method: 'POST', path: `/api/projects/${P}/notes`, body: { id: R, body: 'x' }, kind: 'note.create', entityId: R, label: '' });
    await create('mine');
    vi.mocked(fetch).mockResolvedValue(ok(201));
    await drainOutbox();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

const idle = () => vi.waitFor(() => expect(getSyncInfo().running).toBe(false)); // a sending in flight would reach into the next test

describe('when the engine looks at the outbox (Stage 19C)', () => {
  beforeEach(async () => {
    localStorage.clear();
    localStorage.setItem('access_token', 'tok');
    resetConnectionForTests();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(201)));
    await create('A');
    await refreshOutboxCounts();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('after the application starts it sends what was left on the phone the last time', async () => {
    const stop = startSync();
    await vi.advanceTimersByTimeAsync(1500);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await idle();
    stop();
  });

  it('does not try while the server is known to be out of reach; sends when the signal is back', async () => {
    reportNetworkFailure();
    const stop = startSync();
    await vi.advanceTimersByTimeAsync(SYNC_INTERVAL_MS + 1000);
    expect(fetch).not.toHaveBeenCalled();

    reportNetworkSuccess();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1)); // the store answers on the real scheduler
    await idle();
    stop();
  });

  it('looks again every 30 seconds while something waits (a server that was down)', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(refuse(503, 'down')).mockResolvedValue(ok(201));
    const stop = startSync();
    await vi.advanceTimersByTimeAsync(1500);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await idle();
    await vi.advanceTimersByTimeAsync(SYNC_INTERVAL_MS);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await idle();
    stop();
  });

  it('lets what acts on the server send the waiting changes first, and only while it runs (Stage 19C.3)', async () => {
    const stop = startSync();
    await drainNow(); // the engine's own runner, not the timer
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getOutboxCounts().pending).toBe(0);

    stop();
    await create('B');
    await refreshOutboxCounts();
    await drainNow();
    expect(fetch).toHaveBeenCalledTimes(1); // nothing is sent once the engine is stopped
  });

  it('stops looking when stopped', async () => {
    const stop = startSync();
    stop();
    await vi.advanceTimersByTimeAsync(SYNC_INTERVAL_MS * 2);
    expect(fetch).not.toHaveBeenCalled();
  });
});
