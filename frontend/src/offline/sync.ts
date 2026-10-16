import { loginWithTelegram } from '../api/auth';
import { API_BASE, domainErrorCodeFromMessage } from '../api/http';
import { getConnectionState, reportNetworkFailure, reportNetworkSuccess, subscribeConnection } from './connection';
import { listOps, refreshOutboxCounts, removeOp, updateOp } from './outbox';
import { getOutboxCounts, setDrainRequester, setSyncInfo } from './outboxState';
import type { OutboxOp } from './opTypes';

export const SEND_TIMEOUT_MS = 20_000;
export const SYNC_INTERVAL_MS = 30_000;
/** A server error (5xx, 429, 408) is tried this many times before the change is handed to the owner. */
export const MAX_ATTEMPTS = 5;

type Outcome =
  | { kind: 'ok' }
  | { kind: 'network' }
  | { kind: 'auth' }
  | { kind: 'retry'; status: number; message: string }
  | { kind: 'refused'; status: number; code?: string; message: string };

async function sendOp(op: OutboxOp): Promise<Outcome> {
  const headers = new Headers();
  if (op.body !== null) headers.set('Content-Type', 'application/json');
  const token = localStorage.getItem('access_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), SEND_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${op.path}`, {
      method: op.method,
      headers,
      body: op.body !== null ? JSON.stringify(op.body) : undefined,
      signal: controller.signal,
    });
    if (response.ok) return { kind: 'ok' };
    if (response.status === 401) return { kind: 'auth' };
    // the record is already gone (this very removal was made before the answer was lost): nothing left to do
    if (response.status === 404 && op.method === 'DELETE') return { kind: 'ok' };
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const structured = typeof detail === 'object' && detail !== null && !Array.isArray(detail) ? (detail as { code?: unknown; message?: unknown }) : null;
    const message = typeof detail === 'string' ? detail : typeof structured?.message === 'string' ? structured.message : `Request failed (${response.status})`;
    const code = typeof structured?.code === 'string' ? structured.code : typeof detail === 'string' ? domainErrorCodeFromMessage(detail) : undefined;
    if (response.status >= 500 || response.status === 429 || response.status === 408) return { kind: 'retry', status: response.status, message };
    return { kind: 'refused', status: response.status, code, message };
  } catch {
    return { kind: 'network' };
  } finally {
    clearTimeout(timer);
  }
}

/** The token expired while the changes were waiting: sign in again by the data Telegram gives the open Mini App (no password). */
async function signInAgain(): Promise<boolean> {
  const initData = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp?.initData;
  if (!initData) return false;
  try {
    const response = await loginWithTelegram(initData);
    localStorage.setItem('access_token', response.access_token);
    return true;
  } catch {
    return false;
  }
}

export interface DrainResult {
  sent: number;
  refused: number;
  /** Why the sending stopped before the end of the queue, if it did. */
  stoppedBy: 'network' | 'server' | 'login' | null;
}

let draining: Promise<DrainResult> | null = null;

async function run(): Promise<DrainResult> {
  const result: DrainResult = { sent: 0, refused: 0, stoppedBy: null };
  let triedLogin = false;
  setSyncInfo({ running: true, needsLogin: false });
  try {
    for (;;) {
      const op = (await listOps()).find((candidate) => candidate.status === 'pending');
      if (!op || op.seq === undefined) break;
      const outcome = await sendOp(op);
      if (outcome.kind === 'ok') {
        reportNetworkSuccess();
        await removeOp(op.seq);
        result.sent += 1;
      } else if (outcome.kind === 'network') {
        reportNetworkFailure();
        result.stoppedBy = 'network';
        break;
      } else if (outcome.kind === 'auth') {
        if (!triedLogin && (await signInAgain())) {
          triedLogin = true;
          continue; // the same change again, with the new token
        }
        setSyncInfo({ needsLogin: true });
        result.stoppedBy = 'login';
        break;
      } else if (outcome.kind === 'retry') {
        const attempts = op.attempts + 1;
        const error = { status: outcome.status, message: outcome.message };
        if (attempts >= MAX_ATTEMPTS) {
          await updateOp(op.seq, { status: 'failed', attempts, error });
          result.refused += 1;
          continue;
        }
        await updateOp(op.seq, { attempts, error });
        result.stoppedBy = 'server';
        break;
      } else {
        // the server looked at it and said no: it needs the owner's eyes, the rest of the queue goes on
        await updateOp(op.seq, { status: 'failed', attempts: op.attempts + 1, error: { status: outcome.status, code: outcome.code, message: outcome.message } });
        result.refused += 1;
      }
    }
  } finally {
    await refreshOutboxCounts();
    setSyncInfo({ running: false, ...(result.sent > 0 ? { lastSent: { at: Date.now(), count: result.sent } } : {}) });
  }
  return result;
}

/** Sends what waits, one change at a time in the order they were made; one sending at a time. */
export function drainOutbox(): Promise<DrainResult> {
  if (!draining) {
    draining = run().finally(() => {
      draining = null;
    });
  }
  return draining;
}

/**
 * Starts the engine: it looks at the outbox soon after a change is made, when the signal returns, when the application starts and
 * every 30 s while something waits. Returns the function that stops it.
 */
export function startSync(): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  const request = (delayMs = 300) => {
    if (stopped) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (getOutboxCounts().pending > 0 && !getConnectionState().offline) void drainOutbox();
    }, delayMs);
  };
  setDrainRequester(request);
  void refreshOutboxCounts().then(() => request(1000));
  let wasOffline = getConnectionState().offline;
  const unsubscribe = subscribeConnection(() => {
    const offline = getConnectionState().offline;
    if (wasOffline && !offline) request(500);
    wasOffline = offline;
  });
  const interval = setInterval(() => request(0), SYNC_INTERVAL_MS);
  return () => {
    stopped = true;
    clearTimeout(timer);
    clearInterval(interval);
    unsubscribe();
    setDrainRequester(() => {});
  };
}
