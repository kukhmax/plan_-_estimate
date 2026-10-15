import 'fake-indexeddb/auto'; // the IndexedDB classes (IDBRequest, IDBTransaction …) the idb library expects
import { IDBFactory, IDBKeyRange as FakeKeyRange } from 'fake-indexeddb';
import { closeOfflineDbForTests } from '../offline/db';

/** A fresh, empty IndexedDB for one test (jsdom has none). Call from `beforeEach`. */
export async function freshIndexedDb(): Promise<void> {
  await closeOfflineDbForTests();
  (globalThis as unknown as { indexedDB: IDBFactory }).indexedDB = new IDBFactory();
  (globalThis as unknown as { IDBKeyRange: typeof FakeKeyRange }).IDBKeyRange = FakeKeyRange;
}

/** The browser without IndexedDB (a very old WebView): the application must keep working. */
export async function noIndexedDb(): Promise<void> {
  await closeOfflineDbForTests();
  delete (globalThis as unknown as { indexedDB?: unknown }).indexedDB;
}
