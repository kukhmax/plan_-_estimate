import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { fetchPhoto, uploadPhoto } from '../api/photos';
import { PhotoCaptureSource, PhotoTarget } from '../types/photo';
import { PhotoUploadQueue, QueueItem } from '../utils/photoUploadQueue';
import { refreshPhotoStorage } from './usePhotoStorage';

// One queue per app session, so uploads started in a card keep going while the user navigates inside the Mini App
// (D2: in-memory only, a WebView restart drops it).

let shared: PhotoUploadQueue | null = null;
const doneListeners = new Set<(item: QueueItem) => void>();
const refetchListeners = new Set<(what: 'parent' | 'list', item: QueueItem) => void>();

export function getPhotoUploadQueue(): PhotoUploadQueue {
  if (!shared) {
    shared = new PhotoUploadQueue({
      transport: { upload: uploadPhoto, fetchDetail: fetchPhoto },
      onDone: (item) => doneListeners.forEach((listener) => listener(item)),
      onRefetch: (what, item) => refetchListeners.forEach((listener) => listener(what, item)),
      // The gate closed or the quota is full: refresh the shared status so every section hides its buttons.
      onStopped: () => {
        void refreshPhotoStorage();
      },
    });
  }
  return shared;
}

/** Tests / logout: drop the shared queue (aborts the active upload, revokes previews). */
export function resetPhotoUploadQueue(): void {
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
  };
}
