import { useSyncExternalStore } from 'react';

export interface OutboxCounts {
  pending: number;
  failed: number;
}

/**
 * How many changes wait on the phone, kept in memory: the strip shows it and every request asks "is anything waiting?" (then a new
 * change goes behind the older ones, so the order of the changes is kept). The store refreshes it after every change of the outbox.
 */
let counts: OutboxCounts = { pending: 0, failed: 0 };
const listeners = new Set<() => void>();

export const getOutboxCounts = (): OutboxCounts => counts;

export function setOutboxCounts(next: OutboxCounts): void {
  if (next.pending !== counts.pending || next.failed !== counts.failed) counts = next;
  listeners.forEach((listener) => listener());
}

export function subscribeOutbox(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useOutboxCounts(): OutboxCounts {
  return useSyncExternalStore(subscribeOutbox, getOutboxCounts, getOutboxCounts);
}

/** What the last sending did, for the strip: "12 changes were sent" and whether the owner has to sign in again. */
export interface SyncInfo {
  running: boolean;
  lastSent: { at: number; count: number } | null;
  needsLogin: boolean;
}

let info: SyncInfo = { running: false, lastSent: null, needsLogin: false };
const infoListeners = new Set<() => void>();

export const getSyncInfo = (): SyncInfo => info;

export function setSyncInfo(patch: Partial<SyncInfo>): void {
  info = { ...info, ...patch };
  infoListeners.forEach((listener) => listener());
}

export function useSyncInfo(): SyncInfo {
  return useSyncExternalStore(
    (listener) => {
      infoListeners.add(listener);
      return () => {
        infoListeners.delete(listener);
      };
    },
    getSyncInfo,
    getSyncInfo,
  );
}

/** The sending is started by the engine; a change made on the phone asks it to look at the outbox soon. */
let requestDrain: (delayMs?: number) => void = () => {};
export function setDrainRequester(fn: (delayMs?: number) => void): void {
  requestDrain = fn;
}
export function askForSending(delayMs?: number): void {
  requestDrain(delayMs);
}

/** Sends what waits right now and resolves when the sending is over (the engine registers it); nothing is sent without the engine. */
let drainRunner: (() => Promise<unknown>) | null = null;
export function setDrainRunner(fn: (() => Promise<unknown>) | null): void {
  drainRunner = fn;
}
export async function drainNow(): Promise<void> {
  if (drainRunner) await drainRunner();
}

export function resetSyncStateForTests(): void {
  info = { running: false, lastSent: null, needsLogin: false };
  counts = { pending: 0, failed: 0 };
  requestDrain = () => {};
  drainRunner = null;
}
