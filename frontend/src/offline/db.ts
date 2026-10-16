import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { OutboxOp } from './opTypes';
import type { StoredPhoto } from '../utils/photoUploadQueue';

export const OFFLINE_DB_NAME = 'plan-estimate-offline';
export const OFFLINE_DB_VERSION = 3;

export interface CachedRead {
  /** `<owner>|<path>`: the copies of two owners never meet. */
  key: string;
  ownerId: string;
  path: string;
  savedAt: number;
  data: unknown;
}

export interface MetaRecord {
  key: string;
  value: unknown;
}

interface OfflineDb extends DBSchema {
  readCache: { key: string; value: CachedRead; indexes: { 'by-saved': number } };
  meta: { key: string; value: MetaRecord };
  /** Stage 19C: the changes made without a signal, in the order they were made (`seq`). */
  outbox: { key: number; value: OutboxOp };
  /** Stage 19D: the photos taken without a signal, what is known about each one (the bytes are in `photoFiles`). */
  photos: { key: string; value: StoredPhoto };
  /** Stage 19D: the bytes of a waiting photo; kept apart so that a change of state does not rewrite up to 25 MB. */
  photoFiles: { key: string; value: PhotoBytes };
}

export interface PhotoBytes {
  id: string;
  /** An ArrayBuffer rather than a Blob: it is copied faithfully by every WebView. */
  bytes: ArrayBuffer;
}

let opened: Promise<IDBPDatabase<OfflineDb>> | null = null;

/** The database of the phone, opened once; `null` where the browser has no IndexedDB (the application then works as before). */
export function offlineDb(): Promise<IDBPDatabase<OfflineDb>> | null {
  if (typeof indexedDB === 'undefined') return null;
  if (!opened) {
    opened = openDB<OfflineDb>(OFFLINE_DB_NAME, OFFLINE_DB_VERSION, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          const reads = db.createObjectStore('readCache', { keyPath: 'key' });
          reads.createIndex('by-saved', 'savedAt');
          db.createObjectStore('meta', { keyPath: 'key' });
        }
        if (oldVersion < 2) db.createObjectStore('outbox', { keyPath: 'seq', autoIncrement: true });
        if (oldVersion < 3) {
          db.createObjectStore('photos', { keyPath: 'id' });
          db.createObjectStore('photoFiles', { keyPath: 'id' });
        }
      },
    }).catch((error: unknown) => {
      opened = null; // try again next time (a private window, a full disk)
      throw error;
    });
  }
  return opened;
}

/** Tests only: forget the opened connection so the next call opens (and, after `indexedDB.deleteDatabase`, recreates) the database. */
export async function closeOfflineDbForTests(): Promise<void> {
  if (opened) {
    const db = await opened.catch(() => null);
    db?.close();
  }
  opened = null;
}
