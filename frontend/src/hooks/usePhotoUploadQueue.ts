import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { fetchPhoto, uploadPhoto } from '../api/photos';
import { PhotoCaptureSource, PhotoTarget } from '../types/photo';
import { getConnectionState, subscribeConnection } from '../offline/connection';
import { offlineDb } from '../offline/db';
import { getOutboxCounts, subscribeOutbox } from '../offline/outboxState';
import { idbPhotoStore, loadStoredPhotos } from '../offline/photoStore';
import { onOfflineDataCleared } from '../offline/readCache';
import { signInAgain } from '../offline/sync';
import { PHOTO_QUEUE_LIMIT_BYTES, PHOTO_QUEUE_WARN_BYTES, PhotoUploadQueue, QueueItem, queueBytes } from '../utils/photoUploadQueue';
import { refreshPhotoStorage } from './usePhotoStorage';

// One queue per app session, so uploads started in a card keep going while the user navigates inside the Mini App.
// Stage 19D: the unfinished photos are kept on the phone (IndexedDB), so a closed application or a missing signal does not lose
// them. The queue waits while there is no signal, and while older changes (a room, a wall the photo belongs to) are still
// on the phone; it starts again by itself when either changes.

let shared: PhotoUploadQueue | null = null;
let stopWatching: (() => void) | null = null;
const doneListeners = new Set<(item: QueueItem) => void>();
const refetchListeners = new Set<(what: 'parent' | 'list', item: QueueItem) => void>();

export function getPhotoUploadQueue(): PhotoUploadQueue {
  if (!shared) {
    const queue = new PhotoUploadQueue({
      transport: { upload: uploadPhoto, fetchDetail: fetchPhoto },
      store: offlineDb() ? idbPhotoStore : undefined,
      canStart: () => !getConnectionState().offline && getOutboxCounts().pending === 0,
      refreshSession: signInAgain,
      onDone: (item) => doneListeners.forEach((listener) => listener(item)),
      onRefetch: (what, item) => refetchListeners.forEach((listener) => listener(what, item)),
      // The gate closed or the quota is full: refresh the shared status so every section hides its buttons.
      onStopped: () => {
        void refreshPhotoStorage();
      },
    });
    shared = queue;
    const offConnection = subscribeConnection(() => queue.kick());
    const offOutbox = subscribeOutbox(() => queue.kick());
    const offCleared = onOfflineDataCleared(() => resetPhotoUploadQueue());
    stopWatching = () => {
      offConnection();
      offOutbox();
      offCleared();
    };
  }
  return shared;
}

/** After the owner is known: puts back the photos the phone kept from an earlier session and starts sending them. */
export async function restorePhotoQueue(): Promise<void> {
  if (!offlineDb()) return;
  const records = await loadStoredPhotos();
  if (records.length > 0) getPhotoUploadQueue().restore(records);
}

/** Tests / logout: drop the shared queue (aborts the active upload, revokes previews). */
export function resetPhotoUploadQueue(): void {
  stopWatching?.();
  stopWatching = null;
  shared?.destroy();
  shared = null;
}

/** Host callback after an item reached `done` (refetch the list, adjust counts). Returns the unsubscribe. */
export function subscribePhotoUploadDone(listener: (item: QueueItem) => void): () => void {
  doneListeners.add(listener);
  return () => {
    doneListeners.delete(listener);
  };
}

export function subscribePhotoUploadRefetch(listener: (what: 'parent' | 'list', item: QueueItem) => void): () => void {
  refetchListeners.add(listener);
  return () => {
    refetchListeners.delete(listener);
  };
}

export interface PhotoUploadQueueView {
  items: readonly QueueItem[];
  enqueue: (files: readonly File[], target: PhotoTarget, source: PhotoCaptureSource) => ReturnType<PhotoUploadQueue['enqueue']>;
  cancel: (id: string) => void;
  retry: (id: string) => void;
  retryAsNew: (id: string) => void;
  dismiss: (id: string) => void;
  dismissDone: () => void;
  /** Bytes taken by the photos still waiting on the phone, and the limit (Q3: 200 MB, a warning from 80 %). */
  usedBytes: number;
  limitBytes: number;
  nearlyFull: boolean;
}

/** Queue items of one project (all items when `projectId` is omitted). */
export function usePhotoUploadQueue(projectId?: string): PhotoUploadQueueView {
  const queue = getPhotoUploadQueue();
  const all = useSyncExternalStore(queue.subscribe, queue.getItems, queue.getItems);

  // Foreground / back online: a suspended WebView may have lost the response of an in-flight upload.
  useEffect(() => {
    const reconcile = () => {
      void queue.reconcile();
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') reconcile();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('online', reconcile);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('online', reconcile);
    };
  }, [queue]);

  const items = useMemo(
    () => (projectId ? all.filter((item) => item.target.projectId === projectId) : all),
    [all, projectId],
  );

  const usedBytes = useMemo(() => queueBytes(all), [all]);

  const enqueue = useCallback(
    (files: readonly File[], target: PhotoTarget, source: PhotoCaptureSource) => queue.enqueue(files, target, source),
    [queue],
  );

  return {
    items,
    enqueue,
    cancel: useCallback((id: string) => queue.cancel(id), [queue]),
    retry: useCallback((id: string) => queue.retry(id), [queue]),
    retryAsNew: useCallback((id: string) => queue.retryAsNew(id), [queue]),
    dismiss: useCallback((id: string) => queue.dismiss(id), [queue]),
    dismissDone: useCallback(() => queue.dismissDone(), [queue]),
    usedBytes,
    limitBytes: PHOTO_QUEUE_LIMIT_BYTES,
    nearlyFull: usedBytes >= PHOTO_QUEUE_WARN_BYTES,
  };
}
