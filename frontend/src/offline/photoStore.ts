import { offlineDb } from './db';
import { currentOfflineOwner } from './readCache';
import type { PhotoQueueStore, QueueItem, StoredPhoto, StoredPhotoPatch } from '../utils/photoUploadQueue';

// Stage 19D: where the photos taken without a signal rest until they are sent. The facts about a photo are in `photos`, its bytes in
// `photoFiles` (under the same id); both belong to the owner who is signed in.

/** A File's bytes; `FileReader` where `arrayBuffer()` is missing (an old WebView). */
async function bytesOfFile(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === 'function') return file.arrayBuffer();
  return new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error('the photo could not be read'));
    reader.readAsArrayBuffer(file);
  });
}

function requireDb() {
  const db = offlineDb();
  if (!db) throw new Error('IndexedDB is not available');
  return db;
}

export const idbPhotoStore: PhotoQueueStore = {
  async put(item: QueueItem, file: File): Promise<void> {
    const owner = currentOfflineOwner();
    if (!owner) throw new Error('no signed-in owner to keep the photo for');
    const bytes = await bytesOfFile(file);
    const record: StoredPhoto = {
      id: item.id,
      ownerId: owner,
      uploadId: item.uploadId,
      target: item.target,
      source: item.source,
      name: file.name,
      type: file.type,
      lastModified: file.lastModified,
      size: file.size,
      createdAt: Date.now(),
      state: item.state === 'failed' ? 'failed' : 'queued',
      attempt: item.attempt,
      error: item.error,
    };
    const db = await requireDb();
    // the bytes and the record are written together: a record without bytes would never be sent
    const tx = db.transaction(['photos', 'photoFiles'], 'readwrite');
    await Promise.all([tx.objectStore('photoFiles').put({ id: item.id, bytes }), tx.objectStore('photos').put(record), tx.done]);
  },

  async update(id: string, patch: StoredPhotoPatch): Promise<void> {
    const db = await requireDb();
    const tx = db.transaction('photos', 'readwrite');
    const record = await tx.store.get(id);
    if (record) await tx.store.put({ ...record, ...patch });
    await tx.done;
  },

  async remove(id: string): Promise<void> {
    const db = await requireDb();
    const tx = db.transaction(['photos', 'photoFiles'], 'readwrite');
    await Promise.all([tx.objectStore('photos').delete(id), tx.objectStore('photoFiles').delete(id), tx.done]);
  },

  async loadFile(id: string): Promise<File | null> {
    const db = await requireDb();
    const [record, stored] = await Promise.all([db.get('photos', id), db.get('photoFiles', id)]);
    if (!record || !stored) return null;
    return new File([stored.bytes], record.name, { type: record.type, lastModified: record.lastModified });
  },
};

/** The unfinished photos of the owner who is signed in (what a restart found on the phone). */
export async function loadStoredPhotos(): Promise<StoredPhoto[]> {
  const owner = currentOfflineOwner();
  const db = offlineDb();
  if (!owner || !db) return [];
  try {
    const all = await (await db).getAll('photos');
    return all.filter((record) => record.ownerId === owner);
  } catch (error) {
    console.warn('[photos] the waiting photos could not be read', error);
    return [];
  }
}
