import { beforeEach, describe, expect, it } from 'vitest';
import { freshIndexedDb, noIndexedDb } from '../test/fakeIdb';
import type { OutboxOp } from './opTypes';
import { addOp, clearOutbox, listOps, refreshOutboxCounts, removeOp, updateOp } from './outbox';
import { getOutboxCounts, resetSyncStateForTests } from './outboxState';
import { clearOfflineData, setOfflineOwner } from './readCache';

const base = (n: number, over: Partial<Omit<OutboxOp, 'seq' | 'status' | 'attempts'>> = {}) => ({
  ownerId: 'owner-1', createdAt: 1000 + n, method: 'POST' as const, path: '/api/x', body: { n }, kind: 'note.create' as const, entityId: `e${n}`, label: `L${n}`, ...over,
});

describe('the outbox on the phone (Stage 19C)', () => {
  beforeEach(async () => {
    localStorage.clear();
    resetSyncStateForTests();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });

  it('keeps the changes in the order they were made, pending, with the counts in memory', async () => {
    await addOp(base(1));
    await addOp(base(2));
    await addOp(base(3));

    const ops = await listOps();
    expect(ops.map((o) => o.label)).toEqual(['L1', 'L2', 'L3']);
    expect(ops.every((o) => o.status === 'pending' && o.attempts === 0)).toBe(true);
    expect(ops[0].seq).toBeLessThan(ops[1].seq as number);
    expect(getOutboxCounts()).toEqual({ pending: 3, failed: 0 });
  });

  it('a change is updated in place, a failed one is counted apart, a sent one is removed', async () => {
    const a = await addOp(base(1));
    const b = await addOp(base(2));

    await updateOp(a!.seq as number, { status: 'failed', attempts: 1, error: { status: 422, message: 'no' } });
    expect(getOutboxCounts()).toEqual({ pending: 1, failed: 1 });
    expect((await listOps())[0]).toMatchObject({ status: 'failed', attempts: 1, error: { status: 422 }, label: 'L1' });

    await removeOp(b!.seq as number);
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 1 });
    expect(await listOps()).toHaveLength(1);
  });

  it('shows only the changes of the signed-in owner', async () => {
    await addOp(base(1));
    await addOp(base(2, { ownerId: 'someone-else' }));
    expect((await listOps()).map((o) => o.label)).toEqual(['L1']);
  });

  it('survives the application being closed: the next start finds the changes and counts them', async () => {
    await addOp(base(1));
    resetSyncStateForTests(); // the memory of the application is gone, the phone keeps the store
    expect(getOutboxCounts().pending).toBe(0);

    await refreshOutboxCounts();

    expect(getOutboxCounts().pending).toBe(1);
  });

  it('is emptied by "Wyczyść dane offline" and when another owner signs in', async () => {
    await addOp(base(1));
    await clearOfflineData();
    expect(await listOps()).toEqual([]);
    expect(getOutboxCounts()).toEqual({ pending: 0, failed: 0 });

    await addOp(base(2));
    await setOfflineOwner('owner-2');
    expect(await listOps()).toEqual([]);
    await setOfflineOwner('owner-1');
    expect(await listOps()).toEqual([]); // really gone, not hidden
  });

  it('clearOutbox empties only the changes', async () => {
    await addOp(base(1));
    await clearOutbox();
    expect(await listOps()).toEqual([]);
  });

  it('keeps nothing without IndexedDB (the caller then fails as before)', async () => {
    await noIndexedDb();
    localStorage.setItem('offline_owner', 'owner-1');
    expect(await addOp(base(1))).toBeNull();
    expect(await listOps()).toEqual([]);
    await expect(updateOp(1, { attempts: 2 })).resolves.toBeUndefined();
    await expect(removeOp(1)).resolves.toBeUndefined();
  });
});
