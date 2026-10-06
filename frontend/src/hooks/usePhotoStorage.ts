import { useEffect, useSyncExternalStore } from 'react';
import { fetchPhotoStorage } from '../api/photos';
import { PhotoStorageState, PhotoStorageStatus } from '../types/photo';

// One shared `GET /api/photo-storage` per workspace session (contract §4): every photo section reads the same
// snapshot; `refreshPhotoStorage()` refetches (after an upload batch or when the queue is stopped by the server).

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';

interface Snapshot {
  status: LoadStatus;
  data: PhotoStorageStatus | null;
}

let snapshot: Snapshot = { status: 'idle', data: null };
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: Snapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): Snapshot {
  return snapshot;
}

/** Fetch (or join the fetch in flight). Resolves when the snapshot was updated; never rejects. */
export function refreshPhotoStorage(): Promise<void> {
  if (inflight) return inflight;
  publish({ status: snapshot.data ? snapshot.status : 'loading', data: snapshot.data });
  inflight = fetchPhotoStorage()
    .then((data) => publish({ status: 'ready', data }))
    // Unknown availability is treated as "uploads unavailable" by the hook; the last good data is kept.
    .catch(() => publish({ status: 'error', data: snapshot.data }))
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Forget the cached status (tests, logout). */
export function resetPhotoStorage(): void {
  inflight = null;
  publish({ status: 'idle', data: null });
}

export interface PhotoStorageView {
  status: LoadStatus;
  data: PhotoStorageStatus | null;
  /** False while unknown, on error and when the server gate is closed (D5: no upload controls then). */
  uploadsEnabled: boolean;
  mediaAvailable: boolean;
  state: PhotoStorageState | null;
  refresh: () => Promise<void>;
}

export function usePhotoStorage(): PhotoStorageView {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    if (snapshot.status === 'idle') void refreshPhotoStorage();
  }, []);

  const data = current.data;
  return {
    status: current.status,
    data,
    uploadsEnabled: data?.uploads_enabled === true && data.state !== 'FULL',
    mediaAvailable: data?.media_available === true,
    state: data?.state ?? null,
    refresh: refreshPhotoStorage,
  };
}
