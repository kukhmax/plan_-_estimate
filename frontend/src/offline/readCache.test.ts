import { beforeEach, describe, expect, it, vi } from 'vitest';
import { freshIndexedDb, noIndexedDb } from '../test/fakeIdb';
import {
  READ_CACHE_MAX_AGE_MS,
  clearOfflineData,
  countSavedReads,
  currentOfflineOwner,
  getMeta,
  loadRead,
  purgeStaleReads,
  saveRead,
  setMeta,
  setOfflineOwner,
} from './readCache';

describe('the read cache on the phone (Stage 19B)', () => {
  beforeEach(async () => {
    localStorage.clear();
    await freshIndexedDb();
  });

  it('keeps a copy and gives it back with the time it was saved', async () => {
    await setOfflineOwner('owner-1');
    const before = Date.now();
    await saveRead('/api/projects', { items: [{ id: 'p1' }], total: 1 });

    const saved = await loadRead('/api/projects');
    expect(saved?.data).toEqual({ items: [{ id: 'p1' }], total: 1 });
    expect(saved?.savedAt).toBeGreaterThanOrEqual(before);
    expect(await loadRead('/api/clients')).toBeNull();
  });

  it('keeps nothing until an owner is known, and the copies of two owners never meet', async () => {
    await saveRead('/api/projects', { a: 1 });
    expect(await countSavedReads()).toBe(0);

    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { a: 1 });
    expect(await loadRead('/api/projects')).not.toBeNull();

    localStorage.setItem('offline_owner', 'owner-2'); // a stranger's session without the clean-up
    expect(await loadRead('/api/projects')).toBeNull();
  });

  it('removes everything of the previous owner when another one signs in (Q8)', async () => {
    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { a: 1 });
    await setMeta('prepared:p1', { at: 1 });

    await setOfflineOwner('owner-2');

    expect(currentOfflineOwner()).toBe('owner-2');
    expect(await countSavedReads()).toBe(0);
    expect(await getMeta('prepared:p1')).toBeNull();
    await setOfflineOwner('owner-1');
    expect(await loadRead('/api/projects')).toBeNull(); // really gone, not just hidden
  });

  it('the same owner signing in again keeps the copies', async () => {
    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { a: 1 });
    await setOfflineOwner('owner-1');
    expect(await loadRead('/api/projects')).not.toBeNull();
  });

  it('"Wyczyść dane offline" removes copies and notes', async () => {
    await setOfflineOwner('owner-1');
    await saveRead('/api/projects', { a: 1 });
    await saveRead('/api/clients', { b: 2 });
    await setMeta('prepared:p1', { at: 1 });
    expect(await countSavedReads()).toBe(2);

    await clearOfflineData();

    expect(await countSavedReads()).toBe(0);
    expect(await getMeta('prepared:p1')).toBeNull();
  });

  it('drops copies not saved again for 30 days and keeps the fresh ones (Q10)', async () => {
    await setOfflineOwner('owner-1');
    await saveRead('/api/old', { x: 1 });
    await saveRead('/api/fresh', { x: 2 });
    const now = Date.now() + READ_CACHE_MAX_AGE_MS + 1000;
    // the fresh one is "saved" a day before `now`
    vi.spyOn(Date, 'now').mockReturnValue(now - 24 * 60 * 60 * 1000);
    await saveRead('/api/fresh', { x: 2 });
    vi.restoreAllMocks();

    expect(await purgeStaleReads(now)).toBe(1);
    expect(await loadRead('/api/old')).toBeNull();
    expect(await loadRead('/api/fresh')).not.toBeNull();
  });

  it('works as before where the browser has no IndexedDB', async () => {
    await noIndexedDb();
    localStorage.setItem('offline_owner', 'owner-1');
    await expect(saveRead('/api/projects', {})).resolves.toBeUndefined();
    expect(await loadRead('/api/projects')).toBeNull();
    expect(await countSavedReads()).toBe(0);
    await expect(clearOfflineData()).resolves.toBeUndefined();
    expect(await purgeStaleReads()).toBe(0);
    expect(await getMeta('x')).toBeNull();
  });
});
