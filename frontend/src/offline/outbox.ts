import { offlineDb } from './db';
import { getOutboxCounts, setOutboxCounts, type OutboxCounts } from './outboxState';
import type { OutboxOp } from './opTypes';
import { currentOfflineOwner } from './readCache';

function warn(what: string, error: unknown): void {
  console.warn(`[offline] ${what}`, error);
}

/** Every change of the signed-in owner, in the order they were made. */
export async function listOps(): Promise<OutboxOp[]> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return [];
  try {
    const all = await (await db).getAll('outbox');
    return all.filter((op) => op.ownerId === owner);
  } catch (error) {
    warn('the changes could not be read', error);
    return [];
  }
}

/** Counts are kept in memory (for the strip and for the "is anything waiting?" question of every request) and refreshed from the store. */
export async function refreshOutboxCounts(): Promise<OutboxCounts> {
  const ops = await listOps();
  setOutboxCounts({ pending: ops.filter((op) => op.status === 'pending').length, failed: ops.filter((op) => op.status === 'failed').length });
  return getOutboxCounts();
}

export async function addOp(op: Omit<OutboxOp, 'seq' | 'status' | 'attempts'>): Promise<OutboxOp | null> {
  const db = offlineDb();
  if (!db) return null;
  try {
    const record = { ...op, status: 'pending', attempts: 0 } as OutboxOp;
    const seq = await (await db).add('outbox', record);
    await refreshOutboxCounts();
    return { ...record, seq: Number(seq) };
  } catch (error) {
    warn('a change could not be kept', error);
    return null;
  }
}

export async function updateOp(seq: number, patch: Partial<OutboxOp>): Promise<void> {
  const db = offlineDb();
  if (!db) return;
  try {
    const handle = await db;
    const current = await handle.get('outbox', seq);
    if (current) await handle.put('outbox', { ...current, ...patch, seq });
    await refreshOutboxCounts();
  } catch (error) {
    warn('a change could not be updated', error);
  }
}

export async function removeOp(seq: number): Promise<void> {
  const db = offlineDb();
  if (!db) return;
  try {
    await (await db).delete('outbox', seq);
    await refreshOutboxCounts();
  } catch (error) {
    warn('a change could not be removed', error);
  }
}

export async function clearOutbox(): Promise<void> {
  const db = offlineDb();
  if (db) {
    try {
      await (await db).clear('outbox');
    } catch (error) {
      warn('the changes could not be cleared', error);
    }
  }
  setOutboxCounts({ pending: 0, failed: 0 });
}

export function resetOutboxForTests(): void {
  setOutboxCounts({ pending: 0, failed: 0 });
}
