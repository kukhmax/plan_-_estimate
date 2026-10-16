import { beforeEach, describe, expect, it, vi } from 'vitest';
import { freshIndexedDb } from '../test/fakeIdb';
import type { QueueItem } from '../utils/photoUploadQueue';
import { offlineDb } from './db';
import { idbPhotoStore, loadStoredPhotos } from './photoStore';
import { clearOfflineData, onOfflineDataCleared, setOfflineOwner } from './readCache';

const item = (id: string, over: Partial<QueueItem> = {}): QueueItem => ({
  id, uploadId: `up-${id}`, file: null, name: 'x.jpg', size: 3, target: { projectId: 'p1', context: 'SURFACE', surfaceId: 's1' },
  source: 'CAMERA', state: 'queued', progress: 0, attempt: 0, previewUrl: null, error: null, result: null, notBefore: 0,
  networkRetries: 0, busyRetried: false, verify: false, authRetried: false, saveFailed: false, ...over,
});

const photo = (name = 'IMG_1.jpg') => new File([new Uint8Array([1, 2, 3])], name, { type: 'image/jpeg', lastModified: 1234 });

// jsdom's File has no arrayBuffer(): the store's FileReader fallback is what these tests exercise
const bytesOf = (f: File) =>
  new Promise<ArrayBuffer>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.readAsArrayBuffer(f);
  });

describe('the photos kept on the phone (Stage 19D)', () => {
  beforeEach(async () => {
    localStorage.clear();
    await freshIndexedDb();
    await setOfflineOwner('owner-1');
  });

  it('keeps a photo and gives back the same bytes, name, type and date', async () => {
    await idbPhotoStore.put(item('a'), photo());
    const back = await idbPhotoStore.loadFile('a');
    expect(back).toMatchObject({ name: 'IMG_1.jpg', type: 'image/jpeg', lastModified: 1234, size: 3 });
    expect(new Uint8Array(await bytesOf(back!))).toEqual(new Uint8Array([1, 2, 3]));

    const [record] = await loadStoredPhotos();
    expect(record).toMatchObject({ id: 'a', ownerId: 'owner-1', uploadId: 'up-a', state: 'queued', attempt: 0, size: 3, target: { surfaceId: 's1' } });
  });

  it('a change of state rewrites the record only, not the bytes', async () => {
    await idbPhotoStore.put(item('a'), photo());
    await idbPhotoStore.update('a', { attempt: 2, state: 'failed', uploadId: 'up-new' });
    const [record] = await loadStoredPhotos();
    expect(record).toMatchObject({ attempt: 2, state: 'failed', uploadId: 'up-new', name: 'IMG_1.jpg' });
    expect((await idbPhotoStore.loadFile('a'))?.size).toBe(3);
    await idbPhotoStore.update('missing', { attempt: 1 }); // nothing there: no record is invented
    expect(await loadStoredPhotos()).toHaveLength(1);
  });

  it('removing a photo removes its bytes too', async () => {
    await idbPhotoStore.put(item('a'), photo());
    await idbPhotoStore.remove('a');
    expect(await loadStoredPhotos()).toEqual([]);
    expect(await idbPhotoStore.loadFile('a')).toBeNull();
    const db = await offlineDb()!;
    expect(await db.count('photoFiles')).toBe(0);
  });

  it('shows an owner only his own photos', async () => {
    await idbPhotoStore.put(item('a'), photo());
    localStorage.setItem('offline_owner', 'owner-2'); // another signed-in owner without the wipe (defence in depth)
    expect(await loadStoredPhotos()).toEqual([]);
  });

  it('refuses to keep a photo while nobody is signed in', async () => {
    localStorage.clear();
    await expect(idbPhotoStore.put(item('a'), photo())).rejects.toThrow();
  });

  it('"clear offline data" and a change of owner remove the photos and tell the queue', async () => {
    const cleared = vi.fn();
    const off = onOfflineDataCleared(cleared);
    await idbPhotoStore.put(item('a'), photo());
    await idbPhotoStore.put(item('b'), photo('b.jpg'));

    await clearOfflineData();
    expect(await loadStoredPhotos()).toEqual([]);
    const db = await offlineDb()!;
    expect(await db.count('photoFiles')).toBe(0);
    expect(cleared).toHaveBeenCalledTimes(1);

    await idbPhotoStore.put(item('c'), photo());
    await setOfflineOwner('owner-2');
    expect(await loadStoredPhotos()).toEqual([]);
    expect(cleared).toHaveBeenCalledTimes(2);
    off();
  });
});
