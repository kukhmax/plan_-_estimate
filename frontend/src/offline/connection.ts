import { useSyncExternalStore } from 'react';

/**
 * What the application knows about its connection (Stage 19B). It is learned from the requests themselves — `navigator.onLine` often
 * says "online" in a basement with no signal — and from the browser's online / offline events.
 */
export interface ConnectionState {
  /** The last request (or the browser) said the server cannot be reached. */
  offline: boolean;
  /** The oldest saved copy shown since the last answer from the server (ms); null when everything on screen is fresh. */
  servedFrom: number | null;
}

let state: ConnectionState = { offline: false, servedFrom: null };
const listeners = new Set<() => void>();

function set(next: ConnectionState): void {
  if (next.offline === state.offline && next.servedFrom === state.servedFrom) return;
  state = next;
  listeners.forEach((listener) => listener());
}

export const getConnectionState = (): ConnectionState => state;

export function subscribeConnection(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function reportNetworkFailure(): void {
  set({ ...state, offline: true });
}

/** Any answer of the server (even an error one) proves the server is reachable. */
export function reportNetworkSuccess(): void {
  set({ offline: false, servedFrom: null });
}

export function reportServedFromCache(savedAt: number): void {
  set({ ...state, servedFrom: state.servedFrom === null ? savedAt : Math.min(state.servedFrom, savedAt) });
}

export function resetConnectionForTests(): void {
  state = { offline: false, servedFrom: null };
  listeners.forEach((listener) => listener());
}

export function useConnection(): ConnectionState {
  return useSyncExternalStore(subscribeConnection, getConnectionState, getConnectionState);
}
