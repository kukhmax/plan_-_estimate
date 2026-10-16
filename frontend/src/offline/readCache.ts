import { offlineDb, type CachedRead } from './db';
import { setOutboxCounts } from './outboxState';

const OWNER_KEY = 'offline_owner';
export const READ_CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000; // 30 days without being saved again (Q10)

function warn(what: string, error: unknown): void {
  // storage trouble must never break the application, but it is not hidden either
  console.warn(`[offline] ${what}`, error);
}

export function currentOfflineOwner(): string | null {
  try {
    return localStorage.getItem(OWNER_KEY);
  } catch {
    return null;
  }
}

/** The owner who is signed in. Another owner than the one whose data is on the phone: everything stored is removed first (Q8). */
export async function setOfflineOwner(ownerId: string): Promise<void> {
  const previous = currentOfflineOwner();
  if (previous !== null && previous !== ownerId) await clearOfflineData();
  try {
    localStorage.setItem(OWNER_KEY, ownerId);
  } catch (error) {
    warn('the owner could not be remembered', error);
  }
}

const keyOf = (ownerId: string, path: string) => `${ownerId}|${path}`;

export async function saveRead(path: string, data: unknown): Promise<void> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return;
  try {
    const record: CachedRead = { key: keyOf(owner, path), ownerId: owner, path, savedAt: Date.now(), data };
    await (await db).put('readCache', record);
  } catch (error) {
    warn('a copy could not be saved', error);
  }
}

export async function loadRead(path: string): Promise<{ data: unknown; savedAt: number } | null> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return null;
  try {
    const record = await (await db).get('readCache', keyOf(owner, path));
    return record ? { data: record.data, savedAt: record.savedAt } : null;
  } catch (error) {
    warn('a copy could not be read', error);
    return null;
  }
}

/** The saved copies whose path starts with `prefix` (the list of a kind of record and the records under it). */
export async function loadReadsByPrefix(prefix: string): Promise<Array<{ path: string; data: unknown; savedAt: number }>> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return [];
  try {
    const range = IDBKeyRange.bound(keyOf(owner, prefix), `${keyOf(owner, prefix)}\uffff`);
    const records = await (await db).getAll('readCache', range);
    return records.map((record) => ({ path: record.path, data: record.data, savedAt: record.savedAt }));
  } catch (error) {
    warn('copies could not be listed', error);
    return [];
  }
}

export async function countSavedReads(): Promise<number> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return 0;
  try {
    const all = await (await db).getAllKeys('readCache');
    return all.filter((key) => String(key).startsWith(`${owner}|`)).length;
  } catch (error) {
    warn('the copies could not be counted', error);
    return 0;
  }
}

/** Removes everything the application keeps for work without a signal ("Wyczyść dane offline", a change of owner). */
export async function clearOfflineData(): Promise<void> {
  const db = offlineDb();
  if (!db) return;
  try {
    const handle = await db;
    await handle.clear('readCache');
    await handle.clear('meta');
    await handle.clear('outbox');
    setOutboxCounts({ pending: 0, failed: 0 });
  } catch (error) {
    warn('the offline data could not be cleared', error);
  }
}

/** Copies not saved again for 30 days go (Q10). */
export async function purgeStaleReads(now: number = Date.now()): Promise<number> {
  const db = offlineDb();
  if (!db) return 0;
  try {
    const handle = await db;
    const stale = await handle.getAllKeysFromIndex('readCache', 'by-saved', IDBKeyRange.upperBound(now - READ_CACHE_MAX_AGE_MS));
    for (const key of stale) await handle.delete('readCache', key);
    return stale.length;
  } catch (error) {
    warn('old copies could not be removed', error);
    return 0;
  }
}

export async function setMeta(key: string, value: unknown): Promise<void> {
  const db = offlineDb();
  if (!db) return;
  try {
    await (await db).put('meta', { key, value });
  } catch (error) {
    warn('a note could not be saved', error);
  }
}

export async function getMeta<T>(key: string): Promise<T | null> {
  const db = offlineDb();
  if (!db) return null;
  try {
    const record = await (await db).get('meta', key);
    return record ? (record.value as T) : null;
  } catch (error) {
    warn('a note could not be read', error);
    return null;
  }
}
